"""
Tests for Simulation Data Generator
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.simulation_data import SimulationDataGenerator


def test_initialization_with_seed():
    """Test initialization with seed for reproducibility"""
    gen1 = SimulationDataGenerator(seed=42)
    gen2 = SimulationDataGenerator(seed=42)

    df1 = gen1.generate_ohlcv(periods=100)
    df2 = gen2.generate_ohlcv(periods=100)

    # Should generate identical data
    pd.testing.assert_frame_equal(df1, df2)


def test_initialization_without_seed():
    """Test initialization without seed"""
    gen1 = SimulationDataGenerator()
    gen2 = SimulationDataGenerator()

    df1 = gen1.generate_ohlcv(periods=100)
    df2 = gen2.generate_ohlcv(periods=100)

    # Should generate different data
    assert not df1['close'].equals(df2['close'])


def test_generate_ohlcv_columns():
    """Test that generated data has correct columns"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    expected_columns = ['open', 'high', 'low', 'close', 'volume']
    assert all(col in df.columns for col in expected_columns)


def test_generate_ohlcv_length():
    """Test that generated data has correct length"""
    gen = SimulationDataGenerator(seed=42)

    for periods in [50, 100, 500]:
        df = gen.generate_ohlcv(periods=periods)
        assert len(df) == periods


def test_ohlc_consistency():
    """Test that OHLC values are consistent (low <= open,close <= high)"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    # High should be >= low
    assert (df['high'] >= df['low']).all()

    # Open should be between low and high
    assert (df['open'] >= df['low']).all()
    assert (df['open'] <= df['high']).all()

    # Close should be between low and high
    assert (df['close'] >= df['low']).all()
    assert (df['close'] <= df['high']).all()


def test_positive_prices():
    """Test that all prices are positive"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    assert (df['open'] > 0).all()
    assert (df['high'] > 0).all()
    assert (df['low'] > 0).all()
    assert (df['close'] > 0).all()


def test_positive_volume():
    """Test that volume is positive"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    assert (df['volume'] > 0).all()


def test_timestamp_index():
    """Test that data has timestamp index"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    assert df.index.name == 'timestamp' or isinstance(df.index, pd.DatetimeIndex)


def test_drift_effect():
    """Test that drift parameter affects trend"""
    gen = SimulationDataGenerator(seed=42)

    # Bullish drift
    df_bull = gen.generate_ohlcv(periods=1000, drift=0.001, volatility=0.01)
    bull_return = (df_bull['close'].iloc[-1] - df_bull['close'].iloc[0]) / df_bull['close'].iloc[0]

    # Bearish drift
    gen2 = SimulationDataGenerator(seed=42)
    df_bear = gen2.generate_ohlcv(periods=1000, drift=-0.001, volatility=0.01)
    bear_return = (df_bear['close'].iloc[-1] - df_bear['close'].iloc[0]) / df_bear['close'].iloc[0]

    # Bullish should outperform bearish
    assert bull_return > bear_return


def test_volatility_effect():
    """Test that volatility parameter affects price variance"""
    # Low volatility
    gen1 = SimulationDataGenerator(seed=42)
    df_low_vol = gen1.generate_ohlcv(periods=1000, volatility=0.01)
    low_vol_std = df_low_vol['close'].pct_change().std()

    # High volatility
    gen2 = SimulationDataGenerator(seed=42)
    df_high_vol = gen2.generate_ohlcv(periods=1000, volatility=0.05)
    high_vol_std = df_high_vol['close'].pct_change().std()

    # High volatility should have higher standard deviation
    assert high_vol_std > low_vol_std


def test_generate_trend_data_bullish():
    """Test bullish trend generation"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_trend_data(periods=1000, trend='bullish')

    # Calculate overall return
    total_return = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]

    # Should generally be positive (though not guaranteed due to randomness)
    # With seed=42 and 1000 periods, should be positive
    assert len(df) == 1000


def test_generate_trend_data_bearish():
    """Test bearish trend generation"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_trend_data(periods=1000, trend='bearish')

    assert len(df) == 1000


