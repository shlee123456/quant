"""
Tests for Bollinger Bands Strategy
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy


@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(42)

    # Create trending price data
    prices = [100]
    for i in range(99):
        change = np.random.normal(0, 2)
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


def test_bollinger_bands_initialization():
    """Test Bollinger Bands strategy initialization"""
    strategy = BollingerBandsStrategy(period=20, num_std=2.0)

    assert strategy.period == 20
    assert strategy.num_std == 2.0
    assert strategy.name == "BollingerBands_20_2.0"


def test_bollinger_bands_calculation(sample_data):
    """Test Bollinger Bands calculation"""
    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(sample_data)

    # Check that Bollinger Band columns exist
    assert 'bb_upper' in result.columns
    assert 'bb_middle' in result.columns
    assert 'bb_lower' in result.columns
    assert 'bb_percent_b' in result.columns

    # Upper band should always be above middle, middle above lower
    valid = result.dropna(subset=['bb_upper', 'bb_middle', 'bb_lower'])
    assert (valid['bb_upper'] >= valid['bb_middle']).all()
    assert (valid['bb_middle'] >= valid['bb_lower']).all()

    # First period-1 values should be NaN (warm-up period)
    assert result['bb_middle'].iloc[:19].isna().all()


def test_middle_band_is_sma(sample_data):
    """Test that middle band is the SMA of close prices"""
    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(sample_data)

    # Calculate SMA independently
    expected_sma = sample_data['close'].rolling(window=20).mean()

    pd.testing.assert_series_equal(
        result['bb_middle'],
        expected_sma,
        check_names=False
    )


def test_band_width_with_std(sample_data):
    """Test that bands are at correct distance from middle"""
    strategy = BollingerBandsStrategy(period=20, num_std=2.0)
    result = strategy.calculate_indicators(sample_data)

    # Calculate expected std independently
    expected_std = sample_data['close'].rolling(window=20).std()

    valid = result.dropna(subset=['bb_upper', 'bb_middle', 'bb_lower'])
    expected_std_valid = expected_std[valid.index]

    # Upper band = middle + 2 * std
    expected_upper = valid['bb_middle'] + 2.0 * expected_std_valid
    pd.testing.assert_series_equal(
        valid['bb_upper'],
        expected_upper,
        check_names=False,
        atol=1e-10
    )

    # Lower band = middle - 2 * std
    expected_lower = valid['bb_middle'] - 2.0 * expected_std_valid
    pd.testing.assert_series_equal(
        valid['bb_lower'],
        expected_lower,
        check_names=False,
        atol=1e-10
    )


def test_signal_generation(sample_data):
    """Test signal generation"""
    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(sample_data)

    # Check signal column exists
    assert 'signal' in result.columns
    assert 'position' in result.columns

    # Signals should be -1, 0, or 1
    assert result['signal'].isin([-1, 0, 1]).all()


def test_buy_signal_below_lower_band():
    """Test BUY signal when price crosses below lower band"""
    # Create data that drops sharply to cross below lower band
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')
    np.random.seed(10)

    # Stable prices followed by sharp drop
    prices = [100.0] * 30
    for i in range(30):
        prices.append(prices[-1] - 2)  # Sharp decline

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.001 for p in prices],
        'low': [p * 0.999 for p in prices],
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = BollingerBandsStrategy(period=20, num_std=2.0)
    result = strategy.calculate_indicators(df)

    # Should have at least one buy signal
    buy_signals = result[result['signal'] == 1]
    assert len(buy_signals) > 0


def test_sell_signal_above_upper_band():
    """Test SELL signal when price crosses above upper band"""
    # Create data that rises sharply to cross above upper band
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')

    # Stable prices followed by sharp rise
    prices = [100.0] * 30
    for i in range(30):
        prices.append(prices[-1] + 2)  # Sharp rise

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.001 for p in prices],
        'low': [p * 0.999 for p in prices],
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = BollingerBandsStrategy(period=20, num_std=2.0)
    result = strategy.calculate_indicators(df)

    # Should have at least one sell signal
    sell_signals = result[result['signal'] == -1]
    assert len(sell_signals) > 0


def test_get_current_signal(sample_data):
    """Test getting current signal"""
    strategy = BollingerBandsStrategy(period=20)
    signal, info = strategy.get_current_signal(sample_data)

    # Signal should be -1, 0, or 1
    assert signal in [-1, 0, 1]

    # Info should contain required fields
    assert 'close' in info
    assert 'bb_upper' in info
    assert 'bb_middle' in info
    assert 'bb_lower' in info
    assert 'bb_percent_b' in info
    assert 'signal' in info
    assert 'position' in info


def test_get_all_signals(sample_data):
    """Test getting all signals"""
    strategy = BollingerBandsStrategy(period=20)
    signals = strategy.get_all_signals(sample_data)

    # Signals should be a list
    assert isinstance(signals, list)

    # Each signal should have required fields
    if signals:
        signal = signals[0]
        assert 'timestamp' in signal
        assert 'signal' in signal
        assert 'price' in signal
        assert 'bb_upper' in signal
        assert 'bb_middle' in signal
        assert 'bb_lower' in signal
        assert 'bb_percent_b' in signal
        assert signal['signal'] in ['BUY', 'SELL']


def test_different_parameters():
    """Test strategy with different parameters"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    np.random.seed(42)
    prices = [100]
    for _ in range(99):
        prices.append(prices[-1] + np.random.normal(0, 2))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 100
    })
    df.set_index('timestamp', inplace=True)

    # Test with period=10, num_std=1.5
    strategy1 = BollingerBandsStrategy(period=10, num_std=1.5)
    result1 = strategy1.calculate_indicators(df)
    assert result1['bb_middle'].notna().sum() > 0

    # Test with period=30, num_std=2.5
    strategy2 = BollingerBandsStrategy(period=30, num_std=2.5)
    result2 = strategy2.calculate_indicators(df)
    assert result2['bb_middle'].notna().sum() > 0

    # Results should be different
    assert not result1['bb_middle'].equals(result2['bb_middle'])


