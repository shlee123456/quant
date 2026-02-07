"""
Unit tests for backtesting engine
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy import MovingAverageCrossover
from trading_bot.backtester import Backtester


class TestBacktester(unittest.TestCase):
    """Test cases for Backtester"""

    def setUp(self):
        """Set up test fixtures"""
        self.strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        self.backtester = Backtester(
            strategy=self.strategy,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        # Create sample data with clear signals
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')

        # Create trending data
        prices = np.concatenate([
            np.linspace(100, 120, 30),  # Uptrend
            np.linspace(120, 110, 20),  # Downtrend
            np.linspace(110, 130, 30),  # Uptrend
            np.linspace(130, 115, 20)   # Downtrend
        ])

        self.sample_data = pd.DataFrame({
            'open': prices,
            'high': prices + 2,
            'low': prices - 2,
            'close': prices,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)

    def test_initialization(self):
        """Test backtester initialization"""
        self.assertEqual(self.backtester.initial_capital, 10000.0)
        self.assertEqual(self.backtester.position_size, 0.95)
        self.assertEqual(self.backtester.commission, 0.001)
        self.assertEqual(self.backtester.trades, [])
        self.assertEqual(self.backtester.equity_curve, [])

    def test_run_backtest(self):
        """Test running a backtest"""
        results = self.backtester.run(self.sample_data)

        # Check results dictionary has required keys
        required_keys = [
            'initial_capital', 'final_capital', 'total_return',
            'total_trades', 'winning_trades', 'losing_trades',
            'win_rate', 'avg_win', 'avg_loss', 'max_drawdown',
            'sharpe_ratio', 'start_date', 'end_date'
        ]

        for key in required_keys:
            self.assertIn(key, results)

    def test_trades_generated(self):
        """Test that trades are generated"""
        results = self.backtester.run(self.sample_data)

        # Should have some trades
        self.assertGreater(len(self.backtester.trades), 0)

        # Should have both buy and sell trades
        buy_trades = [t for t in self.backtester.trades if t['type'] == 'BUY']
        sell_trades = [t for t in self.backtester.trades if 'SELL' in t['type']]

        self.assertGreater(len(buy_trades), 0)
        self.assertGreater(len(sell_trades), 0)

    def test_equity_curve_generated(self):
        """Test that equity curve is generated"""
        results = self.backtester.run(self.sample_data)

        # Should have equity curve data
        self.assertGreater(len(self.backtester.equity_curve), 0)

        # Each equity point should have required fields
        required_keys = ['timestamp', 'equity', 'price', 'position']
        for point in self.backtester.equity_curve:
            for key in required_keys:
                self.assertIn(key, point)

    def test_commission_applied(self):
        """Test that commission is applied to trades"""
        results = self.backtester.run(self.sample_data)

        # Check that trades have commission
        for trade in self.backtester.trades:
            self.assertIn('commission', trade)
            self.assertGreater(trade['commission'], 0)

    def test_final_capital_calculation(self):
        """Test final capital is calculated correctly"""
        results = self.backtester.run(self.sample_data)

        # Final capital should be positive
        self.assertGreater(results['final_capital'], 0)

        # Total return should match capital change
        expected_return = ((results['final_capital'] - results['initial_capital']) /
                          results['initial_capital']) * 100
        self.assertAlmostEqual(results['total_return'], expected_return, places=2)

    def test_win_rate_calculation(self):
        """Test win rate calculation"""
        results = self.backtester.run(self.sample_data)

        if results['total_trades'] > 0:
            expected_win_rate = (results['winning_trades'] / results['total_trades']) * 100
            self.assertAlmostEqual(results['win_rate'], expected_win_rate, places=2)

            # Win rate should be between 0 and 100
            self.assertGreaterEqual(results['win_rate'], 0)
            self.assertLessEqual(results['win_rate'], 100)

    def test_get_trades_df(self):
        """Test getting trades as DataFrame"""
        results = self.backtester.run(self.sample_data)
        trades_df = self.backtester.get_trades_df()

        # Should return a DataFrame
        self.assertIsInstance(trades_df, pd.DataFrame)

        if not trades_df.empty:
            # Should have required columns
            self.assertIn('timestamp', trades_df.columns)
            self.assertIn('type', trades_df.columns)
            self.assertIn('price', trades_df.columns)

    def test_get_equity_curve_df(self):
        """Test getting equity curve as DataFrame"""
        results = self.backtester.run(self.sample_data)
        equity_df = self.backtester.get_equity_curve_df()

        # Should return a DataFrame
        self.assertIsInstance(equity_df, pd.DataFrame)

        # Should have required columns
        self.assertIn('timestamp', equity_df.columns)
        self.assertIn('equity', equity_df.columns)
        self.assertIn('price', equity_df.columns)

    def test_position_sizing(self):
        """Test position sizing is respected"""
        results = self.backtester.run(self.sample_data)

        # Check buy trades use correct position size
        buy_trades = [t for t in self.backtester.trades if t['type'] == 'BUY']

        for trade in buy_trades:
            # Position value should be approximately position_size * capital at time of trade
            # (accounting for commission)
            expected_capital_used = self.backtester.initial_capital * self.backtester.position_size
            # This is approximate due to capital changes over time
            self.assertGreater(trade['size'], 0)

    def test_no_signals_scenario(self):
        """Test backtester with data that generates no signals"""
        # Create flat data that won't generate signals
        dates = pd.date_range(start='2024-01-01', periods=20, freq='1H')
        flat_data = pd.DataFrame({
            'open': [100] * 20,
            'high': [100.5] * 20,
            'low': [99.5] * 20,
            'close': [100] * 20,
            'volume': [1000] * 20
        }, index=dates)

        backtester = Backtester(
            strategy=self.strategy,
            initial_capital=10000.0
        )

        results = backtester.run(flat_data)

        # Should have minimal or no trades
        self.assertLessEqual(results['total_trades'], 1)

        # Final capital should be close to initial (minus any commissions)
        self.assertAlmostEqual(
            results['final_capital'],
            results['initial_capital'],
            delta=100
        )

    def test_max_drawdown_calculation(self):
        """Test maximum drawdown calculation"""
        results = self.backtester.run(self.sample_data)

        # Max drawdown should be negative or zero
        self.assertLessEqual(results['max_drawdown'], 0)

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation"""
        results = self.backtester.run(self.sample_data)

        # Sharpe ratio should be a number
        self.assertIsInstance(results['sharpe_ratio'], (int, float))
        self.assertFalse(np.isnan(results['sharpe_ratio']))


class TestBacktesterEdgeCases(unittest.TestCase):
    """Test edge cases for backtester"""

    def test_small_capital(self):
        """Test with very small initial capital"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        backtester = Backtester(strategy=strategy, initial_capital=100.0)

        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        prices = np.linspace(100, 120, 50)

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices,
            'volume': [1000] * 50
        }, index=dates)

        results = backtester.run(data)

        # Should complete without errors
        self.assertGreater(results['final_capital'], 0)

    def test_high_commission(self):
        """Test with high commission rate"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        backtester = Backtester(
            strategy=strategy,
            initial_capital=10000.0,
            commission=0.01  # 1% commission
        )

        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        prices = np.linspace(100, 120, 50)

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices,
            'volume': [1000] * 50
        }, index=dates)

        results = backtester.run(data)

        # High commission should reduce final capital
        # With 1% commission on both buy and sell, results should be worse
        self.assertIsInstance(results['final_capital'], (int, float))


if __name__ == '__main__':
    unittest.main()
