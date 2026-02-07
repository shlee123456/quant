"""
Tests for Stochastic Oscillator Strategy
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategies.stochastic_strategy import StochasticStrategy


@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(42)

    # Create trending price data with variation in high/low
    prices = [100]
    for i in range(99):
        change = np.random.normal(0, 2)
        prices.append(prices[-1] + change)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.02 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    return df


def test_stochastic_initialization():
    """Test Stochastic strategy initialization"""
    strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)

    assert strategy.k_period == 14
    assert strategy.d_period == 3
    assert strategy.overbought == 80
    assert strategy.oversold == 20
    assert strategy.name == "Stochastic_14_3_20_80"


def test_stochastic_calculation(sample_data):
    """Test Stochastic Oscillator calculation"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(sample_data)

    # Check that Stochastic columns exist
    assert 'stochastic_k' in result.columns
    assert 'stochastic_d' in result.columns
    assert 'lowest_low' in result.columns
    assert 'highest_high' in result.columns

    # %K should be between 0 and 100
    valid_k = result['stochastic_k'].dropna()
    assert (valid_k >= 0).all()
    assert (valid_k <= 100).all()

    # %D should also be between 0 and 100
    valid_d = result['stochastic_d'].dropna()
    assert (valid_d >= 0).all()
    assert (valid_d <= 100).all()

    # First k_period-1 values of %K should be NaN (warm-up period)
    assert result['stochastic_k'].iloc[:13].isna().all()


def test_k_line_formula(sample_data):
    """Test that %K is calculated correctly: (Close - LL) / (HH - LL) * 100"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(sample_data)

    # Calculate %K independently
    lowest_low = sample_data['low'].rolling(window=14).min()
    highest_high = sample_data['high'].rolling(window=14).max()
    expected_k = (sample_data['close'] - lowest_low) / (highest_high - lowest_low) * 100

    pd.testing.assert_series_equal(
        result['stochastic_k'],
        expected_k,
        check_names=False,
        atol=1e-10
    )


def test_d_line_is_sma_of_k(sample_data):
    """Test that %D is the SMA of %K"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(sample_data)

    # Calculate %D independently
    expected_d = result['stochastic_k'].rolling(window=3).mean()

    pd.testing.assert_series_equal(
        result['stochastic_d'],
        expected_d,
        check_names=False,
        atol=1e-10
    )


def test_signal_generation(sample_data):
    """Test signal generation"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(sample_data)

    # Check signal column exists
    assert 'signal' in result.columns
    assert 'position' in result.columns

    # Signals should be -1, 0, or 1
    assert result['signal'].isin([-1, 0, 1]).all()


def test_buy_signal_oversold_crossover():
    """Test BUY signal when %K crosses above %D in oversold zone"""
    # Create data that produces oversold condition with crossover
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')
    np.random.seed(10)

    # Create price pattern that will result in oversold Stochastic
    # Start high then drop, then recover slightly
    prices = [100.0] * 15
    for i in range(20):
        prices.append(prices[-1] - 3)  # Sharp decline
    for i in range(25):
        prices.append(prices[-1] + 1.5)  # Gradual recovery

    highs = [p * 1.02 for p in prices]
    lows = [p * 0.98 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
    result = strategy.calculate_indicators(df)

    # Should have at least one buy signal in oversold region
    buy_signals = result[result['signal'] == 1]
    assert len(buy_signals) > 0

    # Verify buy signals are in oversold zone
    for idx in buy_signals.index:
        k_value = result.loc[idx, 'stochastic_k']
        assert k_value < 20  # Should be oversold


def test_sell_signal_overbought_crossover():
    """Test SELL signal when %K crosses below %D in overbought zone"""
    # Create data that produces overbought condition with crossover
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')

    # Create price pattern that will result in overbought Stochastic
    # Start low then rise, then drop slightly
    prices = [100.0] * 15
    for i in range(20):
        prices.append(prices[-1] + 3)  # Sharp rise
    for i in range(25):
        prices.append(prices[-1] - 1.5)  # Gradual decline

    highs = [p * 1.02 for p in prices]
    lows = [p * 0.98 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
    result = strategy.calculate_indicators(df)

    # Should have at least one sell signal in overbought region
    sell_signals = result[result['signal'] == -1]
    assert len(sell_signals) > 0

    # Verify sell signals are in overbought zone
    for idx in sell_signals.index:
        k_value = result.loc[idx, 'stochastic_k']
        assert k_value > 80  # Should be overbought


def test_get_current_signal(sample_data):
    """Test getting current signal"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    signal, info = strategy.get_current_signal(sample_data)

    # Signal should be -1, 0, or 1
    assert signal in [-1, 0, 1]

    # Info should contain required fields
    assert 'close' in info
    assert 'stochastic_k' in info
    assert 'stochastic_d' in info
    assert 'signal' in info
    assert 'position' in info
    assert 'overbought_level' in info
    assert 'oversold_level' in info