def test_position_tracking(sample_data):
    """Test position tracking"""
    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(sample_data)

    # Position should be 0 or 1
    assert result['position'].isin([0, 1]).all()

    # Position should persist after signal
    for i in range(len(result) - 1):
        if result['signal'].iloc[i] == 1:  # Buy signal
            assert result['position'].iloc[i] == 1 or result['position'].iloc[i+1] == 1


def test_string_representation():
    """Test __str__ method"""
    strategy = BollingerBandsStrategy(period=20, num_std=2.0)
    string = str(strategy)

    assert 'Bollinger Bands' in string
    assert '20' in string
    assert '2.0' in string


def test_empty_dataframe():
    """Test handling of empty DataFrame"""
    strategy = BollingerBandsStrategy(period=20)
    empty_df = pd.DataFrame()

    # Should not raise an error
    result = strategy.calculate_indicators(empty_df)
    assert result.empty


def test_insufficient_data():
    """Test with data shorter than period"""
    dates = pd.date_range(start='2024-01-01', periods=10, freq='1h')
    prices = list(range(10))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 10
    })
    df.set_index('timestamp', inplace=True)

    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(df)

    # Bollinger Bands should be all NaN due to insufficient data
    assert result['bb_middle'].isna().all()


def test_percent_b_calculation(sample_data):
    """Test %B indicator calculation"""
    strategy = BollingerBandsStrategy(period=20)
    result = strategy.calculate_indicators(sample_data)

    valid = result.dropna(subset=['bb_percent_b'])

    # %B should be close to 0 when price is at lower band
    # %B should be close to 1 when price is at upper band
    # %B should be close to 0.5 when price is at middle band
    # In general, %B = (price - lower) / (upper - lower)
    expected = (valid['close'] - valid['bb_lower']) / (valid['bb_upper'] - valid['bb_lower'])
    pd.testing.assert_series_equal(
        valid['bb_percent_b'],
        expected,
        check_names=False,
        atol=1e-10
    )


def test_narrow_bands_with_small_std():
    """Test that smaller num_std produces narrower bands"""
    dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
    np.random.seed(42)
    prices = [100]
    for _ in range(49):
        prices.append(prices[-1] + np.random.normal(0, 1))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 50
    })
    df.set_index('timestamp', inplace=True)

    strategy_narrow = BollingerBandsStrategy(period=20, num_std=1.0)
    strategy_wide = BollingerBandsStrategy(period=20, num_std=3.0)

    result_narrow = strategy_narrow.calculate_indicators(df)
    result_wide = strategy_wide.calculate_indicators(df)

    valid_narrow = result_narrow.dropna(subset=['bb_upper', 'bb_lower'])
    valid_wide = result_wide.dropna(subset=['bb_upper', 'bb_lower'])

    width_narrow = (valid_narrow['bb_upper'] - valid_narrow['bb_lower']).mean()
    width_wide = (valid_wide['bb_upper'] - valid_wide['bb_lower']).mean()

    assert width_narrow < width_wide
