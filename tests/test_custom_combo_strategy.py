"""
Tests for CustomComboStrategy

Covers initialization, combination logic (AND, OR, MAJORITY, WEIGHTED),
calculate_indicators, get_current_signal, get_all_signals, get_entries_exits.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading_bot.custom_combo_strategy import CustomComboStrategy
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_data():
    """100-bar OHLCV test data"""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
    np.random.seed(42)
    prices = [100.0]
    for _ in range(99):
        prices.append(prices[-1] + np.random.normal(0, 2))
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * 100,
        },
        index=dates,
    )
    return df


@pytest.fixture
def rsi_strategy():
    return RSIStrategy(period=14, overbought=70, oversold=30)


@pytest.fixture
def macd_strategy():
    return MACDStrategy(fast_period=12, slow_period=26, signal_period=9)


@pytest.fixture
def two_strategies(rsi_strategy, macd_strategy):
    return [rsi_strategy, macd_strategy]


@pytest.fixture
def two_names():
    return ["RSI Strategy", "MACD Strategy"]


# ---------------------------------------------------------------------------
# Stub strategy for deterministic signal testing
# ---------------------------------------------------------------------------

class _StubStrategy:
    """Returns predetermined signals for testing combination logic."""

    def __init__(self, signals):
        self.name = "Stub"
        self._signals = signals

    def calculate_indicators(self, df):
        data = df.copy()
        data["signal"] = self._signals[: len(data)]
        data["position"] = data["signal"].replace(0, np.nan).ffill().fillna(0)
        return data

    def get_entries_exits(self, df):
        data = self.calculate_indicators(df)
        entries = data["signal"] == 1
        exits = data["signal"] == -1
        return entries, exits


def _make_df(n=5):
    return pd.DataFrame(
        {
            "open": [100] * n,
            "high": [101] * n,
            "low": [99] * n,
            "close": [100] * n,
            "volume": [1000] * n,
        }
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestCustomComboInit:

    def test_basic_init(self, two_strategies, two_names):
        combo = CustomComboStrategy(
            strategies=two_strategies,
            strategy_names=two_names,
        )
        assert combo.combination_logic == "MAJORITY"
        assert len(combo.strategies) == 2
        assert len(combo.weights) == 2
        assert "Custom_" in combo.name

    def test_empty_strategies_raises(self):
        with pytest.raises(ValueError, match="최소 1개"):
            CustomComboStrategy(strategies=[], strategy_names=[])

    def test_weight_mismatch_raises(self, two_strategies, two_names):
        with pytest.raises(ValueError, match="일치"):
            CustomComboStrategy(
                strategies=two_strategies,
                strategy_names=two_names,
                weights=[1.0],
            )

    def test_weights_normalized(self, two_strategies, two_names):
        combo = CustomComboStrategy(
            strategies=two_strategies,
            strategy_names=two_names,
            weights=[2.0, 8.0],
        )
        assert abs(sum(combo.weights) - 1.0) < 1e-9

    def test_default_equal_weights(self, two_strategies, two_names):
        combo = CustomComboStrategy(
            strategies=two_strategies,
            strategy_names=two_names,
        )
        assert abs(combo.weights[0] - 0.5) < 1e-9
        assert abs(combo.weights[1] - 0.5) < 1e-9

    def test_logic_case_insensitive(self, two_strategies, two_names):
        combo = CustomComboStrategy(
            strategies=two_strategies,
            strategy_names=two_names,
            combination_logic="and",
        )
        assert combo.combination_logic == "AND"


# ---------------------------------------------------------------------------
# calculate_indicators
# ---------------------------------------------------------------------------

class TestCalculateIndicators:

    def test_returns_dataframe(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        result = combo.calculate_indicators(sample_data)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_data)

    def test_has_signal_and_position(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        result = combo.calculate_indicators(sample_data)
        assert "signal" in result.columns
        assert "position" in result.columns

    def test_signal_values_valid(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        result = combo.calculate_indicators(sample_data)
        assert result["signal"].isin([-1, 0, 1]).all()

    def test_strategy_prefix_columns(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        result = combo.calculate_indicators(sample_data)
        strat1_cols = [c for c in result.columns if c.startswith("strat1_")]
        strat2_cols = [c for c in result.columns if c.startswith("strat2_")]
        assert len(strat1_cols) > 0
        assert len(strat2_cols) > 0

    def test_empty_dataframe(self, two_strategies, two_names):
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        result = combo.calculate_indicators(empty)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Combination logic
# ---------------------------------------------------------------------------

class TestCombinationLogic:

    def test_and_logic_all_buy(self):
        s1 = _StubStrategy([0, 1, 1, -1, 0])
        s2 = _StubStrategy([0, 1, 0, -1, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="AND",
        )
        result = combo.calculate_indicators(_make_df())
        assert result["signal"].iloc[1] == 1   # both BUY
        assert result["signal"].iloc[2] == 0   # only s1 BUY

    def test_and_logic_all_sell(self):
        s1 = _StubStrategy([0, -1, -1, 0, 0])
        s2 = _StubStrategy([0, -1, 0, 0, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="AND",
        )
        result = combo.calculate_indicators(_make_df())
        assert result["signal"].iloc[1] == -1
        assert result["signal"].iloc[2] == 0

    def test_or_logic(self):
        s1 = _StubStrategy([0, 1, 0, 0, 0])
        s2 = _StubStrategy([0, 0, 0, -1, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="OR",
        )
        result = combo.calculate_indicators(_make_df())
        assert result["signal"].iloc[1] == 1
        assert result["signal"].iloc[3] == -1

    def test_or_buy_takes_priority(self):
        s1 = _StubStrategy([0, 1, 0, 0, 0])
        s2 = _StubStrategy([0, -1, 0, 0, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="OR",
        )
        result = combo.calculate_indicators(_make_df())
        assert result["signal"].iloc[1] == 1

    def test_majority_logic(self):
        s1 = _StubStrategy([0, 1, 1, 0, 0])
        s2 = _StubStrategy([0, 1, 0, 0, 0])
        s3 = _StubStrategy([0, 0, 0, 0, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2, s3],
            strategy_names=["S1", "S2", "S3"],
            combination_logic="MAJORITY",
        )
        result = combo.calculate_indicators(_make_df())
        assert result["signal"].iloc[1] == 1   # 2/3 > 1.5
        assert result["signal"].iloc[2] == 0   # 1/3 not majority

    def test_weighted_logic(self):
        s1 = _StubStrategy([0, 1, 0, 0, 0])
        s2 = _StubStrategy([0, 0, 0, 0, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="WEIGHTED",
            weights=[9.0, 1.0],
            threshold=0.5,
        )
        result = combo.calculate_indicators(_make_df())
        # s1 weight = 0.9, s1=1 -> weighted_sum = 0.9 > 0.5 -> BUY
        assert result["signal"].iloc[1] == 1

    def test_weighted_below_threshold(self):
        s1 = _StubStrategy([0, 1, 0, 0, 0])
        s2 = _StubStrategy([0, 0, 0, 0, 0])
        combo = CustomComboStrategy(
            strategies=[s1, s2],
            strategy_names=["S1", "S2"],
            combination_logic="WEIGHTED",
            weights=[1.0, 9.0],
            threshold=0.5,
        )
        result = combo.calculate_indicators(_make_df())
        # s1 weight = 0.1, s1=1 -> weighted_sum = 0.1 < 0.5 -> HOLD
        assert result["signal"].iloc[1] == 0

    def test_unknown_logic_raises(self):
        s1 = _StubStrategy([0, 0])
        combo = CustomComboStrategy(
            strategies=[s1],
            strategy_names=["S1"],
            combination_logic="MAGIC",
        )
        with pytest.raises(ValueError, match="Unknown combination logic"):
            combo.calculate_indicators(_make_df(2))


# ---------------------------------------------------------------------------
# get_current_signal
# ---------------------------------------------------------------------------

class TestGetCurrentSignal:

    def test_returns_tuple(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        signal, info = combo.get_current_signal(sample_data)
        assert isinstance(signal, int)
        assert signal in [-1, 0, 1]
        assert isinstance(info, dict)

    def test_info_contains_individual_signals(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        _, info = combo.get_current_signal(sample_data)
        assert "individual_signals" in info
        assert "combination_logic" in info
        assert "weights" in info

    def test_empty_data_returns_zero(self, two_strategies, two_names):
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        signal, info = combo.get_current_signal(empty)
        assert signal == 0
        assert info == {}


# ---------------------------------------------------------------------------
# get_all_signals
# ---------------------------------------------------------------------------

class TestGetAllSignals:

    def test_returns_list(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        signals = combo.get_all_signals(sample_data)
        assert isinstance(signals, list)

    def test_signal_dict_structure(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        signals = combo.get_all_signals(sample_data)
        for s in signals:
            assert "signal" in s
            assert s["signal"] in ("BUY", "SELL")
            assert "price" in s
            assert "individual_signals" in s


# ---------------------------------------------------------------------------
# get_entries_exits
# ---------------------------------------------------------------------------

class TestGetEntriesExits:

    def test_returns_bool_series(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        entries, exits = combo.get_entries_exits(sample_data)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert len(entries) == len(sample_data)

    def test_no_overlap(self, sample_data, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        entries, exits = combo.get_entries_exits(sample_data)
        assert not (entries & exits).any()

    def test_empty_dataframe(self, two_strategies, two_names):
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        entries, exits = combo.get_entries_exits(empty)
        assert len(entries) == 0
        assert len(exits) == 0

    def test_all_logics_produce_entries_exits(self, sample_data, two_strategies, two_names):
        for logic in ["AND", "OR", "MAJORITY", "WEIGHTED"]:
            combo = CustomComboStrategy(
                strategies=two_strategies,
                strategy_names=two_names,
                combination_logic=logic,
            )
            entries, exits = combo.get_entries_exits(sample_data)
            assert entries.dtype == bool
            assert exits.dtype == bool

    def test_unknown_logic_raises_in_entries_exits(self):
        s1 = _StubStrategy([0, 0])
        combo = CustomComboStrategy(
            strategies=[s1],
            strategy_names=["S1"],
            combination_logic="MAGIC",
        )
        with pytest.raises(ValueError, match="Unknown combination logic"):
            combo.get_entries_exits(_make_df(2))


# ---------------------------------------------------------------------------
# get_params / get_param_info / __str__
# ---------------------------------------------------------------------------

class TestMetaMethods:

    def test_get_params(self, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        params = combo.get_params()
        assert "combination_logic" in params
        assert "strategy_names" in params
        assert "weights" in params
        assert "threshold" in params

    def test_get_param_info(self, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        info = combo.get_param_info()
        assert len(info) > 0

    def test_str(self, two_strategies, two_names):
        combo = CustomComboStrategy(strategies=two_strategies, strategy_names=two_names)
        s = str(combo)
        assert "Custom Combo" in s
        assert "MAJORITY" in s
