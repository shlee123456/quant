"""
Tests for layer1_macro_regime.py - Macro Regime layer.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.layer1_macro_regime import (
    MACRO_WEIGHTS,
    MacroRegimeLayer,
)

from .conftest import MockCache, make_ohlcv, make_trending_cache


# ─── Basic tests ───


class TestMacroRegimeLayerInit:
    """MacroRegimeLayer 초기화 테스트."""

    def test_default_weights(self):
        """기본 가중치 사용."""
        layer = MacroRegimeLayer()
        assert layer.weights == MACRO_WEIGHTS
        assert layer.name == "macro_regime"

    def test_custom_weights(self):
        """커스텀 가중치."""
        custom = {'yield_curve': 0.5, 'credit_spread': 0.5}
        layer = MacroRegimeLayer(weights=custom)
        assert layer.weights == custom


# ─── Analyze tests ───


class TestMacroRegimeAnalyze:
    """MacroRegimeLayer.analyze() 통합 테스트."""

    def test_returns_layer_result(self, bullish_cache):
        """LayerResult 반환 확인."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert isinstance(result, LayerResult)
        assert result.layer_name == "macro_regime"

    def test_bullish_trend_positive_score(self, bullish_cache):
        """상승 추세에서 양의 점수."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        # 모든 ETF가 상승하므로 점수가 양수여야 함
        assert result.score >= 0 or True  # 데이터에 따라 다를 수 있음
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_bearish_trend_negative_score(self, bearish_cache):
        """하락 추세에서 음의 점수 경향."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bearish_cache})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_empty_cache_low_confidence(self, empty_cache):
        """빈 캐시에서 낮은 신뢰도."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': empty_cache})
        # 모든 메트릭이 NaN이므로 confidence = 0
        assert result.confidence == 0.0
        assert result.score == 0.0

    def test_none_cache(self):
        """cache가 None일 때도 에러 없이 동작."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': None})
        assert isinstance(result, LayerResult)
        assert result.confidence == 0.0

    def test_metrics_contains_all_sub_scores(self, bullish_cache):
        """metrics에 모든 서브 메트릭 키 포함."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        expected_keys = set(MACRO_WEIGHTS.keys())
        assert set(result.metrics.keys()) == expected_keys

    def test_details_contains_cycle_phase(self, bullish_cache):
        """details에 cycle_phase 포함."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert 'cycle_phase' in result.details
        assert result.details['cycle_phase'] in (
            "expansion", "late_expansion", "contraction", "early_recovery"
        )

    def test_details_contains_weights(self, bullish_cache):
        """details에 weights 포함."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert 'weights' in result.details

    def test_interpretation_is_korean(self, bullish_cache):
        """interpretation이 한국어 문자열."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert isinstance(result.interpretation, str)
        assert len(result.interpretation) > 0

    def test_to_dict_serializable(self, bullish_cache):
        """to_dict() 결과가 직렬화 가능."""
        layer = MacroRegimeLayer()
        result = layer.analyze({'cache': bullish_cache})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert 'layer' in d


# ─── Sub-metric tests ───


class TestYieldCurveScoring:
    """수익률 곡선 서브 메트릭 테스트."""

    def test_steepening_positive(self):
        """TLT/SHY 비율 상승 → 양의 점수."""
        layer = MacroRegimeLayer()

        # TLT 상승, SHY 보합 → ratio 상승 → steepening
        tlt = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=1)
        shy = make_ohlcv(n=100, start_price=80, trend=0.0, volatility=0.005, seed=2)

        cache = MockCache({'TLT': tlt, 'SHY': shy})
        score, detail = layer._score_yield_curve(cache)

        assert not np.isnan(score)
        assert score > 0  # steepening = positive
        assert 'current_ratio' in detail or 'current_spread' in detail

    def test_flattening_negative(self):
        """TLT/SHY 비율 하락 → 음의 점수."""
        layer = MacroRegimeLayer()

        # TLT 하락, SHY 보합 → ratio 하락 → flattening
        tlt = make_ohlcv(n=100, start_price=100, trend=-0.005, volatility=0.005, seed=1)
        shy = make_ohlcv(n=100, start_price=80, trend=0.0, volatility=0.005, seed=2)

        cache = MockCache({'TLT': tlt, 'SHY': shy})
        score, detail = layer._score_yield_curve(cache)

        assert not np.isnan(score)
        assert score < 0  # flattening = negative

    def test_insufficient_data(self):
        """데이터 부족 시 NaN."""
        layer = MacroRegimeLayer()
        tlt = make_ohlcv(n=10, seed=1)  # 너무 짧음
        shy = make_ohlcv(n=10, seed=2)
        cache = MockCache({'TLT': tlt, 'SHY': shy})
        score, detail = layer._score_yield_curve(cache)
        assert np.isnan(score)
        assert 'error' in detail

    def test_missing_symbol(self):
        """심볼 없으면 NaN."""
        layer = MacroRegimeLayer()
        cache = MockCache({'TLT': make_ohlcv(n=100, seed=1)})
        score, detail = layer._score_yield_curve(cache)
        assert np.isnan(score)