def test_get_all_signals(sample_data):
    """Test getting all signals"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    signals = strategy.get_all_signals(sample_data)

    # Signals should be a list
    assert isinstance(signals, list)

    # Each signal should have required fields
    if signals:
        signal = signals[0]
        assert 'timestamp' in signal
        assert 'signal' in signal
        assert 'price' in signal
        assert 'stochastic_k' in signal
        assert 'stochastic_d' in signal
        assert signal['signal'] in ['BUY', 'SELL']


def test_different_parameters():
    """Test strategy with different parameters"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(42)
    prices = [100]
    for _ in range(99):
        prices.append(prices[-1] + np.random.normal(0, 2))

    highs = [p * 1.02 for p in prices]
    lows = [p * 0.98 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    # Test with k_period=5, d_period=3
    strategy1 = StochasticStrategy(k_period=5, d_period=3)
    result1 = strategy1.calculate_indicators(df)
    assert result1['stochastic_k'].notna().sum() > 0

    # Test with k_period=21, d_period=5
    strategy2 = StochasticStrategy(k_period=21, d_period=5)
    result2 = strategy2.calculate_indicators(df)
    assert result2['stochastic_k'].notna().sum() > 0

    # Results should be different
    assert not result1['stochastic_k'].equals(result2['stochastic_k'])


def test_position_tracking(sample_data):
    """Test position tracking"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(sample_data)

    # Position should be 0 or 1
    assert result['position'].isin([0, 1]).all()

    # Position should persist after signal
    for i in range(len(result) - 1):
        if result['signal'].iloc[i] == 1:  # Buy signal
            assert result['position'].iloc[i] == 1 or result['position'].iloc[i+1] == 1


def test_string_representation():
    """Test __str__ method"""
    strategy = StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
    string = str(strategy)

    assert 'Stochastic' in string
    assert '14' in string
    assert '3' in string
    assert '80' in string
    assert '20' in string


def test_empty_dataframe():
    """Test handling of empty DataFrame"""
    strategy = StochasticStrategy(k_period=14, d_period=3)
    empty_df = pd.DataFrame()

    # Should not raise an error
    result = strategy.calculate_indicators(empty_df)
    assert result.empty


def test_insufficient_data():
    """Test with data shorter than k_period"""
    dates = pd.date_range(start='2024-01-01', periods=10, freq='1h')
    prices = list(range(10))
    highs = [p * 1.02 for p in prices]
    lows = [p * 0.98 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 10
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(df)

    # Stochastic should be all NaN due to insufficient data
    assert result['stochastic_k'].isna().all()


def test_extreme_values():
    """Test with extreme price values at bounds"""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='1h')

    # Create scenario where close equals highest high (should give %K = 100)
    prices = [100] * 15 + [150] * 15
    highs = [p * 1.0 for p in prices]  # High = Close
    lows = [90] * 30  # Constant low

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 30
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(df)

    # When close = highest_high, %K should be 100
    last_k = result['stochastic_k'].iloc[-1]
    assert abs(last_k - 100) < 0.01


def test_zero_range_handling():
    """Test handling when highest_high equals lowest_low"""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='1h')

    # Constant prices (no range)
    prices = [100.0] * 30
    highs = [100.0] * 30
    lows = [100.0] * 30

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 30
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(df)

    # When range is 0, result will be inf or NaN (division by zero)
    # Just verify it doesn't crash
    assert 'stochastic_k' in result.columns


def test_crossover_detection():
    """Test that crossover detection works correctly"""
    dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
    np.random.seed(99)

    # Create controlled price movement
    prices = [100]
    for _ in range(49):
        prices.append(prices[-1] + np.random.normal(0, 3))

    highs = [p * 1.03 for p in prices]
    lows = [p * 0.97 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 50
    })
    df.set_index('timestamp', inplace=True)

    strategy = StochasticStrategy(k_period=14, d_period=3)
    result = strategy.calculate_indicators(df)

    # Verify that signals only occur on actual crossovers
    buy_signals = result[result['signal'] == 1]
    for idx in buy_signals.index:
        idx_pos = result.index.get_loc(idx)
        if idx_pos > 0:
            prev_idx = result.index[idx_pos - 1]
            # At signal: k > d, previously: k <= d
            assert result.loc[idx, 'stochastic_k'] > result.loc[idx, 'stochastic_d']
            assert result.loc[prev_idx, 'stochastic_k'] <= result.loc[prev_idx, 'stochastic_d']


def test_custom_overbought_oversold_levels():
    """Test with custom overbought/oversold levels"""
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')
    np.random.seed(42)

    prices = [100]
    for _ in range(59):
        prices.append(prices[-1] + np.random.normal(0, 3))

    highs = [p * 1.02 for p in prices]
    lows = [p * 0.98 for p in prices]

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    # Use custom levels
    strategy = StochasticStrategy(k_period=14, d_period=3, overbought=70, oversold=30)
    result = strategy.calculate_indicators(df)

    # Verify signals respect custom levels
    buy_signals = result[result['signal'] == 1]
    for idx in buy_signals.index:
        assert result.loc[idx, 'stochastic_k'] < 30

    sell_signals = result[result['signal'] == -1]
    for idx in sell_signals.index:
        assert result.loc[idx, 'stochastic_k'] > 70
