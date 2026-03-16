"""
Performance metrics calculator for trading sessions.

Extracted from PaperTrader to follow single-responsibility principle.
Calculates Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor, etc.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
import logging


logger = logging.getLogger(__name__)


# Annualization factors for Sharpe ratio by timeframe
ANNUALIZATION_FACTORS = {
    '1d': np.sqrt(252),
    '1h': np.sqrt(252 * 6.5),
    '4h': np.sqrt(252 * 1.625),
    '15m': np.sqrt(252 * 26),
}


class PerformanceCalculator:
    """
    Calculates trading performance metrics from trades and equity history.

    Args:
        timeframe: Trading timeframe for Sharpe ratio annualization.
                   Supported: '1d', '1h', '4h', '15m'. Default: '1h'.
    """

    def __init__(self, timeframe: str = '1h'):
        self.timeframe = timeframe

    def _get_annualization_factor(self) -> float:
        """Return the annualization factor for the configured timeframe."""
        return ANNUALIZATION_FACTORS.get(self.timeframe, ANNUALIZATION_FACTORS['1h'])

    def calculate_sharpe_ratio(self, equity_history: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate Sharpe ratio from equity history.

        Args:
            equity_history: List of dicts with 'equity' key.

        Returns:
            Annualized Sharpe ratio or None if insufficient data.
        """
        if len(equity_history) < 2:
            return None

        equity_values = [eq['equity'] for eq in equity_history]
        returns = pd.Series(equity_values).pct_change().dropna()

        if len(returns) < 2:
            return None

        mean_return = returns.mean()
        std_return = returns.std()

        if std_return == 0:
            return None

        factor = self._get_annualization_factor()
        sharpe = (mean_return / std_return) * factor
        return float(sharpe)

    def calculate_max_drawdown(self, equity_history: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate maximum drawdown from equity history.

        Args:
            equity_history: List of dicts with 'equity' key.

        Returns:
            Max drawdown as a percentage, or None if no data.
        """
        if not equity_history:
            return None

        equity_values = [eq['equity'] for eq in equity_history]
        peak = equity_values[0]
        max_dd = 0.0

        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return float(max_dd)

    def calculate_win_rate(self, trades: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate win rate from completed trades.

        Args:
            trades: List of trade dicts. SELL trades with 'pnl' key are used.

        Returns:
            Win rate as a percentage, or None if no sell trades.
        """
        sell_trades = [t for t in trades if t['type'] in ('SELL', 'COVER')]

        if not sell_trades:
            return None

        winning = [t for t in sell_trades if t.get('pnl', 0) > 0]
        win_rate = len(winning) / len(sell_trades) * 100

        return float(win_rate)

    def calculate_profit_factor(self, trades: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate profit factor (gross profit / gross loss).

        Args:
            trades: List of trade dicts. SELL/COVER trades with 'pnl' key are used.

        Returns:
            Profit factor, or None if no losing trades.
        """
        sell_trades = [t for t in trades if t['type'] in ('SELL', 'COVER')]

        if not sell_trades:
            return None

        gross_profit = sum(t['pnl'] for t in sell_trades if t.get('pnl', 0) > 0)
        gross_loss = abs(sum(t['pnl'] for t in sell_trades if t.get('pnl', 0) < 0))

        if gross_loss == 0:
            return None

        return float(gross_profit / gross_loss)

    def get_performance_summary(
        self,
        trades: List[Dict[str, Any]],
        equity_history: List[Dict[str, Any]],
        initial_capital: float
    ) -> Dict[str, Any]:
        """
        Calculate a complete performance summary.

        Args:
            trades: List of trade dicts.
            equity_history: List of equity history dicts.
            initial_capital: Initial capital amount.

        Returns:
            Dict with all performance metrics.
        """
        final_value = equity_history[-1]['equity'] if equity_history else initial_capital
        total_return = ((final_value - initial_capital) / initial_capital) * 100

        sell_trades = [t for t in trades if t['type'] in ('SELL', 'COVER')]

        summary = {
            'initial_capital': initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'total_trades': len(sell_trades),
            'sharpe_ratio': self.calculate_sharpe_ratio(equity_history),
            'max_drawdown': self.calculate_max_drawdown(equity_history),
            'win_rate': self.calculate_win_rate(trades),
            'profit_factor': self.calculate_profit_factor(trades),
        }

        if sell_trades:
            winning = [t for t in sell_trades if t.get('pnl', 0) > 0]
            summary['winning_trades'] = len(winning)
            summary['losing_trades'] = len(sell_trades) - len(winning)

        return summary