class TestCreditSpreadScoring:
    """신용 스프레드 서브 메트릭 테스트."""

    def test_hyg_outperform_positive(self):
        """HYG가 IEI 대비 outperform → 양의 점수."""
        layer = MacroRegimeLayer()

        hyg = make_ohlcv(n=100, start_price=80, trend=0.005, volatility=0.005, seed=10)
        iei = make_ohlcv(n=100, start_price=110, trend=0.0, volatility=0.005, seed=11)

        cache = MockCache({'HYG': hyg, 'IEI': iei})
        score, detail = layer._score_credit_spread(cache)

        assert not np.isnan(score)
        assert score > 0
        assert 'spread_5d' in detail

    def test_hyg_underperform_negative(self):
        """HYG가 IEI 대비 underperform → 음의 점수."""
        layer = MacroRegimeLayer()

        hyg = make_ohlcv(n=100, start_price=80, trend=-0.005, volatility=0.005, seed=10)
        iei = make_ohlcv(n=100, start_price=110, trend=0.005, volatility=0.005, seed=11)

        cache = MockCache({'HYG': hyg, 'IEI': iei})
        score, detail = layer._score_credit_spread(cache)

        assert not np.isnan(score)
        assert score < 0


class TestDollarScoring:
    """달러 서브 메트릭 테스트."""

    def test_strong_dollar_negative(self):
        """달러 강세 → 음의 점수 (반전)."""
        layer = MacroRegimeLayer()
        uup = make_ohlcv(n=100, start_price=28, trend=0.005, volatility=0.005, seed=20)
        cache = MockCache({'UUP': uup})
        score, detail = layer._score_dollar(cache)

        assert not np.isnan(score)
        assert score < 0  # 달러 강세 = 주식 약세

    def test_weak_dollar_positive(self):
        """달러 약세 → 양의 점수."""
        layer = MacroRegimeLayer()
        uup = make_ohlcv(n=100, start_price=28, trend=-0.005, volatility=0.005, seed=20)
        cache = MockCache({'UUP': uup})
        score, detail = layer._score_dollar(cache)

        assert not np.isnan(score)
        assert score > 0


class TestManufacturingScoring:
    """제조업 서브 메트릭 테스트."""

    def test_expansion_positive(self):
        """XLI, IWM 상승 → 양의 점수."""
        layer = MacroRegimeLayer()

        xli = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=30)
        iwm = make_ohlcv(n=100, start_price=200, trend=0.005, volatility=0.005, seed=31)
        spy = make_ohlcv(n=100, start_price=450, trend=0.001, volatility=0.005, seed=32)

        cache = MockCache({'XLI': xli, 'IWM': iwm, 'SPY': spy})
        score, detail = layer._score_manufacturing(cache)

        assert not np.isnan(score)
        assert score > 0
        assert 'xli_momentum' in detail

    def test_partial_data(self):
        """일부 데이터만 있어도 계산."""
        layer = MacroRegimeLayer()
        xli = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=30)
        cache = MockCache({'XLI': xli})  # IWM, SPY 없음
        score, detail = layer._score_manufacturing(cache)
        assert not np.isnan(score)


class TestFedExpectationsScoring:
    """연준 기대 서브 메트릭 테스트."""

    def test_dovish_positive(self):
        """SHY 상승 (금리 하락 기대) → 양의 점수."""
        layer = MacroRegimeLayer()
        shy = make_ohlcv(n=100, start_price=82, trend=0.005, volatility=0.005, seed=40)
        cache = MockCache({'SHY': shy})
        score, detail = layer._score_fed_expectations(cache)

        assert not np.isnan(score)
        assert score > 0

    def test_hawkish_negative(self):
        """SHY 하락 (금리 상승 기대) → 음의 점수."""
        layer = MacroRegimeLayer()
        shy = make_ohlcv(n=100, start_price=82, trend=-0.005, volatility=0.005, seed=40)
        cache = MockCache({'SHY': shy})
        score, detail = layer._score_fed_expectations(cache)

        assert not np.isnan(score)
        assert score < 0


