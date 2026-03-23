"""
Tests for kr_layer2_market_structure.py - 한국 시장 구조 레이어.
"""

import numpy as np
import pandas as pd
import pytest
from typing import Dict, List

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.kr_layer2_market_structure import (
    KR_STRUCTURE_WEIGHTS,
    KRMarketStructureLayer,
    VKOSPI_SYMBOL,
    KR_BREADTH_STOCKS,
    KR_SECTOR_ETFS,
)

from .conftest import MockCache, make_ohlcv


# ─── Fixtures ───


def _make_kr_structure_cache(
    trend: float = 0.001,
    n: int = 250,
    seed: int = 42,
    vkospi_price: float = 18.0,
) -> MockCache:
    """한국 시장 구조 분석용 MockCache 생성."""
    data: Dict[str, pd.DataFrame] = {}

    # VKOSPI (Close 가격이 VIX 수준처럼 사용됨)
    data[VKOSPI_SYMBOL] = make_ohlcv(
        n=n, start_price=vkospi_price, trend=0.0, volatility=0.02, seed=seed
    )

    # 대형주 25개
    for i, sym in enumerate(KR_BREADTH_STOCKS):
        data[sym] = make_ohlcv(
            n=n, start_price=50000 + i * 1000,
            trend=trend, volatility=0.015, seed=seed + 10 + i,
        )

    # 섹터 ETF
    for i, sym in enumerate(KR_SECTOR_ETFS):
        data[sym] = make_ohlcv(
            n=n, start_price=10000 + i * 500,
            trend=trend, volatility=0.015, seed=seed + 50 + i,
        )

    return MockCache(data)


@pytest.fixture
def kr_bullish_structure() -> MockCache:
    return _make_kr_structure_cache(trend=0.002, seed=100, vkospi_price=15.0)


@pytest.fixture
def kr_bearish_structure() -> MockCache:
    return _make_kr_structure_cache(trend=-0.002, seed=200, vkospi_price=30.0)


@pytest.fixture
def empty_cache() -> MockCache:
    return MockCache({})


# ─── Basic tests ───


class TestKRMarketStructureInit:
    """KRMarketStructureLayer 초기화 테스트."""

    def test_default_weights(self):
        layer = KRMarketStructureLayer()
        assert layer.weights == KR_STRUCTURE_WEIGHTS
        assert layer.name == "kr_market_structure"

    def test_custom_weights(self):
        custom = {'vkospi_level': 0.5, 'breadth_50ma': 0.5}
        layer = KRMarketStructureLayer(weights=custom)
        assert layer.weights == custom

    def test_custom_symbols(self):
        layer = KRMarketStructureLayer(
            breadth_symbols=['005930.KS'],
            sector_symbols=['091160.KS'],
        )
        assert layer.breadth_symbols == ['005930.KS']
        assert layer.sector_symbols == ['091160.KS']


# ─── Analyze tests ───


