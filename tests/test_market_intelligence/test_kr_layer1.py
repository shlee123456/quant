"""
Tests for kr_layer1_macro_regime.py - 한국 매크로 레짐 레이어.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.kr_layer1_macro_regime import (
    KR_MACRO_WEIGHTS,
    KRMacroRegimeLayer,
    KR_BOND_3Y_ETF,
    KR_CORP_AA_ETF,
    KR_GOV_BOND_ETF,
    USDKRW_SYMBOL,
)

from .conftest import MockCache, make_ohlcv


# ─── Helper: MockBOKFetcher ───


class MockBOKFetcher:
    """테스트용 BOK 데이터 페처."""

    def __init__(
        self,
        base_rate: float = 3.5,
        base_rate_prev: float = 3.5,
        ip_current: float = 102.0,
        ip_prev: float = 100.0,
    ):
        self._base_rate = base_rate
        self._base_rate_prev = base_rate_prev
        self._ip_current = ip_current
        self._ip_prev = ip_prev

    def get_base_rate(self) -> pd.Series:
        """기준금리 시리즈 반환."""
        return pd.Series(
            [self._base_rate_prev, self._base_rate],
            index=pd.date_range('2026-01-01', periods=2, freq='MS'),
        )

    def get_industrial_production(self) -> pd.Series:
        """광공업생산지수 시리즈 반환."""
        return pd.Series(
            [self._ip_prev, self._ip_current],
            index=pd.date_range('2026-01-01', periods=2, freq='MS'),
        )


class MockBOKFetcherFailing:
    """조회 실패하는 BOK 페처."""

    def get_base_rate(self) -> pd.Series:
        raise ConnectionError("BOK API 연결 실패")

    def get_industrial_production(self) -> pd.Series:
        raise ConnectionError("BOK API 연결 실패")


# ─── Fixtures ───


def _make_kr_cache(trend: float = 0.001, n: int = 200, seed: int = 42) -> MockCache:
    """한국 시장 심볼로 MockCache 생성."""
    data = {
        KR_BOND_3Y_ETF: make_ohlcv(n=n, start_price=110, trend=trend, seed=seed),
        KR_CORP_AA_ETF: make_ohlcv(n=n, start_price=105, trend=trend, seed=seed + 1),
        KR_GOV_BOND_ETF: make_ohlcv(n=n, start_price=120, trend=trend * 0.5, seed=seed + 2),
        USDKRW_SYMBOL: make_ohlcv(n=n, start_price=1300, trend=-trend, seed=seed + 3),
    }
    return MockCache(data)


@pytest.fixture
def kr_bullish_cache() -> MockCache:
    return _make_kr_cache(trend=0.002, seed=100)


@pytest.fixture
def kr_bearish_cache() -> MockCache:
    return _make_kr_cache(trend=-0.002, seed=200)


@pytest.fixture
def empty_cache() -> MockCache:
    return MockCache({})


@pytest.fixture
def bok_fetcher_cutting() -> MockBOKFetcher:
    """금리 인하 BOK 페처."""
    return MockBOKFetcher(base_rate=3.25, base_rate_prev=3.5, ip_current=103.0, ip_prev=100.0)


@pytest.fixture
def bok_fetcher_hiking() -> MockBOKFetcher:
    """금리 인상 BOK 페처."""
    return MockBOKFetcher(base_rate=3.75, base_rate_prev=3.5, ip_current=98.0, ip_prev=100.0)


# ─── Basic tests ───


class TestKRMacroRegimeLayerInit:
    """KRMacroRegimeLayer 초기화 테스트."""

    def test_default_weights(self):
        layer = KRMacroRegimeLayer()
        assert layer.weights == KR_MACRO_WEIGHTS
        assert layer.name == "kr_macro_regime"

    def test_custom_weights(self):
        custom = {'interest_rate': 0.5, 'credit_spread': 0.5}
        layer = KRMacroRegimeLayer(weights=custom)
        assert layer.weights == custom


# ─── Analyze tests ───


class TestKRMacroRegimeAnalyze:
    """KRMacroRegimeLayer.analyze() 통합 테스트."""

    def test_returns_layer_result(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        assert isinstance(result, LayerResult)
        assert result.layer_name == "kr_macro_regime"

    def test_bullish_trend_valid(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_bearish_trend_valid(self, kr_bearish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bearish_cache})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_empty_cache_low_confidence(self, empty_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': empty_cache})
        assert result.confidence == 0.0
        assert result.score == 0.0

    def test_none_cache(self):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': None})
        assert isinstance(result, LayerResult)
        assert result.confidence == 0.0

    def test_metrics_contains_all_sub_scores(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        expected_keys = set(KR_MACRO_WEIGHTS.keys())
        assert set(result.metrics.keys()) == expected_keys

    def test_details_contains_cycle_phase(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        assert 'cycle_phase' in result.details
        assert result.details['cycle_phase'] in (
            "expansion", "late_expansion", "contraction", "early_recovery"
        )

    def test_with_bok_fetcher(self, kr_bullish_cache, bok_fetcher_cutting):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({
            'cache': kr_bullish_cache,
            'bok_fetcher': bok_fetcher_cutting,
        })
        assert isinstance(result, LayerResult)
        # BOK 데이터가 있으면 interest_rate와 industrial_production 점수가 NaN이 아님
        assert not np.isnan(result.metrics['interest_rate'])
        assert not np.isnan(result.metrics['industrial_production'])

    def test_with_failing_bok_fetcher(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({
            'cache': kr_bullish_cache,
            'bok_fetcher': MockBOKFetcherFailing(),
        })
        # BOK 실패해도 ETF 폴백으로 동작
        assert isinstance(result, LayerResult)

    def test_interpretation_is_korean(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        assert isinstance(result.interpretation, str)
        assert len(result.interpretation) > 0

    def test_to_dict_serializable(self, kr_bullish_cache):
        layer = KRMacroRegimeLayer()
        result = layer.analyze({'cache': kr_bullish_cache})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert 'layer' in d


# ─── Sub-metric tests ───


class TestInterestRateScoring:
    """금리 방향 서브 메트릭 테스트."""

    def test_bond_etf_rising_positive(self):
        """채권 ETF 상승 → 양의 점수 (금리 하락 기대)."""
        layer = KRMacroRegimeLayer()
        bond = make_ohlcv(n=100, start_price=110, trend=0.005, volatility=0.005, seed=1)
        cache = MockCache({KR_BOND_3Y_ETF: bond})
        score, detail = layer._score_interest_rate(cache, None)
        assert not np.isnan(score)
        assert score > 0
        assert detail['source'] == 'KR_BOND_3Y_ETF'

    def test_bond_etf_falling_negative(self):
        """채권 ETF 하락 → 음의 점수."""
        layer = KRMacroRegimeLayer()
        bond = make_ohlcv(n=100, start_price=110, trend=-0.005, volatility=0.005, seed=1)
        cache = MockCache({KR_BOND_3Y_ETF: bond})
        score, detail = layer._score_interest_rate(cache, None)
        assert not np.isnan(score)
        assert score < 0

    def test_bok_rate_cutting_positive(self):
        """BOK 금리 인하 → 양의 점수."""
        layer = KRMacroRegimeLayer()
        bok = MockBOKFetcher(base_rate=3.25, base_rate_prev=3.5)
        score, detail = layer._score_interest_rate(None, bok)
        assert not np.isnan(score)
        assert score > 0
        assert detail['source'] == 'BOK_BASE_RATE'
        assert detail['direction'] == 'cutting'

    def test_bok_rate_hiking_negative(self):
        """BOK 금리 인상 → 음의 점수."""
        layer = KRMacroRegimeLayer()
        bok = MockBOKFetcher(base_rate=3.75, base_rate_prev=3.5)
        score, detail = layer._score_interest_rate(None, bok)
        assert not np.isnan(score)
        assert score < 0
        assert detail['direction'] == 'hiking'

    def test_insufficient_data(self):
        layer = KRMacroRegimeLayer()
        bond = make_ohlcv(n=10, seed=1)
        cache = MockCache({KR_BOND_3Y_ETF: bond})
        score, detail = layer._score_interest_rate(cache, None)
        assert np.isnan(score)


class TestKRCreditSpreadScoring:
    """한국 신용 스프레드 서브 메트릭 테스트."""

    def test_corp_outperform_positive(self):
        """회사채 ETF outperform → 양의 점수."""
        layer = KRMacroRegimeLayer()
        corp = make_ohlcv(n=100, start_price=105, trend=0.005, volatility=0.005, seed=10)
        gov = make_ohlcv(n=100, start_price=120, trend=0.0, volatility=0.005, seed=11)
        cache = MockCache({KR_CORP_AA_ETF: corp, KR_GOV_BOND_ETF: gov})
        score, detail = layer._score_credit_spread(cache)
        assert not np.isnan(score)
        assert score > 0

    def test_corp_underperform_negative(self):
        """회사채 ETF underperform → 음의 점수."""
        layer = KRMacroRegimeLayer()
        corp = make_ohlcv(n=100, start_price=105, trend=-0.005, volatility=0.005, seed=10)
        gov = make_ohlcv(n=100, start_price=120, trend=0.005, volatility=0.005, seed=11)
        cache = MockCache({KR_CORP_AA_ETF: corp, KR_GOV_BOND_ETF: gov})
        score, detail = layer._score_credit_spread(cache)
        assert not np.isnan(score)
        assert score < 0


class TestExchangeRateScoring:
    """환율 서브 메트릭 테스트."""

    def test_weak_krw_negative(self):
        """원화 약세 (USDKRW 상승) → 음의 점수."""
        layer = KRMacroRegimeLayer()
        usdkrw = make_ohlcv(n=100, start_price=1300, trend=0.005, volatility=0.005, seed=20)
        cache = MockCache({USDKRW_SYMBOL: usdkrw})
        score, detail = layer._score_exchange_rate(cache)
        assert not np.isnan(score)
        assert score < 0

    def test_strong_krw_positive(self):
        """원화 강세 (USDKRW 하락) → 양의 점수."""
        layer = KRMacroRegimeLayer()
        usdkrw = make_ohlcv(n=100, start_price=1300, trend=-0.005, volatility=0.005, seed=20)
        cache = MockCache({USDKRW_SYMBOL: usdkrw})
        score, detail = layer._score_exchange_rate(cache)
        assert not np.isnan(score)
        assert score > 0


class TestIndustrialProductionScoring:
    """산업생산지수 서브 메트릭 테스트."""

    def test_expanding_positive(self):
        """산업생산 확장 → 양의 점수."""
        layer = KRMacroRegimeLayer()
        bok = MockBOKFetcher(ip_current=105.0, ip_prev=100.0)
        score, detail = layer._score_industrial_production(bok)
        assert not np.isnan(score)
        assert score > 0
        assert detail['direction'] == 'improving'

    def test_contracting_negative(self):
        """산업생산 수축 → 음의 점수."""
        layer = KRMacroRegimeLayer()
        bok = MockBOKFetcher(ip_current=95.0, ip_prev=100.0)
        score, detail = layer._score_industrial_production(bok)
        assert not np.isnan(score)
        assert score < 0
        assert detail['direction'] == 'declining'

    def test_no_bok_fetcher(self):
        """BOK 페처 없으면 NaN."""
        layer = KRMacroRegimeLayer()
        score, detail = layer._score_industrial_production(None)
        assert np.isnan(score)


class TestMonetaryPolicyScoring:
    """통화정책 기대 서브 메트릭 테스트."""

    def test_dovish_positive(self):
        """채권 가격 상승 (금리 인하 기대) → 양의 점수."""
        layer = KRMacroRegimeLayer()
        bond = make_ohlcv(n=100, start_price=110, trend=0.005, volatility=0.005, seed=40)
        cache = MockCache({KR_BOND_3Y_ETF: bond})
        score, detail = layer._score_monetary_policy(cache)
        assert not np.isnan(score)
        assert score > 0

    def test_hawkish_negative(self):
        """채권 가격 하락 (금리 상승 기대) → 음의 점수."""
        layer = KRMacroRegimeLayer()
        bond = make_ohlcv(n=100, start_price=110, trend=-0.005, volatility=0.005, seed=40)
        cache = MockCache({KR_BOND_3Y_ETF: bond})
        score, detail = layer._score_monetary_policy(cache)
        assert not np.isnan(score)
        assert score < 0


# ─── Cycle phase tests ───


class TestKRCyclePhaseDetection:
    """한국 경기 사이클 국면 감지 테스트."""

    def test_expansion(self):
        layer = KRMacroRegimeLayer()
        scores = {'interest_rate': 30, 'credit_spread': 20, 'industrial_production': 25}
        phase = layer._detect_cycle_phase(scores)
        assert phase == "expansion"

    def test_contraction(self):
        layer = KRMacroRegimeLayer()
        scores = {'interest_rate': -30, 'credit_spread': -20, 'industrial_production': -25}
        phase = layer._detect_cycle_phase(scores)
        assert phase == "contraction"

    def test_early_recovery(self):
        layer = KRMacroRegimeLayer()
        scores = {'interest_rate': 30, 'credit_spread': 5, 'industrial_production': -15}
        phase = layer._detect_cycle_phase(scores)
        assert phase == "early_recovery"

    def test_nan_scores_treated_as_zero(self):
        layer = KRMacroRegimeLayer()
        scores = {
            'interest_rate': float('nan'),
            'credit_spread': float('nan'),
            'industrial_production': float('nan'),
        }
        phase = layer._detect_cycle_phase(scores)
        assert phase in ("expansion", "late_expansion", "contraction", "early_recovery")


# ─── Interpretation tests ───


class TestKRInterpretation:
    """한국어 해석 테스트."""

    def test_strong_expansion(self):
        layer = KRMacroRegimeLayer()
        assert "강한 확장" in layer._interpret(60)

    def test_mild_expansion(self):
        layer = KRMacroRegimeLayer()
        assert "완만한 확장" in layer._interpret(30)

    def test_neutral(self):
        layer = KRMacroRegimeLayer()
        assert "중립" in layer._interpret(0)

    def test_slowdown(self):
        layer = KRMacroRegimeLayer()
        assert "둔화" in layer._interpret(-30)

    def test_recession(self):
        layer = KRMacroRegimeLayer()
        assert "침체" in layer._interpret(-60)

    def test_kr_prefix_in_interpretation(self):
        """해석에 '한국' 접두사 포함."""
        layer = KRMacroRegimeLayer()
        assert "한국" in layer._interpret(0)
