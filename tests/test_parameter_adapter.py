"""Tests for ParameterAdapter"""

import math
import pytest
from unittest.mock import Mock

from trading_bot.parameter_adapter import ParameterAdapter
from trading_bot.regime_detector import MarketRegime, RegimeResult
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from trading_bot.strategies.stochastic_strategy import StochasticStrategy
from trading_bot.strategies.rsi_macd_combo_strategy import RSIMACDComboStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_regime_result(vol_pct, regime=MarketRegime.SIDEWAYS, confidence=0.8):
    return RegimeResult(
        regime=regime,
        confidence=confidence,
        adx=20.0,
        trend_direction=0.0,
        volatility_percentile=vol_pct,
    )


# ---------------------------------------------------------------------------
# Tests: interpolation accuracy
# ---------------------------------------------------------------------------

class TestInterpolation:
    """_interpolate() 선형 보간 정확성."""

    @pytest.fixture
    def adapter(self):
        return ParameterAdapter(base_strategy_params={})

    def test_vol_0_returns_low(self, adapter):
        """vol_pct=0 -> low 값."""
        assert adapter._interpolate(0.0, 70.0, 65.0, 85.0) == 65.0

    def test_vol_25_returns_base(self, adapter):
        """vol_pct=25 -> base 값."""
        assert adapter._interpolate(25.0, 70.0, 65.0, 85.0) == 70.0

    def test_vol_50_returns_base(self, adapter):
        """vol_pct=50 -> base 값 (중간 구간)."""
        assert adapter._interpolate(50.0, 70.0, 65.0, 85.0) == 70.0

    def test_vol_75_returns_base(self, adapter):
        """vol_pct=75 -> base 값."""
        assert adapter._interpolate(75.0, 70.0, 65.0, 85.0) == 70.0

    def test_vol_100_returns_high(self, adapter):
        """vol_pct=100 -> high 값."""
        assert adapter._interpolate(100.0, 70.0, 65.0, 85.0) == 85.0

    def test_vol_12_5_midpoint_low_to_base(self, adapter):
        """vol_pct=12.5 -> low와 base의 중간."""
        result = adapter._interpolate(12.5, 70.0, 65.0, 85.0)
        assert abs(result - 67.5) < 0.01

    def test_vol_87_5_midpoint_base_to_high(self, adapter):
        """vol_pct=87.5 -> base와 high의 중간."""
        result = adapter._interpolate(87.5, 70.0, 65.0, 85.0)
        assert abs(result - 77.5) < 0.01


# ---------------------------------------------------------------------------
# Tests: clamping
# ---------------------------------------------------------------------------

class TestClamping:
    """경계값 클램핑."""

    @pytest.fixture
    def adapter(self):
        return ParameterAdapter(base_strategy_params={})

    def test_vol_below_zero_clamped(self, adapter):
        """vol_pct < 0 -> 0으로 클램핑."""
        result = adapter._interpolate(-10.0, 70.0, 65.0, 85.0)
        assert result == 65.0

    def test_vol_above_100_clamped(self, adapter):
        """vol_pct > 100 -> 100으로 클램핑."""
        result = adapter._interpolate(110.0, 70.0, 65.0, 85.0)
        assert result == 85.0

    def test_result_clamped_to_range(self, adapter):
        """결과가 [min(low,high), max(low,high)] 범위 내."""
        # oversold: low=15, high=35 (inverted)
        result = adapter._interpolate(0.0, 30.0, 35.0, 15.0)
        assert 15.0 <= result <= 35.0


# ---------------------------------------------------------------------------
# Tests: volatility zones
# ---------------------------------------------------------------------------

class TestVolatilityZones:
    """각 변동성 구간에서 RSI와 리스크 파라미터 동작."""

    def test_low_volatility_tighter_rsi(self):
        """극저변동성(0) -> overbought=65, oversold=35."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))

        assert result['strategy_params']['overbought'] == 65.0
        assert result['strategy_params']['oversold'] == 35.0
        assert result['strategy_params_changed'] is True

    def test_mid_volatility_base_params(self):
        """보통 변동성(50) -> 기본값 유지."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
        )
        result = adapter.adapt(_make_regime_result(vol_pct=50.0))

        assert result['strategy_params']['overbought'] == 70
        assert result['strategy_params']['oversold'] == 30
        assert result['strategy_params_changed'] is False

    def test_high_volatility_wider_rsi(self):
        """극고변동성(100) -> overbought=85, oversold=15."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
        )
        result = adapter.adapt(_make_regime_result(vol_pct=100.0))

        assert result['strategy_params']['overbought'] == 85.0
        assert result['strategy_params']['oversold'] == 15.0
        assert result['strategy_params_changed'] is True

    def test_low_volatility_tighter_risk(self):
        """극저변동성(0) -> SL=2%, TP=4%."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14},
            base_stop_loss_pct=0.05,
            base_take_profit_pct=0.10,
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))

        assert abs(result['stop_loss_pct'] - 0.02) < 0.001
        assert abs(result['take_profit_pct'] - 0.04) < 0.001

    def test_high_volatility_wider_risk(self):
        """극고변동성(100) -> SL=8%, TP=15%."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14},
            base_stop_loss_pct=0.05,
            base_take_profit_pct=0.10,
        )
        result = adapter.adapt(_make_regime_result(vol_pct=100.0))

        assert abs(result['stop_loss_pct'] - 0.08) < 0.001
        assert abs(result['take_profit_pct'] - 0.15) < 0.001


# ---------------------------------------------------------------------------
# Tests: NaN volatility_percentile
# ---------------------------------------------------------------------------

class TestNaNHandling:
    def test_nan_vol_returns_defaults(self):
        """NaN volatility_percentile -> 기본값 반환."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            base_stop_loss_pct=0.05,
            base_take_profit_pct=0.10,
        )
        regime = RegimeResult(
            regime=MarketRegime.SIDEWAYS,
            confidence=0.8,
            adx=20.0,
            trend_direction=0.0,
            volatility_percentile=float('nan'),
        )
        result = adapter.adapt(regime)

        assert result['strategy_params_changed'] is False
        assert result['stop_loss_pct'] == 0.05
        assert result['take_profit_pct'] == 0.10
        assert result['adjustments'] == []

    def test_none_vol_returns_defaults(self):
        """volatility_percentile=None -> 기본값 반환."""
        adapter = ParameterAdapter(
            base_strategy_params={'overbought': 70, 'oversold': 30},
        )
        regime = RegimeResult(
            regime=MarketRegime.SIDEWAYS,
            confidence=0.8,
            adx=20.0,
            trend_direction=0.0,
            volatility_percentile=None,
        )
        result = adapter.adapt(regime)
        assert result['strategy_params_changed'] is False