class TestKRMarketStructureAnalyze:
    """KRMarketStructureLayer.analyze() 통합 테스트."""

    def test_returns_layer_result(self, kr_bullish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        assert isinstance(result, LayerResult)
        assert result.layer_name == "kr_market_structure"

    def test_bullish_valid(self, kr_bullish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_bearish_valid(self, kr_bearish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bearish_structure})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_empty_cache_low_confidence(self, empty_cache):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': empty_cache})
        assert result.confidence == 0.0

    def test_none_cache(self):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': None})
        assert isinstance(result, LayerResult)

    def test_metrics_contains_all_sub_scores(self, kr_bullish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        expected_keys = set(KR_STRUCTURE_WEIGHTS.keys())
        assert set(result.metrics.keys()) == expected_keys
        assert 'investor_flow' in result.metrics

    def test_interpretation_is_korean(self, kr_bullish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        assert isinstance(result.interpretation, str)
        assert len(result.interpretation) > 0

    def test_to_dict_serializable(self, kr_bullish_structure):
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert 'layer' in d


# ─── VKOSPI scoring tests ───


class TestVKOSPIScoring:
    """VKOSPI 수준 서브 메트릭 테스트."""

    def test_healthy_vkospi_positive(self):
        """VKOSPI 15 근처 → 양의 점수."""
        layer = KRMarketStructureLayer()
        vkospi = make_ohlcv(n=50, start_price=15.0, trend=0.0, volatility=0.01, seed=1)
        cache = MockCache({VKOSPI_SYMBOL: vkospi})
        score, detail = layer._score_vkospi_level(cache)
        assert not np.isnan(score)
        assert score > 0
        assert detail['source'] == VKOSPI_SYMBOL

    def test_high_vkospi_negative(self):
        """VKOSPI 30+ → 음의 점수 (공포)."""
        layer = KRMarketStructureLayer()
        vkospi = make_ohlcv(n=50, start_price=32.0, trend=0.0, volatility=0.01, seed=1)
        cache = MockCache({VKOSPI_SYMBOL: vkospi})
        score, detail = layer._score_vkospi_level(cache)
        assert not np.isnan(score)
        assert score < 0

    def test_missing_vkospi_nan(self):
        """VKOSPI 데이터 없으면 NaN."""
        layer = KRMarketStructureLayer()
        cache = MockCache({})
        score, detail = layer._score_vkospi_level(cache)
        assert np.isnan(score)

    def test_nonlinear_scoring(self):
        """비선형 스코어링 커브 검증."""
        # 15.0 → 최대 점수 근처
        assert KRMarketStructureLayer._vkospi_nonlinear_score(15.0) == 50.0
        # 30.0 → 매우 부정적
        assert KRMarketStructureLayer._vkospi_nonlinear_score(30.0) == -50.0
        # 45.0+ → 역발상 0 근처
        assert KRMarketStructureLayer._vkospi_nonlinear_score(45.0) == 0.0


# ─── Breadth tests ───


class TestKRBreadthMA:
    """한국 breadth MA 서브 메트릭 테스트."""

    def test_all_above_50ma(self):
        """모든 종목이 50MA 위 → 강한 양의 점수."""
        layer = KRMarketStructureLayer(
            breadth_symbols=['A', 'B', 'C']
        )
        # 강한 상승 추세 (모두 50MA 위)
        data = {
            'A': make_ohlcv(n=100, start_price=100, trend=0.005, seed=1),
            'B': make_ohlcv(n=100, start_price=200, trend=0.005, seed=2),
            'C': make_ohlcv(n=100, start_price=300, trend=0.005, seed=3),
        }
        cache = MockCache(data)
        score, detail = layer._score_breadth_ma(cache, window=50)
        assert not np.isnan(score)
        assert detail['pct_above'] > 50

    def test_no_data_nan(self):
        """데이터 없으면 NaN."""
        layer = KRMarketStructureLayer(breadth_symbols=['MISSING'])
        cache = MockCache({})
        score, detail = layer._score_breadth_ma(cache, window=50)
        assert np.isnan(score)


# ─── Sector breadth tests ───


class TestKRSectorBreadth:
    """KODEX 섹터 ETF breadth 테스트."""

    def test_all_positive(self):
        """모든 섹터가 양의 수익률 → 양의 점수."""
        layer = KRMarketStructureLayer(sector_symbols=['S1', 'S2', 'S3'])
        data = {
            'S1': make_ohlcv(n=50, start_price=100, trend=0.005, seed=1),
            'S2': make_ohlcv(n=50, start_price=100, trend=0.005, seed=2),
            'S3': make_ohlcv(n=50, start_price=100, trend=0.005, seed=3),
        }
        cache = MockCache(data)
        score, detail = layer._score_sector_breadth(cache)
        assert not np.isnan(score)
        assert score > 0

    def test_no_data_nan(self):
        layer = KRMarketStructureLayer(sector_symbols=['MISSING'])
        cache = MockCache({})
        score, detail = layer._score_sector_breadth(cache)
        assert np.isnan(score)


# ─── McClellan proxy tests ───


class TestKRMcClellanProxy:
    """한국 McClellan 프록시 테스트."""

    def test_with_sufficient_data(self):
        """충분한 데이터 → 유효한 점수."""
        layer = KRMarketStructureLayer(sector_symbols=['S1', 'S2', 'S3', 'S4'])
        data = {
            f'S{i}': make_ohlcv(n=100, start_price=100, trend=0.002, seed=i)
            for i in range(1, 5)
        }
        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)
        assert not np.isnan(score)
        assert 'current_oscillator' in detail

    def test_insufficient_data_nan(self):
        """데이터 부족 → NaN."""
        layer = KRMarketStructureLayer(sector_symbols=['S1'])
        data = {'S1': make_ohlcv(n=100, seed=1)}
        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)
        assert np.isnan(score)


# ─── Interpretation tests ───


class TestKRStructureInterpretation:
    """한국어 해석 테스트."""

    def test_healthy_market(self):
        layer = KRMarketStructureLayer()
        interp = layer._interpret(40, {
            'vkospi_level': {'current': 15.0},
            'breadth_50ma': {'pct_above': 72.0},
        })
        assert "양호" in interp
        assert "VKOSPI" in interp

    def test_weak_market(self):
        layer = KRMarketStructureLayer()
        interp = layer._interpret(-40, {
            'vkospi_level': {'current': 30.0},
            'breadth_50ma': {'pct_above': 28.0},
        })
        assert "취약" in interp

    def test_kr_prefix(self):
        """한국 시장 구조라는 표현 포함."""
        layer = KRMarketStructureLayer()
        interp = layer._interpret(0, {
            'vkospi_level': {'current': 20.0},
            'breadth_50ma': {'pct_above': 50.0},
        })
        assert "한국" in interp


# ─── Investor flow scoring tests ───


class TestInvestorFlowScoring:
    """투자자 수급 서브 메트릭 테스트."""

    def test_weights_sum_to_one(self):
        """가중치 합계가 1.0."""
        total = sum(KR_STRUCTURE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_weights_have_six_metrics(self):
        """6개 서브 메트릭 존재."""
        assert len(KR_STRUCTURE_WEIGHTS) == 6
        assert 'investor_flow' in KR_STRUCTURE_WEIGHTS
        assert KR_STRUCTURE_WEIGHTS['investor_flow'] == 0.20

    def test_none_flow_data_returns_nan(self):
        """flow_data=None → NaN 반환."""
        layer = KRMarketStructureLayer()
        score, detail = layer._score_investor_flow(None)
        assert np.isnan(score)
        assert 'error' in detail

    def test_aligned_buying(self):
        """aligned_buying → +80."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 500_000_000_000,
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == 80.0
        assert detail['consensus'] == 'aligned_buying'

    def test_aligned_selling(self):
        """aligned_selling → -80."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_selling',
            'foreign_net_5d': -500_000_000_000,
            'institutional_net_5d': -300_000_000_000,
            'foreign_trend': 'selling',
            'institutional_trend': 'selling',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == -80.0

    def test_foreign_only_buying(self):
        """외국인만 매수, 기관 매도 → +40."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'divergent',
            'foreign_net_5d': 500_000_000_000,
            'institutional_net_5d': -200_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'selling',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == 40.0

    def test_institutional_only_buying(self):
        """기관만 매수, 외국인 매도 → +30."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'divergent',
            'foreign_net_5d': -200_000_000_000,
            'institutional_net_5d': 500_000_000_000,
            'foreign_trend': 'selling',
            'institutional_trend': 'buying',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == 30.0

    def test_foreign_selling(self):
        """외국인 매도, 기관 비매수 → -40."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'divergent',
            'foreign_net_5d': -200_000_000_000,
            'institutional_net_5d': -100_000_000_000,
            'foreign_trend': 'selling',
            'institutional_trend': 'selling',
        }
        # consensus=aligned_selling 이므로 -80
        # 실제로 both selling이면 consensus는 aligned_selling이어야 함
        # divergent + foreign selling + inst not buying → -40
        flow['consensus'] = 'divergent'
        flow['institutional_trend'] = 'selling'
        score, detail = layer._score_investor_flow(flow)
        assert score == -40.0

    def test_magnitude_bonus_positive(self):
        """외국인 5일 순매수 > 1조원 → +20 보너스."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 1_500_000_000_000,  # 1.5조원
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == 100.0  # 80 + 20 = 100, clamped
        assert detail['magnitude_bonus'] == 20.0

    def test_magnitude_bonus_negative(self):
        """외국인 5일 순매도 > 1조원 → -20 보너스."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_selling',
            'foreign_net_5d': -1_500_000_000_000,  # -1.5조원
            'institutional_net_5d': -300_000_000_000,
            'foreign_trend': 'selling',
            'institutional_trend': 'selling',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == -100.0  # -80 + (-20) = -100, clamped
        assert detail['magnitude_bonus'] == -20.0

    def test_no_magnitude_bonus_under_threshold(self):
        """외국인 5일 순매수 < 1조원 → 보너스 없음."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 500_000_000_000,  # 5000억원
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        score, detail = layer._score_investor_flow(flow)
        assert score == 80.0
        assert detail['magnitude_bonus'] == 0.0

    def test_score_clamped_to_range(self):
        """점수는 -100 ~ +100 범위."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 2_000_000_000_000,
            'institutional_net_5d': 1_000_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        score, _ = layer._score_investor_flow(flow)
        assert -100.0 <= score <= 100.0

    def test_analyze_with_flow_data(self, kr_bullish_structure):
        """analyze()에 kr_flow_data 전달 시 investor_flow 포함."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 500_000_000_000,
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        result = layer.analyze({
            'cache': kr_bullish_structure,
            'kr_flow_data': flow,
        })
        assert 'investor_flow' in result.metrics
        assert not np.isnan(result.metrics['investor_flow'])

    def test_analyze_without_flow_data(self, kr_bullish_structure):
        """analyze()에 kr_flow_data 없으면 investor_flow=NaN."""
        layer = KRMarketStructureLayer()
        result = layer.analyze({'cache': kr_bullish_structure})
        assert 'investor_flow' in result.metrics
        assert np.isnan(result.metrics['investor_flow'])


# ─── Short selling bonus tests ───


class TestShortSellingBonus:
    """공매도 보조 시그널 테스트."""

    def test_short_selling_negative_bonus(self):
        """공매도 비율 >= 5% + 외국인 매도 → -5 보너스."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'divergent',
            'foreign_net_5d': -200_000_000_000,
            'institutional_net_5d': 100_000_000_000,
            'foreign_trend': 'selling',
            'institutional_trend': 'buying',
        }
        short = {
            'short_ratio_today': 0.06,
            'short_ratio_5d_avg': 0.05,
            'trend': 'increasing',
        }
        # 기관만 매수(30) + short_bonus(-5) = 25
        score, detail = layer._score_investor_flow(flow, short_data=short)
        assert score == 25.0
        assert detail['short_bonus'] == -5.0

    def test_short_selling_positive_bonus(self):
        """공매도 감소 + 외국인 매수 → +5 보너스."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 500_000_000_000,
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        short = {
            'short_ratio_today': 0.03,
            'short_ratio_5d_avg': 0.04,
            'trend': 'decreasing',
        }
        # aligned_buying(80) + short_bonus(5) = 85
        score, detail = layer._score_investor_flow(flow, short_data=short)
        assert score == 85.0
        assert detail['short_bonus'] == 5.0

    def test_no_short_data_no_bonus(self):
        """short_data=None → 보너스 없음."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 500_000_000_000,
            'institutional_net_5d': 300_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        score, detail = layer._score_investor_flow(flow, short_data=None)
        assert score == 80.0
        assert detail['short_bonus'] == 0.0

    def test_short_bonus_clamped(self):
        """공매도 보너스 포함해도 -100~+100 범위."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'aligned_buying',
            'foreign_net_5d': 2_000_000_000_000,
            'institutional_net_5d': 1_000_000_000_000,
            'foreign_trend': 'buying',
            'institutional_trend': 'buying',
        }
        short = {
            'short_ratio_today': 0.02,
            'short_ratio_5d_avg': 0.03,
            'trend': 'decreasing',
        }
        # 80 + 20(magnitude) + 5(short) = 105, clamped to 100
        score, _ = layer._score_investor_flow(flow, short_data=short)
        assert score == 100.0

    def test_short_data_included_in_details(self):
        """short_data 제공 시 detail에 포함."""
        layer = KRMarketStructureLayer()
        flow = {
            'consensus': 'divergent',
            'foreign_net_5d': 0,
            'institutional_net_5d': 0,
            'foreign_trend': 'buying',
            'institutional_trend': 'selling',
        }
        short = {
            'short_ratio_today': 0.04,
            'short_ratio_5d_avg': 0.04,
            'trend': 'stable',
        }
        _, detail = layer._score_investor_flow(flow, short_data=short)
        assert 'short_data' in detail
        assert detail['short_data']['trend'] == 'stable'
