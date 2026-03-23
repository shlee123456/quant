"""
LiveOrderManager module for live trading order lifecycle management.

Wraps broker.create_order() with lifecycle tracking, error handling,
fill confirmation, deduplication, and safety guard integration.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from trading_bot.brokers.base_broker import (
    BaseBroker,
    BrokerError,
    InsufficientFunds,
    RateLimitExceeded,
)
from trading_bot.retry_utils import retry_with_backoff
from trading_bot.safety_guard import SafetyGuard

logger = logging.getLogger(__name__)

# Deduplication window in seconds (same as OrderExecutor)
_DEDUP_WINDOW_SECONDS = 5

# Fill polling config for market orders
_FILL_POLL_ATTEMPTS = 5
_FILL_POLL_INTERVAL = 1  # seconds


@dataclass
class LiveOrder:
    """Represents a live trading order with full lifecycle tracking."""

    internal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    broker_order_id: Optional[str] = None
    symbol: str = ''
    side: str = ''  # 'buy' or 'sell'
    order_type: str = 'market'  # 'market' or 'limit'
    requested_amount: float = 0.0
    requested_price: Optional[float] = None
    filled_amount: float = 0.0
    filled_price: float = 0.0
    status: str = 'pending'
    reason: str = 'signal'
    submitted_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    commission: float = 0.0
    slippage_pct: float = 0.0
    error_message: Optional[str] = None


def _normalize_broker_status(raw_status: str) -> str:
    """Normalize broker order status to internal status.

    'closed'/'filled' -> 'filled'
    'open'/'pending'/'submitted' -> 'pending'
    'canceled'/'cancelled' -> 'canceled'
    """
    raw = raw_status.lower()
    if raw in ('closed', 'filled'):
        return 'filled'
    elif raw in ('open', 'pending', 'submitted'):
        return 'pending'
    elif raw in ('canceled', 'cancelled'):
        return 'canceled'
    return raw


class LiveOrderManager:
    """
    Manages live order lifecycle: submission, fill tracking, cancellation.

    Wraps broker.create_order() with:
    - Safety guard pre-order checks
    - Deduplication (5-second window on symbol+side)
    - Fill polling for market orders
    - Slippage calculation
    - Error handling with retry for RateLimitExceeded
    - DB logging

    Args:
        broker: BaseBroker instance for order execution.
        safety_guard: SafetyGuard instance for pre/post order checks.
        db: Optional TradingDatabase for order persistence.
        notifier: Optional NotificationService for error alerts.
        session_id: Optional session ID for DB logging.
    """

    def __init__(
        self,
        broker: BaseBroker,
        safety_guard: SafetyGuard,
        db=None,
        notifier=None,
        session_id: Optional[str] = None,
    ):
        self.broker = broker
        self.safety_guard = safety_guard
        self.db = db
        self.notifier = notifier
        self.session_id = session_id

        # Active orders by internal_id
        self._active_orders: Dict[str, LiveOrder] = {}

        # Deduplication: 'symbol_side' -> last order timestamp
        self._last_orders: Dict[str, datetime] = {}

    def submit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = 'market',
        price: Optional[float] = None,
        reason: str = 'signal',
        dry_run: bool = False,
        positions: Optional[Dict[str, float]] = None,
        capital: float = 0.0,
    ) -> LiveOrder:
        """
        Submit a new order with safety checks, dedup, and fill tracking.

        Args:
            symbol: Trading symbol.
            side: Order side ('buy' or 'sell').
            amount: Order quantity.
            order_type: 'market' or 'limit'.
            price: Order price (required for limit orders).
            reason: Reason for the order.
            dry_run: If True, log order without broker submission.
            positions: Current positions dict for safety guard.
            capital: Current capital for safety guard.

        Returns:
            LiveOrder with final status.
        """
        order = LiveOrder(
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_amount=amount,
            requested_price=price,
            reason=reason,
            submitted_at=datetime.now(),
        )

        # 1. Dedup check
        if self._is_duplicate_order(symbol, side):
            order.status = 'rejected'
            order.error_message = 'Duplicate order within 5 seconds'
            logger.warning(
                f"Duplicate order rejected: {symbol} {side}"
            )
            self._active_orders[order.internal_id] = order
            self._log_order_to_db(order)
            return order

        # 2. Safety guard pre-order check
        check_price = price if price is not None else 0.0
        allowed, check_reason = self.safety_guard.pre_order_check(
            symbol, side, amount, check_price,
            positions or {}, capital,
        )
        if not allowed:
            order.status = 'rejected'
            order.error_message = check_reason
            logger.warning(f"Order rejected by safety guard: {check_reason}")
            self._active_orders[order.internal_id] = order
            self._log_order_to_db(order)
            return order

        # 3. Dry run: log and return without broker call
        if dry_run:
            order.status = 'dry_run'
            logger.info(
                f"[DRY RUN] {side.upper()} {amount} {symbol} "
                f"@ {price or 'market'} reason={reason}"
            )
            self._active_orders[order.internal_id] = order
            self._log_order_to_db(order)
            return order

        # 4. Submit to broker
        try:
            broker_result = self._submit_to_broker(
                symbol, order_type, side, amount, price
            )
        except InsufficientFunds as e:
            order.status = 'failed'
            order.error_message = str(e)[:500]
            logger.error(f"Insufficient funds for {symbol} {side}: {e}")
            if self.notifier:
                self.notifier.notify_error(
                    f"InsufficientFunds: {symbol} {side} {amount}",
                    'LiveOrderManager',
                )
            self._active_orders[order.internal_id] = order
            self._log_order_to_db(order)
            return order
        except RateLimitExceeded as e:
            # Retry with backoff: 3 retries
            broker_result = self._retry_broker_submit(
                symbol, order_type, side, amount, price, order
            )
            if broker_result is None:
                # All retries exhausted
                return order
        except BrokerError as e:
            order.status = 'failed'
            order.error_message = str(e)[:500]
            logger.error(f"Broker error for {symbol} {side}: {e}")
            if self.notifier:
                self.notifier.notify_error(
                    f"BrokerError: {symbol} {side} - {str(e)[:200]}",
                    'LiveOrderManager',
                )
            self._active_orders[order.internal_id] = order
            self._log_order_to_db(order)
            return order

        # Process broker result
        order.broker_order_id = broker_result.get('id')

        # Check if already filled from create_order response
        raw_status = broker_result.get('status', '')
        normalized = _normalize_broker_status(raw_status)
        if normalized == 'filled':
            self._update_fill_info(order, broker_result)
        else:
            order.status = 'submitted'

        # 5. Log to DB
        self._active_orders[order.internal_id] = order
        self._log_order_to_db(order)

        # 6. Poll fill status (market orders only)
        if order_type == 'market' and order.status != 'filled':
            self._poll_fill_status(order)

        # Slippage calculation for filled orders
        if order.status == 'filled' and order.requested_price is not None:
            self._calc_slippage(order)

        return order

    def cancel_order(self, internal_id: str) -> bool:
        """
        Cancel an order by internal ID.

        Args:
            internal_id: Internal order ID.

        Returns:
            True if successfully canceled, False otherwise.
        """
        order = self._active_orders.get(internal_id)
        if order is None:
            logger.warning(f"Order not found: {internal_id}")
            return False

        if order.broker_order_id is None:
            logger.warning(
                f"Cannot cancel order without broker_order_id: {internal_id}"
            )
            return False

        try:
            self.broker.cancel_order(order.broker_order_id, order.symbol)
            order.status = 'canceled'
            self._update_order_in_db(order, {'status': 'canceled'})
            logger.info(f"Order canceled: {internal_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {internal_id}: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """
        Cancel all pending/submitted orders.

        Returns:
            Number of successfully canceled orders.
        """
        canceled_count = 0
        for internal_id, order in list(self._active_orders.items()):
            if order.status in ('pending', 'submitted'):
                if self.cancel_order(internal_id):
                    canceled_count += 1
        return canceled_count

    def get_pending_orders(self) -> List[LiveOrder]:
        """
        Get all pending/submitted orders.

        Returns:
            List of LiveOrder with status 'pending' or 'submitted'.
        """
        return [
            order for order in self._active_orders.values()
            if order.status in ('pending', 'submitted')
        ]

    def _is_duplicate_order(self, symbol: str, side: str) -> bool:
        """Check if same symbol+side order was placed within dedup window."""
        key = f"{symbol}_{side}"
        now = datetime.now()
        last_time = self._last_orders.get(key)

        if last_time is not None:
            elapsed = (now - last_time).total_seconds()
            if elapsed < _DEDUP_WINDOW_SECONDS:
                return True

        self._last_orders[key] = now
        return False

    def _submit_to_broker(
        self, symbol: str, order_type: str, side: str,
        amount: float, price: Optional[float],
    ) -> Dict:
        """Submit order to broker. Raises broker exceptions."""
        return self.broker.create_order(symbol, order_type, side, amount, price)

    def _retry_broker_submit(
        self, symbol: str, order_type: str, side: str,
        amount: float, price: Optional[float], order: LiveOrder,
    ) -> Optional[Dict]:
        """Retry broker submission on RateLimitExceeded (up to 3 retries)."""
        max_retries = 3
        delay = 1.0

        for attempt in range(max_retries):
            logger.warning(
                f"RateLimitExceeded retry {attempt + 1}/{max_retries} "
                f"for {symbol} {side}"
            )
            time.sleep(delay)
            delay *= 2  # backoff_factor=2

            try:
                return self.broker.create_order(
                    symbol, order_type, side, amount, price
                )
            except RateLimitExceeded:
                if attempt == max_retries - 1:
                    order.status = 'failed'
                    order.error_message = 'RateLimitExceeded after 3 retries'
                    logger.error(
                        f"RateLimitExceeded after {max_retries} retries: "
                        f"{symbol} {side}"
                    )
                    if self.notifier:
                        self.notifier.notify_error(
                            f"RateLimitExceeded after 3 retries: "
                            f"{symbol} {side}",
                            'LiveOrderManager',
                        )
                    self._active_orders[order.internal_id] = order
                    self._log_order_to_db(order)
                    return None
            except BrokerError as e:
                order.status = 'failed'
                order.error_message = str(e)[:500]
                logger.error(f"Broker error on retry: {e}")
                if self.notifier:
                    self.notifier.notify_error(
                        f"BrokerError on retry: {str(e)[:200]}",
                        'LiveOrderManager',
                    )
                self._active_orders[order.internal_id] = order
                self._log_order_to_db(order)
                return None

        return None

    def _poll_fill_status(self, order: LiveOrder) -> None:
        """Poll broker for fill status (market orders, up to 5 attempts)."""
        if order.broker_order_id is None:
            return

        for attempt in range(_FILL_POLL_ATTEMPTS):
            time.sleep(_FILL_POLL_INTERVAL)
            try:
                result = self.broker.fetch_order(
                    order.broker_order_id, order.symbol
                )
                normalized = _normalize_broker_status(
                    result.get('status', '')
                )
                if normalized == 'filled':
                    self._update_fill_info(order, result)
                    self._update_order_in_db(order, {
                        'status': 'filled',
                        'filled_amount': order.filled_amount,
                        'filled_price': order.filled_price,
                        'filled_at': order.filled_at.isoformat()
                        if order.filled_at else None,
                    })
                    return
                elif normalized == 'canceled':
                    order.status = 'canceled'
                    self._update_order_in_db(order, {'status': 'canceled'})
                    return
            except Exception as e:
                logger.warning(
                    f"Fill poll attempt {attempt + 1} failed: {e}"
                )

        # Still pending after all polls
        if order.status != 'filled':
            order.status = 'submitted'
            logger.warning(
                f"Order {order.internal_id} still pending after "
                f"{_FILL_POLL_ATTEMPTS} polls"
            )
            self._update_order_in_db(order, {'status': 'submitted'})

    def _update_fill_info(self, order: LiveOrder, result: Dict) -> None:
        """Update LiveOrder with fill information from broker result."""
        order.status = 'filled'
        order.filled_amount = result.get('filled', result.get('amount', 0.0)) or 0.0
        order.filled_price = result.get('average', result.get('price', 0.0)) or 0.0
        order.filled_at = datetime.now()
        order.commission = result.get('fee', {}).get('cost', 0.0) if isinstance(
            result.get('fee'), dict
        ) else 0.0

    def _calc_slippage(self, order: LiveOrder) -> None:
        """Calculate slippage and run post-fill check."""
        if order.requested_price is None or order.requested_price == 0:
            return
        order.slippage_pct = abs(
            order.filled_price - order.requested_price
        ) / order.requested_price
        self.safety_guard.post_fill_check(
            order.requested_price, order.filled_price
        )

    def _log_order_to_db(self, order: LiveOrder) -> None:
        """Log order to database if db is available."""
        if self.db is None:
            return
        try:
            self.db.log_live_order({
                'internal_id': order.internal_id,
                'session_id': self.session_id or '',
                'broker_order_id': order.broker_order_id,
                'symbol': order.symbol,
                'side': order.side,
                'order_type': order.order_type,
                'requested_amount': order.requested_amount,
                'requested_price': order.requested_price,
                'filled_amount': order.filled_amount,
                'filled_price': order.filled_price,
                'status': order.status,
                'reason': order.reason,
                'submitted_at': order.submitted_at.isoformat(),
                'filled_at': order.filled_at.isoformat()
                if order.filled_at else None,
                'commission': order.commission,
                'slippage_pct': order.slippage_pct,
                'error_message': order.error_message,
            })
        except Exception as e:
            logger.error(f"Failed to log order to DB: {e}")

    def _update_order_in_db(self, order: LiveOrder, updates: Dict) -> None:
        """Update order in database if db is available."""
        if self.db is None:
            return
        try:
            self.db.update_live_order(order.internal_id, updates)
        except Exception as e:
            logger.error(f"Failed to update order in DB: {e}")