# ---------------------------------------------------------------------------
# Tests: type(strategy)(**get_params()) pattern
# ---------------------------------------------------------------------------

class TestStrategyRecreation:
    """type(strategy)(**get_params()) 패턴이 모든 전략에서 안전한지 검증."""

    @pytest.mark.parametrize("strategy_cls, params", [
        (RSIStrategy, {'period': 14, 'overbought': 75, 'oversold': 25}),
        (MACDStrategy, {'fast_period': 10, 'slow_period': 24, 'signal_period': 8}),
        (BollingerBandsStrategy, {'period': 20, 'num_std': 2.5}),
        (StochasticStrategy, {'k_period': 14, 'd_period': 5, 'overbought': 75, 'oversold': 25}),
        (RSIMACDComboStrategy, {
            'rsi_period': 14, 'rsi_overbought': 70, 'rsi_oversold': 30,
            'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
        }),
    ])
    def test_recreate_strategy_from_get_params(self, strategy_cls, params):
        """전략 인스턴스 생성 -> get_params() -> 동일 클래스 재생성 가능."""
        original = strategy_cls(**params)
        recreated = type(original)(**original.get_params())

        assert type(recreated) is type(original)
        assert recreated.get_params() == original.get_params()


# ---------------------------------------------------------------------------
# Tests: strategy_params_changed flag
# ---------------------------------------------------------------------------

class TestParamsChangedFlag:
    def test_rsi_params_changed_when_vol_extreme(self):
        """RSI 전략: overbought/oversold 변경 시 True."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))
        assert result['strategy_params_changed'] is True

    def test_macd_params_unchanged(self):
        """MACD 전략: RSI 관련 파라미터 없으므로 항상 False."""
        adapter = ParameterAdapter(
            base_strategy_params={'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))
        assert result['strategy_params_changed'] is False

    def test_rsi_macd_combo_params_changed(self):
        """RSI+MACD Combo: rsi_overbought/rsi_oversold 변경 시 True."""
        adapter = ParameterAdapter(
            base_strategy_params={
                'rsi_period': 14, 'rsi_overbought': 70, 'rsi_oversold': 30,
                'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
            },
        )
        result = adapter.adapt(_make_regime_result(vol_pct=100.0))
        assert result['strategy_params_changed'] is True
        # rsi_overbought and rsi_oversold should be adjusted
        assert result['strategy_params']['rsi_overbought'] == 85.0
        assert result['strategy_params']['rsi_oversold'] == 15.0


# ---------------------------------------------------------------------------
# Tests: disabled
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_disabled_returns_base_params(self):
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            enabled=False,
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))
        assert result['strategy_params_changed'] is False
        assert result['strategy_params'] == {'period': 14, 'overbought': 70, 'oversold': 30}


# ---------------------------------------------------------------------------
# Tests: adjustments list
# ---------------------------------------------------------------------------

class TestAdjustments:
    def test_adjustments_populated(self):
        """변경 사항이 adjustments 리스트에 기록됨."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            base_stop_loss_pct=0.05,
            base_take_profit_pct=0.10,
        )
        result = adapter.adapt(_make_regime_result(vol_pct=0.0))

        assert len(result['adjustments']) > 0
        assert any('overbought' in a for a in result['adjustments'])
        assert any('oversold' in a for a in result['adjustments'])
        assert any('stop_loss' in a for a in result['adjustments'])
        assert any('take_profit' in a for a in result['adjustments'])

    def test_no_adjustments_at_mid_vol(self):
        """중간 변동성에서 조정 없음."""
        adapter = ParameterAdapter(
            base_strategy_params={'period': 14, 'overbought': 70, 'oversold': 30},
            base_stop_loss_pct=0.05,
            base_take_profit_pct=0.10,
        )
        result = adapter.adapt(_make_regime_result(vol_pct=50.0))
        assert result['adjustments'] == []