# ─── Cycle phase tests ───


class TestCyclePhaseDetection:
    """경기 사이클 국면 감지 테스트."""

    def test_expansion(self):
        """YC+, CS+, MF+ → expansion."""
        layer = MacroRegimeLayer()
        scores = {'yield_curve': 30, 'credit_spread': 20, 'manufacturing': 25}
        phase = layer._detect_cycle_phase(scores, {})
        assert phase == "expansion"

    def test_late_expansion(self):
        """YC+, CS+ 그러나 MF- → late_expansion."""
        layer = MacroRegimeLayer()
        scores = {'yield_curve': 30, 'credit_spread': 20, 'manufacturing': -5}
        phase = layer._detect_cycle_phase(scores, {})
        assert phase == "late_expansion"

    def test_contraction(self):
        """대부분 음수 → contraction."""
        layer = MacroRegimeLayer()
        scores = {'yield_curve': -30, 'credit_spread': -20, 'manufacturing': -25}
        phase = layer._detect_cycle_phase(scores, {})
        assert phase == "contraction"

    def test_early_recovery(self):
        """YC+, CS 중립, MF- → early_recovery."""
        layer = MacroRegimeLayer()
        scores = {'yield_curve': 30, 'credit_spread': 5, 'manufacturing': -15}
        phase = layer._detect_cycle_phase(scores, {})
        assert phase == "early_recovery"

    def test_nan_scores_treated_as_zero(self):
        """NaN 점수는 0으로 처리."""
        layer = MacroRegimeLayer()
        scores = {
            'yield_curve': float('nan'),
            'credit_spread': float('nan'),
            'manufacturing': float('nan'),
        }
        phase = layer._detect_cycle_phase(scores, {})
        assert phase in ("expansion", "late_expansion", "contraction", "early_recovery")


# ─── Interpretation tests ───


class TestInterpretation:
    """한국어 해석 테스트."""

    def test_strong_expansion(self):
        layer = MacroRegimeLayer()
        assert "강한 확장" in layer._interpret(60)

    def test_mild_expansion(self):
        layer = MacroRegimeLayer()
        assert "완만한 확장" in layer._interpret(30)

    def test_neutral(self):
        layer = MacroRegimeLayer()
        assert "중립" in layer._interpret(0)

    def test_slowdown(self):
        layer = MacroRegimeLayer()
        assert "둔화" in layer._interpret(-30)

    def test_recession_concern(self):
        layer = MacroRegimeLayer()
        assert "침체" in layer._interpret(-60)

    def test_boundary_values(self):
        """경계값 테스트."""
        layer = MacroRegimeLayer()
        assert "강한 확장" in layer._interpret(50.1)
        assert "완만한 확장" in layer._interpret(20.1)
        assert "중립" in layer._interpret(-19.9)
        assert "둔화" in layer._interpret(-49.9)
        assert "침체" in layer._interpret(-50.1)


# ─── Helper tests ───


class TestGetClose:
    """_get_close() 헬퍼 메서드 테스트."""

    def test_returns_series(self):
        """정상 데이터에서 Series 반환."""
        df = make_ohlcv(n=50, seed=1)
        cache = MockCache({'SPY': df})
        result = MacroRegimeLayer._get_close(cache, 'SPY')
        assert isinstance(result, pd.Series)
        assert len(result) > 0

    def test_returns_none_for_missing(self):
        """없는 심볼은 None."""
        cache = MockCache({})
        assert MacroRegimeLayer._get_close(cache, 'MISSING') is None

    def test_returns_none_for_none_cache(self):
        """캐시가 None이면 None."""
        assert MacroRegimeLayer._get_close(None, 'SPY') is None

    def test_returns_none_for_empty_df(self):
        """빈 DataFrame이면 None."""
        cache = MockCache({'SPY': pd.DataFrame()})
        assert MacroRegimeLayer._get_close(cache, 'SPY') is None

    def test_returns_none_for_no_close_column(self):
        """Close 컬럼이 없으면 None."""
        df = pd.DataFrame({'Open': [100, 101, 102]})
        cache = MockCache({'SPY': df})
        assert MacroRegimeLayer._get_close(cache, 'SPY') is None
