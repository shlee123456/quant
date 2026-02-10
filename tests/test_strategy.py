"""
Unit tests for trading strategy
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


class TestMovingAverageCrossover(unittest.TestCase):
    """Test cases for Moving Average Crossover strategy"""

    def setUp(self):
        """Set up test fixtures"""
        self.strategy = MovingAverageCrossover(fast_period=5, slow_period=10)

        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
        prices = np.linspace(100, 150, 50) + np.random.randn(50) * 2

        self.sample_data = pd.DataFrame({
            'open': prices,
            'high': prices + 2,
            'low': prices - 2,
            'close': prices,
            'volume': np.random.randint(1000, 10000, 50)
        }, index=dates)

    def test_initialization(self):
        """Test strategy initialization"""
        self.assertEqual(self.strategy.fast_period, 5)
        self.assertEqual(self.strategy.slow_period, 10)
        self.assertEqual(self.strategy.name, "MA_Crossover_5_10")

    def test_calculate_indicators(self):
        """Test indicator calculation"""
        result = self.strategy.calculate_indicators(self.sample_data)

        # Check that indicators are calculated
        self.assertIn('fast_ma', result.columns)
        self.assertIn('slow_ma', result.columns)
        self.assertIn('signal', result.columns)
        self.assertIn('position', result.columns)

        # Check that MAs are calculated correctly
        self.assertFalse(result['fast_ma'].isna().all())
        self.assertFalse(result['slow_ma'].isna().all())

        # Check signal values are valid
        self.assertTrue(result['signal'].isin([0, 1, -1]).all())

    def test_moving_averages(self):
        """Test moving average calculations"""
        result = self.strategy.calculate_indicators(self.sample_data)

        # Verify fast MA is indeed faster than slow MA
        fast_ma_last = result['fast_ma'].iloc[-10:].mean()
        slow_ma_last = result['slow_ma'].iloc[-10:].mean()

        # Both should be positive numbers
        self.assertGreater(fast_ma_last, 0)
        self.assertGreater(slow_ma_last, 0)

    def test_buy_signal_generation(self):
        """Test buy signal generation"""
        # Create data with decline then uptrend to trigger MA crossover
        dates = pd.date_range(start='2024-01-01', periods=30, freq='1h')
        prices = np.concatenate([
            np.linspace(120, 100, 12),  # Downtrend (fast MA goes below slow MA)
            np.linspace(100, 130, 18)   # Strong uptrend (fast MA crosses above slow MA)
        ])

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices,
            'volume': [1000] * 30
        }, index=dates)

        result = self.strategy.calculate_indicators(data)

        # Should have at least one buy signal
        buy_signals = result[result['signal'] == 1]
        self.assertGreater(len(buy_signals), 0)

    def test_sell_signal_generation(self):
        """Test sell signal generation"""
        # Create data with uptrend then downtrend
        dates = pd.date_range(start='2024-01-01', periods=30, freq='1h')
        prices = np.concatenate([
            np.linspace(100, 120, 15),  # Uptrend
            np.linspace(120, 100, 15)   # Downtrend
        ])

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices,
            'volume': [1000] * 30
        }, index=dates)

        result = self.strategy.calculate_indicators(data)

        # Should have at least one sell signal
        sell_signals = result[result['signal'] == -1]
        self.assertGreater(len(sell_signals), 0)

    def test_get_current_signal(self):
        """Test getting current signal"""
        signal, info = self.strategy.get_current_signal(self.sample_data)

        # Check signal is valid
        self.assertIn(signal, [0, 1, -1])

        # Check info dict has required keys
        required_keys = ['timestamp', 'close', 'fast_ma', 'slow_ma', 'signal', 'position']
        for key in required_keys:
            self.assertIn(key, info)

    def test_get_all_signals(self):
        """Test getting all signals"""
        signals = self.strategy.get_all_signals(self.sample_data)

        # Signals should be a list
        self.assertIsInstance(signals, list)

        # Each signal should have required fields
        if signals:
            required_keys = ['timestamp', 'signal', 'price', 'fast_ma', 'slow_ma']
            for signal in signals:
                for key in required_keys:
                    self.assertIn(key, signal)

                # Signal should be BUY or SELL
                self.assertIn(signal['signal'], ['BUY', 'SELL'])

    def test_empty_data(self):
        """Test handling of empty data"""
        empty_data = pd.DataFrame()
        signal, info = self.strategy.get_current_signal(empty_data)

        self.assertEqual(signal, 0)
        self.assertEqual(info, {})

    def test_insufficient_data(self):
        """Test handling of insufficient data for MAs"""
        # Only 5 data points, less than slow_ma period
        dates = pd.date_range(start='2024-01-01', periods=5, freq='1h')
        data = pd.DataFrame({
            'open': [100, 101, 102, 103, 104],
            'high': [101, 102, 103, 104, 105],
            'low': [99, 100, 101, 102, 103],
            'close': [100, 101, 102, 103, 104],
            'volume': [1000] * 5
        }, index=dates)

        result = self.strategy.calculate_indicators(data)

        # Should still return a DataFrame
        self.assertIsInstance(result, pd.DataFrame)

        # Fast MA should have some values
        self.assertFalse(result['fast_ma'].isna().all())


class TestStrategyEdgeCases(unittest.TestCase):
    """Test edge cases for strategy"""

    def test_flat_market(self):
        """Test strategy in flat market"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)

        # Create flat market data
        dates = pd.date_range(start='2024-01-01', periods=30, freq='1h')
        prices = [100] * 30 + np.random.randn(30) * 0.5  # Almost flat

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 0.5,
            'low': prices - 0.5,
            'close': prices,
            'volume': [1000] * 30
        }, index=dates)

        result = strategy.calculate_indicators(data)

        # In flat market, should have minimal signals
        total_signals = len(result[result['signal'] != 0])
        self.assertLess(total_signals, 5)

    def test_different_ma_periods(self):
        """Test different MA period combinations"""
        test_cases = [
            (5, 20),
            (10, 30),
            (20, 50),
        ]

        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        prices = np.linspace(100, 150, 100)

        data = pd.DataFrame({
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices,
            'volume': [1000] * 100
        }, index=dates)

        for fast, slow in test_cases:
            with self.subTest(fast=fast, slow=slow):
                strategy = MovingAverageCrossover(fast_period=fast, slow_period=slow)
                result = strategy.calculate_indicators(data)

                # Should calculate without errors
                self.assertIn('fast_ma', result.columns)
                self.assertIn('slow_ma', result.columns)


if __name__ == '__main__':
    unittest.main()
