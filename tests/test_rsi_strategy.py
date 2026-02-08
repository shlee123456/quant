"""
Tests for RSI Strategy
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.strategies.rsi_strategy import RSIStrategy


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


def test_rsi_initialization():
    """Test RSI strategy initialization"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)

    assert strategy.period == 14
    assert strategy.overbought == 70
    assert strategy.oversold == 30
    assert strategy.name == "RSI_14_30_70"


def test_rsi_calculation(sample_data):
    """Test RSI calculation"""
    strategy = RSIStrategy(period=14)
    result = strategy.calculate_indicators(sample_data)

    # Check that RSI column exists
    assert 'rsi' in result.columns

    # RSI should be between 0 and 100
    valid_rsi = result['rsi'].dropna()
    assert (valid_rsi >= 0).all()
    assert (valid_rsi <= 100).all()

    # First 14 values should be NaN (warm-up period)
    assert result['rsi'].iloc[:14].isna().all()


def test_signal_generation(sample_data):
    """Test signal generation"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    result = strategy.calculate_indicators(sample_data)

    # Check signal column exists
    assert 'signal' in result.columns
    assert 'position' in result.columns

    # Signals should be -1, 0, or 1
    assert result['signal'].isin([-1, 0, 1]).all()


def test_oversold_signal():
    """Test BUY signal generation when RSI is oversold"""
    # Create data that will produce RSI crossover from oversold
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')

    # Pattern: sideways -> sharp decline -> recovery (to create oversold crossover)
    prices = [100.0 + i * 0.1 for i in range(15)]  # Slight upward trend (15 elements)
    # Sharp decline to create oversold condition
    current_price = prices[-1]
    for _ in range(20):  # Decline (20 elements)
        current_price -= 2.0
        prices.append(current_price)
    # Recovery to create crossover back above oversold
    for _ in range(25):  # Recovery (25 elements) - total 60
        current_price += 1.0
        prices.append(current_price)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    result = strategy.calculate_indicators(df)

    # Should have at least one buy signal
    buy_signals = result[result['signal'] == 1]
    assert len(buy_signals) > 0


def test_overbought_signal():
    """Test SELL signal generation when RSI is overbought"""
    # Create data that will produce RSI crossover from overbought
    dates = pd.date_range(start='2024-01-01', periods=60, freq='1h')

    # Pattern: sideways -> sharp rise -> decline (to create overbought crossover)
    prices = [50.0 - i * 0.1 for i in range(15)]  # Slight downward trend (15 elements)
    # Sharp rise to create overbought condition
    current_price = prices[-1]
    for _ in range(20):  # Rise (20 elements)
        current_price += 2.0
        prices.append(current_price)
    # Decline to create crossover back below overbought
    for _ in range(25):  # Decline (25 elements) - total 60
        current_price -= 1.0
        prices.append(current_price)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [1000] * 60
    })
    df.set_index('timestamp', inplace=True)

    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    result = strategy.calculate_indicators(df)

    # Should have at least one sell signal
    sell_signals = result[result['signal'] == -1]
    assert len(sell_signals) > 0


def test_get_current_signal(sample_data):
    """Test getting current signal"""
    strategy = RSIStrategy(period=14)
    signal, info = strategy.get_current_signal(sample_data)

    # Signal should be -1, 0, or 1
    assert signal in [-1, 0, 1]

    # Info should contain required fields
    assert 'close' in info
    assert 'rsi' in info
    assert 'signal' in info
    assert 'position' in info


def test_get_all_signals(sample_data):
    """Test getting all signals"""
    strategy = RSIStrategy(period=14)
    signals = strategy.get_all_signals(sample_data)

    # Signals should be a list
    assert isinstance(signals, list)

    # Each signal should have required fields
    if signals:
        signal = signals[0]
        assert 'timestamp' in signal
        assert 'signal' in signal
        assert 'price' in signal
        assert 'rsi' in signal
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

    # Test with period=7
    strategy1 = RSIStrategy(period=7, overbought=70, oversold=30)
    result1 = strategy1.calculate_indicators(df)
    assert result1['rsi'].notna().sum() > 0

    # Test with period=21
    strategy2 = RSIStrategy(period=21, overbought=80, oversold=20)
    result2 = strategy2.calculate_indicators(df)
    assert result2['rsi'].notna().sum() > 0

    # Results should be different
    assert not result1['rsi'].equals(result2['rsi'])


def test_position_tracking(sample_data):
    """Test position tracking"""
    strategy = RSIStrategy(period=14)
    result = strategy.calculate_indicators(sample_data)

    # Position should be 0 or 1
    assert result['position'].isin([0, 1]).all()

    # Position should persist after signal
    for i in range(len(result) - 1):
        if result['signal'].iloc[i] == 1:  # Buy signal
            # Next position should be 1
            assert result['position'].iloc[i] == 1 or result['position'].iloc[i+1] == 1


def test_string_representation():
    """Test __str__ method"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    string = str(strategy)

    assert 'RSI' in string
    assert '14' in string
    assert '70' in string
    assert '30' in string


def test_empty_dataframe():
    """Test handling of empty DataFrame"""
    strategy = RSIStrategy(period=14)
    empty_df = pd.DataFrame()

    # Should not raise an error
    result = strategy.calculate_indicators(empty_df)
    assert result.empty


def test_insufficient_data():
    """Test with data shorter than RSI period"""
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

    strategy = RSIStrategy(period=14)
    result = strategy.calculate_indicators(df)

    # RSI should be all NaN due to insufficient data
    assert result['rsi'].isna().all()
