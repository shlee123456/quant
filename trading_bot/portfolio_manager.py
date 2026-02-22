"""
Portfolio state management for paper trading.

Extracted from PaperTrader to follow single-responsibility principle.
Manages positions, capital, equity tracking, and portfolio snapshots.
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd


logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Manages portfolio state: positions, capital, equity history, and snapshots.

    Args:
        symbols: List of trading symbols
        initial_capital: Starting capital
        db: Optional TradingDatabase instance for persistent logging
        max_equity_history: Maximum number of equity history entries to keep
    """

    def __init__(
        self,
        symbols: List[str],
        initial_capital: float = 10000.0,
        db=None,
        max_equity_history: int = 5000,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, float] = {symbol: 0.0 for symbol in symbols}
        self.entry_prices: Dict[str, float] = {symbol: 0.0 for symbol in symbols}
        self.last_signals: Dict[str, int] = {symbol: 0 for symbol in symbols}

        self.trades: List[Dict[str, Any]] = []
        self.equity_history: List[Dict[str, Any]] = []

        self.db = db
        self.max_equity_history = max_equity_history

        self._lock = threading.RLock()

    def get_portfolio_value(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate current portfolio value.

        Args:
            current_prices: Dict mapping symbol to current price.
                           If None, only returns cash value.

        Returns:
            Total portfolio value (cash + positions)
        """
        if current_prices is None:
            current_prices = {}

        total_value = self.capital

        for symbol, position in self.positions.items():
            if position > 0 and symbol in current_prices:
                total_value += position * current_prices[symbol]

        return total_value

    def record_equity(self, entry: Dict[str, Any]):
        """
        Append an equity history entry, trimming if over the cap.

        Args:
            entry: Dict with at least 'timestamp' and 'equity' keys.
        """
        with self._lock:
            self.equity_history.append(entry)
            if len(self.equity_history) > self.max_equity_history:
                self.equity_history = self.equity_history[-self.max_equity_history:]

    def take_snapshot(self, session_id: Optional[str], timestamp: datetime,
                      total_value: float, current_prices: Optional[Dict[str, float]] = None):
        """
        Take a portfolio snapshot and log to database.

        Args:
            session_id: Current session ID (None skips DB logging)
            timestamp: Snapshot timestamp
            total_value: Total portfolio value
            current_prices: Optional dict of current prices
        """
        if not self.db or not session_id:
            return

        snapshot = {
            'timestamp': timestamp,
            'total_value': total_value,
            'cash': self.capital,
            'positions': self.positions.copy()
        }

        self.db.log_portfolio_snapshot(session_id, snapshot)

    def record_trade(self, trade: Dict[str, Any]):
        """Append a trade to the trade history."""
        with self._lock:
            self.trades.append(trade)

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        return pd.DataFrame(self.trades)

    def get_equity_df(self) -> pd.DataFrame:
        """Get equity history as DataFrame."""
        return pd.DataFrame(self.equity_history)
