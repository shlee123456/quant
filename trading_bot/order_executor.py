"""
Order execution logic for paper trading.

Extracted from PaperTrader to follow single-responsibility principle.
Handles buy/sell execution, commission calculation, order deduplication,
partial position closing, and pyramiding support.
"""

import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any


logger = logging.getLogger(__name__)

# Deduplication window in seconds
_DEDUP_WINDOW_SECONDS = 5


class OrderExecutor:
    """
    Handles order execution for paper trading.

    Features:
    - Commission calculation
    - Order deduplication (same symbol+direction within 5 seconds)
    - Partial position closing (ratio parameter)
    - Pyramiding support (adding to existing positions with weighted avg entry)

    Args:
        commission: Trading commission rate (e.g., 0.001 = 0.1%)
        position_size: Fraction of capital to use per trade
        log_file: Optional path to log trades to file
    """

    def __init__(
        self,
        commission: float = 0.001,
        position_size: float = 0.95,
        log_file: Optional[str] = None,
    ):
        self.commission = commission
        self.position_size = position_size
        self.log_file = log_file

        # Order deduplication tracking: key = "symbol_direction" -> last order time
        self._recent_orders: Dict[str, datetime] = {}

    def _is_duplicate_order(self, symbol: str, direction: str, timestamp: datetime) -> bool:
        """
        Check if this order is a duplicate (same symbol+direction within dedup window).

        Args:
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            timestamp: Order timestamp

        Returns:
            True if duplicate, False otherwise
        """
        key = f"{symbol}_{direction}"
        last_time = self._recent_orders.get(key)

        if last_time is not None:
            elapsed = (timestamp - last_time).total_seconds()
            if elapsed < _DEDUP_WINDOW_SECONDS:
                logger.warning(
                    f"중복 주문 감지: {symbol} {direction} (마지막 주문으로부터 {elapsed:.1f}초 경과, "
                    f"기준: {_DEDUP_WINDOW_SECONDS}초)"
                )
                return True

        self._recent_orders[key] = timestamp
        return False

    def execute_buy(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        capital: float,
        positions: Dict[str, float],
        entry_prices: Dict[str, float],
        allow_pyramiding: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a buy order.

        Args:
            symbol: Trading symbol
            price: Buy price
            timestamp: Trade timestamp
            capital: Current available capital
            positions: Dict of current positions (modified in-place)
            entry_prices: Dict of entry prices (modified in-place)
            allow_pyramiding: If True, allows adding to existing position

        Returns:
            Trade dict if executed, None if skipped
        """
        # Deduplication check
        if self._is_duplicate_order(symbol, 'BUY', timestamp):
            return None

        # Check existing position
        if positions.get(symbol, 0) > 0 and not allow_pyramiding:
            logger.info(f"Already in position for {symbol}, skipping BUY signal")
            return None

        trade_capital = capital * self.position_size
        new_quantity = trade_capital / price * (1 - self.commission)

        if positions.get(symbol, 0) > 0 and allow_pyramiding:
            # Pyramiding: weighted average entry price
            existing_qty = positions[symbol]
            existing_entry = entry_prices[symbol]
            total_qty = existing_qty + new_quantity
            entry_prices[symbol] = (
                (existing_entry * existing_qty) + (price * new_quantity)
            ) / total_qty
            positions[symbol] = total_qty
        else:
            positions[symbol] = new_quantity
            entry_prices[symbol] = price

        new_capital = capital - trade_capital

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'size': positions[symbol] if allow_pyramiding and positions[symbol] != new_quantity else new_quantity,
            'capital': new_capital,
            'commission': trade_capital * self.commission,
        }

        # For pyramiding, record just the newly added quantity
        if allow_pyramiding and positions[symbol] != new_quantity:
            trade['size'] = new_quantity

        self._log_trade_to_file(trade)

        logger.info(f"[BUY] {symbol} {timestamp}")
        logger.debug(f"Price: ${price:.2f}")
        logger.debug(f"Size: {new_quantity:.6f}")
        logger.debug(f"Capital remaining: ${new_capital:.2f}")

        return trade

    def execute_sell(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        capital: float,
        positions: Dict[str, float],
        entry_prices: Dict[str, float],
        reason: str = 'signal',
        ratio: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a sell order.

        Args:
            symbol: Trading symbol
            price: Sell price
            timestamp: Trade timestamp
            capital: Current available capital
            positions: Dict of current positions (modified in-place)
            entry_prices: Dict of entry prices (modified in-place)
            reason: Reason for sell ('signal', 'stop_loss', 'take_profit')
            ratio: Fraction of position to sell (0.0-1.0). Default 1.0 = sell all.

        Returns:
            Trade dict if executed, None if skipped
        """
        if positions.get(symbol, 0) == 0:
            logger.info(f"No position to sell for {symbol}, skipping SELL signal")
            return None

        # Deduplication check
        if self._is_duplicate_order(symbol, 'SELL', timestamp):
            return None

        # Clamp ratio
        ratio = max(0.0, min(1.0, ratio))

        sell_quantity = positions[symbol] * ratio
        sale_proceeds = sell_quantity * price * (1 - self.commission)
        new_capital = capital + sale_proceeds

        # Calculate profit/loss based on entry price
        entry_price = entry_prices[symbol]
        pnl = sale_proceeds - (sell_quantity * entry_price)
        pnl_pct = (price - entry_price) / entry_price * 100

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'SELL',
            'price': price,
            'size': sell_quantity,
            'capital': new_capital,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'commission': sell_quantity * price * self.commission,
            'reason': reason,
        }

        reason_text = {
            'signal': '전략 시그널',
            'stop_loss': '손절매',
            'take_profit': '익절매',
        }
        reason_kr = reason_text.get(reason, '매도')

        logger.info(f"[매도 - {reason_kr}] {symbol} {timestamp}")
        logger.debug(f"가격: ${price:.2f}")
        logger.debug(f"수량: {sell_quantity:.6f}")
        logger.debug(f"손익: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        logger.debug(f"자본: ${new_capital:.2f}")

        # Update positions
        remaining = positions[symbol] - sell_quantity
        if remaining < 1e-10:
            # Fully closed
            positions[symbol] = 0
            entry_prices[symbol] = 0
        else:
            positions[symbol] = remaining

        self._log_trade_to_file(trade)

        return trade

    def execute_short(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        capital: float,
        positions: Dict[str, float],
        entry_prices: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a short sell order.

        Args:
            symbol: Trading symbol
            price: Short entry price
            timestamp: Trade timestamp
            capital: Current available capital
            positions: Dict of current positions (modified in-place)
            entry_prices: Dict of entry prices (modified in-place)

        Returns:
            Trade dict if executed, None if skipped
        """
        # Deduplication check
        if self._is_duplicate_order(symbol, 'SHORT', timestamp):
            return None

        # Cannot short if already in a position
        if positions.get(symbol, 0) != 0:
            logger.info(f"Already in position for {symbol}, skipping SHORT signal")
            return None

        trade_capital = capital * self.position_size
        new_quantity = trade_capital / price * (1 - self.commission)

        positions[symbol] = -new_quantity  # Negative = short
        entry_prices[symbol] = price

        new_capital = capital - trade_capital

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'SHORT',
            'price': price,
            'size': new_quantity,
            'capital': new_capital,
            'commission': trade_capital * self.commission,
        }

        self._log_trade_to_file(trade)

        logger.info(f"[SHORT] {symbol} {timestamp}")
        logger.debug(f"Price: ${price:.2f}")
        logger.debug(f"Size: {new_quantity:.6f}")
        logger.debug(f"Capital remaining: ${new_capital:.2f}")

        return trade

    def execute_cover(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        capital: float,
        positions: Dict[str, float],
        entry_prices: Dict[str, float],
        reason: str = 'signal',
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a cover (buy-to-cover) order to close a short position.

        Args:
            symbol: Trading symbol
            price: Cover price
            timestamp: Trade timestamp
            capital: Current available capital
            positions: Dict of current positions (modified in-place)
            entry_prices: Dict of entry prices (modified in-place)
            reason: Reason for cover ('signal', 'stop_loss', 'take_profit')

        Returns:
            Trade dict if executed, None if skipped
        """
        if positions.get(symbol, 0) >= 0:
            logger.info(f"No short position to cover for {symbol}, skipping COVER signal")
            return None

        # Deduplication check
        if self._is_duplicate_order(symbol, 'COVER', timestamp):
            return None

        entry_price = entry_prices[symbol]
        abs_position = abs(positions[symbol])
        commission_cost = abs_position * price * self.commission

        # PnL for short: profit when price drops
        pnl = abs_position * (entry_price - price) * (1 - self.commission)
        pnl_pct = (entry_price - price) / entry_price * 100

        # Return collateral + pnl
        new_capital = capital + abs_position * entry_price + abs_position * (entry_price - price) - commission_cost

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'COVER',
            'price': price,
            'size': abs_position,
            'capital': new_capital,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'commission': commission_cost,
            'reason': reason,
        }

        reason_text = {
            'signal': '시그널 커버',
            'stop_loss': '손절매 커버',
            'take_profit': '익절매 커버',
        }
        reason_kr = reason_text.get(reason, '커버')

        logger.info(f"[커버 - {reason_kr}] {symbol} {timestamp}")
        logger.debug(f"가격: ${price:.2f}")
        logger.debug(f"수량: {abs_position:.6f}")
        logger.debug(f"손익: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        logger.debug(f"자본: ${new_capital:.2f}")

        # Update positions
        positions[symbol] = 0
        entry_prices[symbol] = 0

        self._log_trade_to_file(trade)

        return trade

    def _log_trade_to_file(self, trade: Dict):
        """Log trade to file if configured."""
        if not self.log_file:
            return

        try:
            with open(self.log_file, 'a') as f:
                trade_copy = trade.copy()
                trade_copy['timestamp'] = str(trade_copy['timestamp'])
                f.write(json.dumps(trade_copy) + '\n')
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
