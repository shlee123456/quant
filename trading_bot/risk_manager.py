"""
Risk management logic for paper trading.

Extracted from PaperTrader to follow single-responsibility principle.
Handles stop loss and take profit checks.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple


logger = logging.getLogger(__name__)


class RiskAction:
    """Represents a risk management action to take."""

    def __init__(self, symbol: str, action: str, current_price: float, pnl_pct: float):
        self.symbol = symbol
        self.action = action  # 'stop_loss' or 'take_profit'
        self.current_price = current_price
        self.pnl_pct = pnl_pct


class RiskManager:
    """
    Manages stop loss and take profit for trading positions.

    Args:
        stop_loss_pct: Stop loss percentage (e.g., 0.05 = 5%)
        take_profit_pct: Take profit percentage (e.g., 0.10 = 10%)
        enable_stop_loss: Whether stop loss is enabled
        enable_take_profit: Whether take profit is enabled
    """

    def __init__(
        self,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.enable_stop_loss = enable_stop_loss
        self.enable_take_profit = enable_take_profit

    def check_positions(
        self,
        positions: Dict[str, float],
        entry_prices: Dict[str, float],
        current_prices: Dict[str, float],
    ) -> List[RiskAction]:
        """
        Check all positions for stop loss / take profit triggers.

        Args:
            positions: Dict mapping symbol to position size
            entry_prices: Dict mapping symbol to entry price
            current_prices: Dict mapping symbol to current price

        Returns:
            List of RiskAction objects for positions that need to be closed
        """
        actions: List[RiskAction] = []

        for symbol, position_size in positions.items():
            if position_size == 0:
                continue

            if symbol not in current_prices or symbol not in entry_prices:
                continue

            entry_price = entry_prices[symbol]
            if entry_price == 0:
                continue

            current_price = current_prices[symbol]
            pnl_pct = (current_price - entry_price) / entry_price

            # Check stop loss
            if self.enable_stop_loss and pnl_pct <= -self.stop_loss_pct:
                logger.info(
                    f"손절매 발동! {symbol}: {pnl_pct*100:.2f}% "
                    f"(기준: -{self.stop_loss_pct*100:.0f}%)"
                )
                actions.append(RiskAction(symbol, 'stop_loss', current_price, pnl_pct))
                continue

            # Check take profit
            if self.enable_take_profit and pnl_pct >= self.take_profit_pct:
                logger.info(
                    f"익절매 발동! {symbol}: {pnl_pct*100:.2f}% "
                    f"(기준: +{self.take_profit_pct*100:.0f}%)"
                )
                actions.append(RiskAction(symbol, 'take_profit', current_price, pnl_pct))

        return actions

    def check_symbol(
        self,
        symbol: str,
        position: float,
        entry_price: float,
        current_price: float,
    ) -> Optional[RiskAction]:
        """
        Check a single symbol for stop loss / take profit.

        Args:
            symbol: Trading symbol
            position: Current position size
            entry_price: Entry price
            current_price: Current market price

        Returns:
            RiskAction if triggered, None otherwise
        """
        if position == 0 or entry_price == 0:
            return None

        pnl_pct = (current_price - entry_price) / entry_price

        if self.enable_stop_loss and pnl_pct <= -self.stop_loss_pct:
            logger.info(
                f"손절매 발동! {symbol}: {pnl_pct*100:.2f}% "
                f"(기준: -{self.stop_loss_pct*100:.0f}%)"
            )
            return RiskAction(symbol, 'stop_loss', current_price, pnl_pct)

        if self.enable_take_profit and pnl_pct >= self.take_profit_pct:
            logger.info(
                f"익절매 발동! {symbol}: {pnl_pct*100:.2f}% "
                f"(기준: +{self.take_profit_pct*100:.0f}%)"
            )
            return RiskAction(symbol, 'take_profit', current_price, pnl_pct)

        return None
