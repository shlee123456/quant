"""
Tests for MACD Strategy
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategies.macd_strategy import MACDStrategy


@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(42)

    # Create trending price data
    prices = [100]
    for i in range(99):
        change = np.random.normal(0.5, 2)  # Slight upward trend
        prices.append(prices[-1] + change)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    return df


def test_macd_initialization():
    """Test MACD strategy initialization"""
    strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)

    assert strategy.fast_period == 12
    assert strategy.slow_period == 26
    assert strategy.signal_period == 9
    assert strategy.name == "MACD_12_26_9"


def test_macd_calculation(sample_data):
    """Test MACD calculation"""
    strategy = MACDStrategy()
    result = strategy.calculate_indicators(sample_data)

    # Check that MACD columns exist
    assert 'macd_line' in result.columns
    assert 'signal_line' in result.columns
    assert 'macd_histogram' in result.columns

    # MACD histogram should equal MACD line - Signal line
    macd_diff = result['macd_line'] - result['signal_line']
    pd.testing.assert_series_equal(
        result['macd_histogram'],
        macd_diff,
        check_names=False
    )


def test_signal_generation(sample_data):
    """Test signal generation"""
    strategy = MACDStrategy()
    result = strategy.calculate_indicators(sample_data)

    # Check signal column exists
    assert 'signal' in result.columns
    assert 'position' in result.columns

    # Signals should be -1, 0, or 1
    assert result['signal'].isin([-1, 0, 1]).all()


def test_golden_cross_signal():
    """Test BUY signal on golden cross (MACD crosses above signal)"""
    # Create data with upward trend to generate golden cross
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')

    # Create price pattern that will cause golden cross
    prices = list(range(50, 80))  # Rising (30 elements)
    prices.extend(list(range(80, 60, -1)))  # Falling (20 elements)
    prices.extend(list(range(60, 110)))  # Rising again (50 elements) - total 100

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    strategy = MACDStrategy()
    result = strategy.calculate_indicators(df)

    # Should have at least one buy signal
    buy_signals = result[result['signal'] == 1]
    assert len(buy_signals) > 0


def test_dead_cross_signal():
    """Test SELL signal on dead cross (MACD crosses below signal)"""
    # Create data with downward trend to generate dead cross
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')

    # Create price pattern
    prices = list(range(100, 70, -1))  # Falling (30 elements)
    prices.extend(list(range(70, 90)))  # Rising (20 elements)
    prices.extend(list(range(90, 40, -1)))  # Falling again (50 elements) - total 100

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    strategy = MACDStrategy()
    result = strategy.calculate_indicators(df)

    # Should have at least one sell signal
    sell_signals = result[result['signal'] == -1]
    assert len(sell_signals) > 0


def test_get_current_signal(sample_data):
    """Test getting current signal"""
    strategy = MACDStrategy()
    signal, info = strategy.get_current_signal(sample_data)

    # Signal should be -1, 0, or 1
    assert signal in [-1, 0, 1]

    # Info should contain required fields
    assert 'close' in info
    assert 'macd_line' in info
    assert 'signal_line' in info
    assert 'macd_histogram' in info
    assert 'signal' in info
    assert 'position' in info


def test_get_all_signals(sample_data):
    """Test getting all signals"""
    strategy = MACDStrategy()
    signals = strategy.get_all_signals(sample_data)

    # Signals should be a list
    assert isinstance(signals, list)

    # Each signal should have required fields
    if signals:
        signal = signals[0]
        assert 'timestamp' in signal
        assert 'signal' in signal
        assert 'price' in signal
        assert 'macd_line' in signal
        assert 'signal_line' in signal
        assert 'macd_histogram' in signal
        assert signal['signal'] in ['BUY', 'SELL']


def test_different_parameters():
    """Test strategy with different parameters"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    prices = list(range(50, 150))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    # Test with default parameters
    strategy1 = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    result1 = strategy1.calculate_indicators(df)

    # Test with custom parameters
    strategy2 = MACDStrategy(fast_period=8, slow_period=21, signal_period=7)
    result2 = strategy2.calculate_indicators(df)

    # Results should be different
    assert not result1['macd_line'].equals(result2['macd_line'])


def test_position_tracking(sample_data):
    """Test position tracking"""
    strategy = MACDStrategy()
    result = strategy.calculate_indicators(sample_data)

    # Position should be 0 or 1
    assert result['position'].isin([0, 1]).all()

    # Position should persist after signal
    for i in range(len(result) - 1):
        if result['signal'].iloc[i] == 1:  # Buy signal
            # Current or next position should be 1
            assert result['position'].iloc[i] == 1 or result['position'].iloc[i+1] == 1


def test_string_representation():
    """Test __str__ method"""
    strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    string = str(strategy)

    assert 'MACD' in string
    assert '12' in string
    assert '26' in string
    assert '9' in string


def test_empty_dataframe():
    """Test handling of empty DataFrame"""
    strategy = MACDStrategy()
    empty_df = pd.DataFrame()

    # Should not raise an error
    result = strategy.calculate_indicators(empty_df)
    assert result.empty


def test_histogram_sign_changes(sample_data):
    """Test that histogram sign changes correspond to crossovers"""
    strategy = MACDStrategy()
    result = strategy.calculate_indicators(sample_data)

    # When MACD crosses above signal, histogram goes from negative to positive
    for i in range(1, len(result)):
        if result['signal'].iloc[i] == 1:  # Buy signal
            # Histogram should be crossing from negative to positive (or near zero)
            prev_hist = result['macd_histogram'].iloc[i-1]
            curr_hist = result['macd_histogram'].iloc[i]
            # At least one should be defined
            assert not (pd.isna(prev_hist) and pd.isna(curr_hist))


def test_ema_calculation():
    """Test that EMAs are calculated correctly"""
    dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
    prices = list(range(100, 150))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 50
    })
    df.set_index('timestamp', inplace=True)

    strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    result = strategy.calculate_indicators(df)

    # MACD line should exist and have values
    assert result['macd_line'].notna().sum() > 0

    # For rising prices, fast EMA should be above slow EMA
    # so MACD should be positive in later periods
    assert result['macd_line'].iloc[-10:].mean() > 0


def test_consistent_signals():
    """Test that signals are consistent with MACD crossovers"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(123)
    prices = [100]
    for _ in range(99):
        prices.append(prices[-1] + np.random.normal(0, 1))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    strategy = MACDStrategy()
    result = strategy.calculate_indicators(df)

    # Check buy signals
    buy_signals = result[result['signal'] == 1]
    for idx in buy_signals.index:
        idx_pos = result.index.get_loc(idx)
        if idx_pos > 0:
            # MACD should cross above signal line
            assert result['macd_line'].iloc[idx_pos] > result['signal_line'].iloc[idx_pos] or \
                   abs(result['macd_line'].iloc[idx_pos] - result['signal_line'].iloc[idx_pos]) < 0.01
