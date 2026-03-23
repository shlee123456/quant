"""Tests for AdaptiveStrategyManager"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from trading_bot.adaptive_strategy_manager import AdaptiveStrategyManager
from trading_bot.regime_detector import MarketRegime, RegimeResult
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def strategy_class_map():
    return {
        'RSI Strategy': RSIStrategy,
        'MACD Strategy': MACDStrategy,
        'Bollinger Bands': BollingerBandsStrategy,
    }


@pytest.fixture
def default_params():
    return {
        'RSI Strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
        'MACD Strategy': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
        'Bollinger Bands': {'period': 20, 'num_std': 2.0},
    }


def _make_regime_result(regime, confidence=0.8, vol_pct=50.0, adx=30.0, trend=1.0):
    return RegimeResult(
        regime=regime,
        confidence=confidence,
        adx=adx,
        trend_direction=trend,
        volatility_percentile=vol_pct,
        recommended_strategies=[],
    )


def _make_detector_mock(regime_result):
    detector = Mock()
    detector.detect.return_value = regime_result
    return detector


@pytest.fixture
def sample_df():
    """Minimal DataFrame — manager doesn't read data, detector does."""
    import pandas as pd
    import numpy as np
    np.random.seed(42)
    n = 10
    return pd.DataFrame({
        'open': [100.0] * n,
        'high': [105.0] * n,
        'low': [95.0] * n,
        'close': [102.0] * n,
        'volume': [1000.0] * n,
    })


# ---------------------------------------------------------------------------
# Tests: initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_initial_strategy_key_resolution(self, strategy_class_map, default_params):
        rsi = RSIStrategy(period=14, overbought=70, oversold=30)
        detector = Mock()
        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
        )
        assert mgr.current_strategy is rsi
        assert mgr.current_strategy_key == 'RSI Strategy'

    def test_no_initial_strategy(self, strategy_class_map):
        detector = Mock()
        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
        )
        assert mgr.current_strategy is None
        assert mgr.current_strategy_key is None


# ---------------------------------------------------------------------------
# Tests: cooldown
# ---------------------------------------------------------------------------

class TestCooldown:
    def test_no_switch_during_cooldown(self, strategy_class_map, default_params, sample_df):
        """cooldown_bars 이내에는 전략 전환이 일어나지 않아야 한다."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            cooldown_bars=5,
        )

        # Force a switch first (cooldown starts at cooldown_bars, so first call can switch)
        _, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True
        mgr.tick()  # bars_since_switch = 1

        # During cooldown (bars 1-4), no switch should happen
        sideways = _make_regime_result(MarketRegime.SIDEWAYS, confidence=0.9)
        detector.detect.return_value = sideways
        for _ in range(3):
            _, _, did_switch = mgr.evaluate(sample_df)
            assert did_switch is False
            mgr.tick()

    def test_switch_after_cooldown(self, strategy_class_map, default_params, sample_df):
        """cooldown이 끝나면 전환 가능."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            cooldown_bars=3,
        )

        # First switch
        mgr.evaluate(sample_df)
        for _ in range(3):
            mgr.tick()

        # After cooldown, try switching to SIDEWAYS
        sideways = _make_regime_result(MarketRegime.SIDEWAYS, confidence=0.9)
        detector.detect.return_value = sideways
        _, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True


# ---------------------------------------------------------------------------
# Tests: confidence filter
# ---------------------------------------------------------------------------

class TestConfidenceFilter:
    def test_low_confidence_prevents_switch(self, strategy_class_map, default_params, sample_df):
        """min_confidence 미만이면 전환 안 됨."""
        rsi = RSIStrategy()
        low_conf = _make_regime_result(MarketRegime.BULLISH, confidence=0.3)
        detector = _make_detector_mock(low_conf)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            min_confidence=0.6,
        )

        _, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is False

    def test_high_confidence_allows_switch(self, strategy_class_map, default_params, sample_df):
        """min_confidence 이상이면 전환 허용."""
        rsi = RSIStrategy()
        high_conf = _make_regime_result(MarketRegime.BULLISH, confidence=0.8)
        detector = _make_detector_mock(high_conf)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            min_confidence=0.6,
        )

        _, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True


# ---------------------------------------------------------------------------
# Tests: strategy switching
# ---------------------------------------------------------------------------