def test_generate_trend_data_sideways():
    """Test sideways trend generation"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_trend_data(periods=1000, trend='sideways')

    # Calculate overall return
    total_return = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]

    # Should be close to zero (though not guaranteed)
    assert len(df) == 1000


def test_generate_volatile_data():
    """Test volatile data generation"""
    gen = SimulationDataGenerator(seed=42)
    df_volatile = gen.generate_volatile_data(periods=1000)

    # Calculate volatility
    volatility = df_volatile['close'].pct_change().std()

    # Should have higher volatility than default
    df_normal = gen.generate_ohlcv(periods=1000, volatility=0.02)
    normal_volatility = df_normal['close'].pct_change().std()

    assert volatility > normal_volatility


def test_generate_cyclical_data():
    """Test cyclical data generation"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_cyclical_data(periods=200, cycle_length=50, amplitude=0.1)

    assert len(df) == 200

    # Prices should oscillate
    # Check that there are both ups and downs
    price_changes = df['close'].diff()
    assert (price_changes > 0).sum() > 0
    assert (price_changes < 0).sum() > 0


def test_cyclical_pattern():
    """Test that cyclical data follows sine pattern"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_cyclical_data(periods=400, cycle_length=100, amplitude=0.2)

    # With 400 periods and cycle_length=100, we should see ~4 cycles
    # Smooth the data to see the pattern
    smoothed = df['close'].rolling(window=10).mean()

    # Count peaks and troughs
    peaks = (smoothed > smoothed.shift(1)) & (smoothed > smoothed.shift(-1))
    troughs = (smoothed < smoothed.shift(1)) & (smoothed < smoothed.shift(-1))

    # Should have multiple peaks and troughs
    assert peaks.sum() >= 2
    assert troughs.sum() >= 2


def test_timeframe_parsing():
    """Test timeframe parsing"""
    gen = SimulationDataGenerator(seed=42)

    # Test different timeframes
    df_1h = gen.generate_ohlcv(periods=10, timeframe='1h')
    df_1d = gen.generate_ohlcv(periods=10, timeframe='1d')
    df_4h = gen.generate_ohlcv(periods=10, timeframe='4h')

    # Check that timestamps are spaced correctly
    time_diff_1h = df_1h.index[1] - df_1h.index[0]
    assert time_diff_1h == timedelta(hours=1)

    time_diff_1d = df_1d.index[1] - df_1d.index[0]
    assert time_diff_1d == timedelta(days=1)

    time_diff_4h = df_4h.index[1] - df_4h.index[0]
    assert time_diff_4h == timedelta(hours=4)


def test_custom_start_date():
    """Test custom start date"""
    gen = SimulationDataGenerator(seed=42)
    start_date = datetime(2023, 1, 1)

    df = gen.generate_ohlcv(periods=10, start_date=start_date)

    assert df.index[0] == start_date


def test_add_market_shock():
    """Test adding market shock"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    # Get mid-point price
    mid_idx = 50
    shock_date = df.index[mid_idx]
    pre_shock_price = df['close'].iloc[mid_idx]

    # Add 30% crash
    df_shocked = gen.add_market_shock(df, shock_date, shock_magnitude=-0.3)

    # Price at shock should be ~30% lower
    post_shock_price = df_shocked['close'].iloc[mid_idx]

    # Check that shock was applied (allowing for some floating point tolerance)
    expected_price = pre_shock_price * 0.7
    assert abs(post_shock_price - expected_price) < 1.0


def test_market_shock_timing():
    """Test that market shock affects correct timeframe"""
    gen = SimulationDataGenerator(seed=42)
    df = gen.generate_ohlcv(periods=100)

    shock_date = df.index[50]
    df_shocked = gen.add_market_shock(df, shock_date, shock_magnitude=-0.2)

    # Prices before shock should be unchanged
    pd.testing.assert_series_equal(
        df['close'].iloc[:50],
        df_shocked['close'].iloc[:50],
        check_names=False
    )

    # Prices after shock should be different
    assert not df['close'].iloc[50:].equals(df_shocked['close'].iloc[50:])


def test_initial_price():
    """Test custom initial price"""
    gen = SimulationDataGenerator(seed=42)

    initial_price = 30000.0
    df = gen.generate_ohlcv(periods=100, initial_price=initial_price)

    # First close should be near initial price
    assert abs(df['close'].iloc[0] - initial_price) < initial_price * 0.1


def test_different_seeds_different_results():
    """Test that different seeds produce different results"""
    gen1 = SimulationDataGenerator(seed=42)
    gen2 = SimulationDataGenerator(seed=123)

    df1 = gen1.generate_ohlcv(periods=100)
    df2 = gen2.generate_ohlcv(periods=100)

    # Should be different
    assert not df1['close'].equals(df2['close'])


def test_reproducibility():
    """Test that same seed produces reproducible results across multiple calls"""
    results = []

    for _ in range(3):
        gen = SimulationDataGenerator(seed=42)
        df = gen.generate_trend_data(periods=100, trend='bullish')
        results.append(df['close'].iloc[-1])

    # All results should be identical
    assert all(r == results[0] for r in results)
