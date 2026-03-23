"""
SafetyGuard module for live trading safety controls.

Enforces daily loss limits, trade count limits, position count limits,
capital-per-position limits, slippage tolerance, and a kill switch
to prevent catastrophic losses during live trading.
"""

import logging
from datetime import date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SafetyGuard:
    """
    Safety guard for live trading with kill switch and daily limits.

    Args:
        initial_capital: Initial trading capital (required).
        max_daily_loss_pct: Maximum daily loss as fraction of initial capital (e.g., 0.05 = 5%).
        max_daily_trades: Maximum number of trades allowed per day.
        max_position_count: Maximum number of simultaneous open positions.
        max_capital_per_position_pct: Maximum fraction of capital per single position.
        slippage_tolerance_pct: Maximum acceptable slippage as fraction of requested price.
        db: Optional TradingDatabase instance for persisting kill switch state.
        notifier: Optional NotificationService instance for kill switch alerts.
    """

    def __init__(
        self,
        initial_capital: float,
        max_daily_loss_pct: float = 0.05,
        max_daily_trades: int = 50,
        max_position_count: int = 10,
        max_capital_per_position_pct: float = 0.15,
        slippage_tolerance_pct: float = 0.02,
        db=None,
        notifier=None,
    ):
        self.initial_capital = initial_capital
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_daily_trades = max_daily_trades
        self.max_position_count = max_position_count
        self.max_capital_per_position_pct = max_capital_per_position_pct
        self.slippage_tolerance_pct = slippage_tolerance_pct
        self.db = db
        self.notifier = notifier

        # Daily counters
        self._daily_trade_count: int = 0
        self._daily_pnl: float = 0.0
        self._daily_reset_date: date = date.today()

        # Kill switch state
        self._kill_switch_active: bool = False

        # Try loading kill switch state from DB
        if db is not None:
            try:
                state = db.get_live_state('kill_switch_active')
                self._kill_switch_active = (state == 'true')
            except (AttributeError, Exception):
                pass

    def pre_order_check(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        positions: Dict[str, float],
        capital: float,
    ) -> Tuple[bool, str]:
        """
        Run pre-order safety checks before submitting an order.

        Checks in order:
        1. Kill switch active
        2. Daily loss limit
        3. Daily trade count
        4. Position count limit (buy only)
        5. Capital per position limit

        Args:
            symbol: Trading symbol.
            side: Order side ('buy' or 'sell').
            amount: Order quantity.
            price: Order price.
            positions: Current positions dict {symbol: qty}.
            capital: Current available capital.

        Returns:
            Tuple of (allowed: bool, reason: str). If allowed, reason is 'ok'.
        """
        self._check_daily_reset()

        # 1. Kill switch
        if self._kill_switch_active:
            return (False, 'Kill switch is active')

        # 2. Daily loss limit
        if self.initial_capital > 0 and self._daily_pnl / self.initial_capital <= -self.max_daily_loss_pct:
            return (False, f'Daily loss limit exceeded: {self._daily_pnl:.2f}')

        # 3. Daily trade count
        if self._daily_trade_count >= self.max_daily_trades:
            return (False, f'Daily trade count limit reached: {self._daily_trade_count}')

        # 4. Position count limit (buy only)
        if side == 'buy':
            open_positions = sum(1 for qty in positions.values() if qty > 0)
            if open_positions >= self.max_position_count:
                return (False, f'Position count limit reached: {open_positions}')

        # 5. Capital per position
        if capital > 0 and (amount * price) / capital > self.max_capital_per_position_pct:
            return (False, f'Capital per position limit exceeded: {amount * price / capital:.2%} > {self.max_capital_per_position_pct:.2%}')

        return (True, 'ok')

    def post_fill_check(self, requested_price: float, fill_price: float) -> Tuple[bool, float]:
        """
        Check slippage after an order fill.

        Args:
            requested_price: The price requested for the order.
            fill_price: The actual fill price.

        Returns:
            Tuple of (within_tolerance: bool, slippage_pct: float).
        """
        if requested_price == 0:
            return (True, 0.0)
        slippage_pct = abs(fill_price - requested_price) / requested_price
        return (slippage_pct <= self.slippage_tolerance_pct, slippage_pct)

    def record_trade(self, pnl: float) -> None:
        """
        Record a completed trade and check daily loss limit.

        Called by LiveTrader AFTER each SELL order fills with realized PnL.

        Args:
            pnl: Realized profit/loss from the trade.
        """
        self._daily_trade_count += 1
        self._daily_pnl += pnl

        if self.initial_capital > 0 and self._daily_pnl / self.initial_capital <= -self.max_daily_loss_pct:
            self.activate_kill_switch(
                f'Daily loss {self._daily_pnl:.2f} exceeded {self.max_daily_loss_pct * 100}% of {self.initial_capital}'
            )

    def activate_kill_switch(self, reason: str) -> None:
        """
        Activate the kill switch to halt all trading.

        Args:
            reason: Human-readable reason for activation.
        """
        self._kill_switch_active = True

        if self.db is not None:
            try:
                self.db.set_live_state('kill_switch_active', 'true')
                self.db.set_live_state('kill_switch_reason', reason)
            except (AttributeError, Exception):
                pass

        if self.notifier is not None:
            self.notifier.notify_error(f'KILL SWITCH: {reason}', 'SafetyGuard')

        logger.critical(reason)

    def deactivate_kill_switch(self) -> None:
        """Deactivate the kill switch to resume trading."""
        self._kill_switch_active = False

        if self.db is not None:
            try:
                self.db.set_live_state('kill_switch_active', 'false')
            except (AttributeError, Exception):
                pass

    def is_kill_switch_active(self) -> bool:
        """Return whether the kill switch is currently active."""
        return self._kill_switch_active

    def reset_daily_counters(self) -> None:
        """Reset daily trade count and PnL counters."""
        self._daily_trade_count = 0
        self._daily_pnl = 0.0
        self._daily_reset_date = date.today()

    def _check_daily_reset(self) -> None:
        """Auto-reset daily counters if the date has changed."""
        if date.today() != self._daily_reset_date:
            self.reset_daily_counters()