class TestStrategySwitching:
    def test_bullish_selects_macd(self, strategy_class_map, default_params, sample_df):
        """BULLISH 레짐에서 MACD Strategy로 전환."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
        )

        new_strat, regime, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True
        assert isinstance(new_strat, MACDStrategy)
        assert mgr.current_strategy_key == 'MACD Strategy'

    def test_sideways_selects_rsi(self, strategy_class_map, default_params, sample_df):
        """SIDEWAYS 레짐에서 RSI Strategy로 전환."""
        macd = MACDStrategy()
        sideways = _make_regime_result(MarketRegime.SIDEWAYS, confidence=0.9)
        detector = _make_detector_mock(sideways)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=macd,
            default_params=default_params,
        )

        new_strat, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True
        assert isinstance(new_strat, RSIStrategy)

    def test_same_regime_no_switch(self, strategy_class_map, default_params, sample_df):
        """현재 전략이 추천 전략과 동일하면 전환 안 됨."""
        macd = MACDStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=macd,
            default_params=default_params,
        )

        _, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is False


# ---------------------------------------------------------------------------
# Tests: switch history
# ---------------------------------------------------------------------------

class TestSwitchHistory:
    def test_history_recorded_on_switch(self, strategy_class_map, default_params, sample_df):
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
        )

        mgr.evaluate(sample_df)
        history = mgr.get_switch_history()

        assert len(history) == 1
        assert history[0]['from_strategy'] == 'RSI Strategy'
        assert history[0]['to_strategy'] == 'MACD Strategy'
        assert history[0]['regime'] == 'BULLISH'
        assert 'confidence' in history[0]

    def test_no_history_when_no_switch(self, strategy_class_map, default_params, sample_df):
        macd = MACDStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=macd,
            default_params=default_params,
        )

        mgr.evaluate(sample_df)
        assert len(mgr.get_switch_history()) == 0


# ---------------------------------------------------------------------------
# Tests: regime_result returned (이중 감지 방지)
# ---------------------------------------------------------------------------

class TestRegimeResultReturned:
    def test_evaluate_returns_regime_result(self, strategy_class_map, default_params, sample_df):
        """evaluate()가 regime_result를 반환하여 SignalPipeline에서 재감지 방지."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
        )

        _, regime_result, _ = mgr.evaluate(sample_df)
        assert regime_result is not None
        assert regime_result.regime == MarketRegime.BULLISH

    def test_get_last_regime_result(self, strategy_class_map, default_params, sample_df):
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.75)
        detector = _make_detector_mock(bullish)

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
        )

        mgr.evaluate(sample_df)
        last = mgr.get_last_regime_result()
        assert last is not None
        assert last.confidence == 0.75


# ---------------------------------------------------------------------------
# Tests: disabled
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_disabled_returns_current_strategy(self, strategy_class_map, default_params, sample_df):
        rsi = RSIStrategy()
        detector = Mock()

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            enabled=False,
        )

        strat, regime, did_switch = mgr.evaluate(sample_df)
        assert strat is rsi
        assert regime is None
        assert did_switch is False
        detector.detect.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: parameter_adapter integration
# ---------------------------------------------------------------------------

class TestParameterAdapterIntegration:
    def test_adapter_called_on_switch(self, strategy_class_map, default_params, sample_df):
        """전략 전환 시 parameter_adapter.adapt() 호출."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        adapter = Mock()
        adapter.adapt.return_value = {
            'strategy_params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
            'strategy_params_changed': False,
            'stop_loss_pct': 0.05,
            'take_profit_pct': 0.10,
            'adjustments': [],
        }

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            parameter_adapter=adapter,
        )

        mgr.evaluate(sample_df)
        adapter.adapt.assert_called_once()

    def test_adapter_applied_when_params_changed(self, strategy_class_map, default_params, sample_df):
        """adapter가 strategy_params_changed=True 반환 시 파라미터 적응 적용."""
        rsi = RSIStrategy()
        bullish = _make_regime_result(MarketRegime.BULLISH, confidence=0.9)
        detector = _make_detector_mock(bullish)

        adapter = Mock()
        adapter.adapt.return_value = {
            'strategy_params': {'fast_period': 8, 'slow_period': 21, 'signal_period': 7},
            'strategy_params_changed': True,
            'stop_loss_pct': 0.03,
            'take_profit_pct': 0.08,
            'adjustments': ['fast_period: 12 -> 8'],
        }

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            parameter_adapter=adapter,
        )

        new_strat, _, did_switch = mgr.evaluate(sample_df)
        assert did_switch is True
        assert isinstance(new_strat, MACDStrategy)
        assert new_strat.fast_period == 8

    def test_adapter_called_on_same_regime(self, strategy_class_map, default_params, sample_df):
        """동일 레짐에서도 parameter_adapter 호출 (전환 없이 파라미터만 조정)."""
        rsi = RSIStrategy(period=14, overbought=70, oversold=30)
        sideways = _make_regime_result(MarketRegime.SIDEWAYS, confidence=0.9, vol_pct=90)
        detector = _make_detector_mock(sideways)

        adapter = Mock()
        adapter.adapt.return_value = {
            'strategy_params': {'period': 14, 'overbought': 80, 'oversold': 20},
            'strategy_params_changed': True,
            'stop_loss_pct': 0.07,
            'take_profit_pct': 0.13,
            'adjustments': ['overbought: 70 -> 80'],
        }

        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
            initial_strategy=rsi,
            default_params=default_params,
            parameter_adapter=adapter,
        )

        new_strat, _, did_switch = mgr.evaluate(sample_df)
        # same regime, no switch, but params adapted
        assert did_switch is False
        adapter.adapt.assert_called_once()
        assert isinstance(new_strat, RSIStrategy)
        assert new_strat.overbought == 80


# ---------------------------------------------------------------------------
# Tests: tick
# ---------------------------------------------------------------------------

class TestTick:
    def test_tick_increments_counter(self, strategy_class_map):
        detector = Mock()
        mgr = AdaptiveStrategyManager(
            strategy_class_map=strategy_class_map,
            regime_detector=detector,
        )
        initial = mgr._bars_since_switch
        mgr.tick()
        assert mgr._bars_since_switch == initial + 1
