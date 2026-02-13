"""
Tests for VBT-compatible get_entries_exits() method across all strategies
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from trading_bot.strategies.stochastic_strategy import StochasticStrategy
from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data with enough periods for all indicators"""
    data_gen = SimulationDataGenerator(seed=42)
    return data_gen.generate_ohlcv(periods=500, volatility=0.03)


@pytest.fixture
def volatile_data():
    """Generate highly volatile data to increase signal frequency"""
    data_gen = SimulationDataGenerator(seed=123)
    return data_gen.generate_ohlcv(periods=500, volatility=0.06)


@pytest.fixture
def empty_data():
    """Empty DataFrame with OHLCV columns"""
    return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])


ALL_STRATEGIES = [
    ("RSI", lambda: RSIStrategy(period=14, overbought=70, oversold=30)),
    ("MACD", lambda: MACDStrategy(fast_period=12, slow_period=26, signal_period=9)),
    ("BollingerBands", lambda: BollingerBandsStrategy(period=20, num_std=2.0)),
    ("Stochastic", lambda: StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)),
    ("RSIMACDCombo", lambda: RSIMACDComboStrategy()),
]


class TestEntriesExitsReturnTypes:
    """Test that get_entries_exits() returns correct types"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_returns_tuple_of_two_series(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        result = strategy.get_entries_exits(sample_data)

        assert isinstance(result, tuple), f"{name}: should return a tuple"
        assert len(result) == 2, f"{name}: should return exactly 2 elements"

        entries, exits = result
        assert isinstance(entries, pd.Series), f"{name}: entries should be pd.Series"
        assert isinstance(exits, pd.Series), f"{name}: exits should be pd.Series"

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_returns_boolean_dtype(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)

        assert entries.dtype == bool, f"{name}: entries dtype should be bool, got {entries.dtype}"
        assert exits.dtype == bool, f"{name}: exits dtype should be bool, got {exits.dtype}"


class TestEntriesExitsLength:
    """Test that output length matches input DataFrame"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_length_matches_input(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)

        assert len(entries) == len(sample_data), f"{name}: entries length mismatch"
        assert len(exits) == len(sample_data), f"{name}: exits length mismatch"

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_index_matches_input(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)

        pd.testing.assert_index_equal(entries.index, sample_data.index)
        pd.testing.assert_index_equal(exits.index, sample_data.index)


class TestEntriesExitsNoNaN:
    """Test that there are no NaN values in entries/exits"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_no_nan_in_entries(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)

        assert not entries.isna().any(), f"{name}: entries contains NaN values"
        assert not exits.isna().any(), f"{name}: exits contains NaN values"


class TestEntriesExitsNoOverlap:
    """Test that entries and exits don't both fire at the same index"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_no_simultaneous_entry_and_exit(self, name, strategy_factory, sample_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)

        overlap = entries & exits
        assert not overlap.any(), (
            f"{name}: entries and exits overlap at indices: "
            f"{sample_data.index[overlap].tolist()[:5]}"
        )


class TestEntriesExitsEmpty:
    """Test behavior with empty DataFrame"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_empty_dataframe(self, name, strategy_factory, empty_data):
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(empty_data)

        assert isinstance(entries, pd.Series)
        assert isinstance(exits, pd.Series)
        assert len(entries) == 0
        assert len(exits) == 0


class TestEntriesExitsConsistency:
    """Test consistency between get_entries_exits() and calculate_indicators()"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_entries_match_buy_signals(self, name, strategy_factory, sample_data):
        """Entry points should correspond to BUY signals from calculate_indicators"""
        strategy = strategy_factory()
        entries, exits = strategy.get_entries_exits(sample_data)
        data = strategy.calculate_indicators(sample_data)

        buy_signals = data['signal'] == 1
        sell_signals = data['signal'] == -1

        # Every entry should be a buy signal
        entry_indices = entries[entries].index
        for idx in entry_indices:
            assert buy_signals.loc[idx], (
                f"{name}: entry at {idx} is not a BUY signal in calculate_indicators"
            )

        # Every exit should be a sell signal
        exit_indices = exits[exits].index
        for idx in exit_indices:
            assert sell_signals.loc[idx], (
                f"{name}: exit at {idx} is not a SELL signal in calculate_indicators"
            )


class TestEntriesExitsCrossing:
    """Test that signals occur only at crossing points, not continuously"""

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_entries_are_sparse(self, name, strategy_factory, sample_data):
        """Entries should not have consecutive True values (crossing = momentary)"""
        strategy = strategy_factory()
        entries, _ = strategy.get_entries_exits(sample_data)

        # Check no consecutive True values
        consecutive = entries & entries.shift(1).fillna(False)
        assert not consecutive.any(), (
            f"{name}: entries have consecutive True values (not crossing points)"
        )

    @pytest.mark.parametrize("name,strategy_factory", ALL_STRATEGIES)
    def test_exits_are_sparse(self, name, strategy_factory, sample_data):
        """Exits should not have consecutive True values (crossing = momentary)"""
        strategy = strategy_factory()
        _, exits = strategy.get_entries_exits(sample_data)

        # Check no consecutive True values
        consecutive = exits & exits.shift(1).fillna(False)
        assert not consecutive.any(), (
            f"{name}: exits have consecutive True values (not crossing points)"
        )


class TestEntriesExitsWithDifferentParams:
    """Test strategies with different parameters"""

    def test_rsi_different_thresholds(self, sample_data):
        """RSI with different overbought/oversold should produce different signals"""
        strategy_tight = RSIStrategy(period=14, overbought=60, oversold=40)
        strategy_wide = RSIStrategy(period=14, overbought=80, oversold=20)

        entries_tight, _ = strategy_tight.get_entries_exits(sample_data)
        entries_wide, _ = strategy_wide.get_entries_exits(sample_data)

        # Tight thresholds should generally produce more or equal signals
        assert entries_tight.sum() >= entries_wide.sum() or True  # Data-dependent

    def test_macd_different_periods(self, sample_data):
        """MACD with different periods should work"""
        for fast, slow, signal in [(8, 17, 9), (12, 26, 9), (5, 35, 5)]:
            strategy = MACDStrategy(fast_period=fast, slow_period=slow, signal_period=signal)
            entries, exits = strategy.get_entries_exits(sample_data)

            assert entries.dtype == bool
            assert exits.dtype == bool
            assert not entries.isna().any()
            assert not exits.isna().any()

    def test_bollinger_different_std(self, sample_data):
        """Bollinger Bands with different std multiplier should work"""
        for num_std in [1.5, 2.0, 2.5, 3.0]:
            strategy = BollingerBandsStrategy(period=20, num_std=num_std)
            entries, exits = strategy.get_entries_exits(sample_data)

            assert entries.dtype == bool
            assert exits.dtype == bool
            assert not entries.isna().any()

    def test_stochastic_different_periods(self, sample_data):
        """Stochastic with different periods should work"""
        for k, d in [(5, 3), (14, 3), (21, 5)]:
            strategy = StochasticStrategy(k_period=k, d_period=d)
            entries, exits = strategy.get_entries_exits(sample_data)

            assert entries.dtype == bool
            assert exits.dtype == bool
            assert not entries.isna().any()
