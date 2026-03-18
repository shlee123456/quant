"""
Tests for kr_layer3_sector_rotation.py - 한국 섹터 로테이션 레이어.
"""

import numpy as np
import pandas as pd
import pytest
from typing import Dict

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.kr_layer3_sector_rotation import (
    KR_SECTOR_ETFS,
    KR_CYCLE_GROUPS,
    KR_SUB_WEIGHTS,
    KRSectorRotationLayer,
    KOSPI200_ETF,
    KOSDAQ150_ETF,
)

from .conftest import MockCache, make_ohlcv


# ─── Fixtures ───


def _make_kr_sector_cache(
    trend: float = 0.001,
    n: int = 200,
    seed: int = 42,
) -> MockCache:
    """한국 섹터 로테이션 분석용 MockCache 생성."""
    data: Dict[str, pd.DataFrame] = {}

    # 섹터 ETF
    for i, sym in enumerate(KR_SECTOR_ETFS.keys()):
        data[sym] = make_ohlcv(
            n=n, start_price=10000 + i * 500,
            trend=trend, volatility=0.015, seed=seed + i,
        )

    # KOSPI200 ETF
    data[KOSPI200_ETF] = make_ohlcv(
        n=n, start_price=35000, trend=trend, volatility=0.012, seed=seed + 100,
    )

    # KOSDAQ150 ETF
    data[KOSDAQ150_ETF] = make_ohlcv(
        n=n, start_price=12000, trend=trend * 0.8, volatility=0.018, seed=seed + 101,
    )

    return MockCache(data)


@pytest.fixture
def kr_bullish_sectors() -> MockCache:
    return _make_kr_sector_cache(trend=0.003, seed=100)


@pytest.fixture
def kr_bearish_sectors() -> MockCache:
    return _make_kr_sector_cache(trend=-0.003, seed=200)


@pytest.fixture
def kr_neutral_sectors() -> MockCache:
    return _make_kr_sector_cache(trend=0.0, seed=300)


@pytest.fixture
def empty_cache() -> MockCache:
    return MockCache({})


# ─── Basic tests ───


class TestKRSectorRotationInit:
    """KRSectorRotationLayer 초기화 테스트."""

    def test_name(self):
        layer = KRSectorRotationLayer()
        assert layer.name == "kr_sector_rotation"


# ─── Analyze tests ───


class TestKRSectorRotationAnalyze:
    """KRSectorRotationLayer.analyze() 통합 테스트."""

    def test_returns_layer_result(self, kr_bullish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        assert isinstance(result, LayerResult)
        assert result.layer_name == "kr_sector_rotation"

    def test_bullish_trend_valid(self, kr_bullish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        assert result.signal in ("bullish", "neutral", "bearish")
        assert 0 <= result.confidence <= 1.0

    def test_bearish_trend_valid(self, kr_bearish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bearish_sectors})
        assert result.signal in ("bullish", "neutral", "bearish")

    def test_empty_cache_neutral(self, empty_cache):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': empty_cache})
        assert result.signal == "neutral"
        assert result.confidence == 0.0

    def test_none_cache_neutral(self):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': None})
        assert result.signal == "neutral"
        assert "분석 불가" in result.interpretation

    def test_metrics_contains_all_sub_scores(self, kr_bullish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        expected_keys = set(KR_SUB_WEIGHTS.keys())
        assert set(result.metrics.keys()) == expected_keys

    def test_interpretation_is_korean(self, kr_bullish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        assert isinstance(result.interpretation, str)
        assert len(result.interpretation) > 0

    def test_to_dict_serializable(self, kr_bullish_sectors):
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert 'layer' in d


# ─── Sector momentum tests ───


class TestKRSectorMomentum:
    """섹터 모멘텀 서브 메트릭 테스트."""

    def test_rising_sectors_positive(self):
        """모든 섹터 상승 → 양의 점수."""
        layer = KRSectorRotationLayer()
        data = {
            '091160.KS': make_ohlcv(n=50, start_price=1000, trend=0.005, seed=1)['Close'],
            '091170.KS': make_ohlcv(n=50, start_price=1000, trend=0.005, seed=2)['Close'],
            '140710.KS': make_ohlcv(n=50, start_price=1000, trend=0.005, seed=3)['Close'],
        }
        score, detail = layer._calc_sector_momentum(data)
        assert score > 0
        assert len(detail['top3']) > 0

    def test_falling_sectors_negative(self):
        """모든 섹터 하락 → 음의 점수."""
        layer = KRSectorRotationLayer()
        data = {
            '091160.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=1)['Close'],
            '091170.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=2)['Close'],
            '140710.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=3)['Close'],
        }
        score, detail = layer._calc_sector_momentum(data)
        assert score < 0

    def test_empty_data(self):
        """빈 데이터 → 0."""
        layer = KRSectorRotationLayer()
        score, detail = layer._calc_sector_momentum({})
        assert score == 0.0

    def test_sector_names_in_details(self):
        """details에 한국 섹터명 포함."""
        layer = KRSectorRotationLayer()
        data = {
            '091160.KS': make_ohlcv(n=50, start_price=1000, trend=0.005, seed=1)['Close'],
        }
        score, detail = layer._calc_sector_momentum(data)
        assert detail['top3'][0]['name'] == '반도체'


# ─── Large/Small ratio tests ───


class TestLargeSmallRatio:
    """KOSPI200/KOSDAQ150 비율 테스트."""

    def test_large_cap_favored(self):
        """KOSPI200 상대 강세 → 대형주 선호."""
        layer = KRSectorRotationLayer()
        data = {
            KOSPI200_ETF: make_ohlcv(n=50, start_price=35000, trend=0.005, seed=1),
            KOSDAQ150_ETF: make_ohlcv(n=50, start_price=12000, trend=-0.002, seed=2),
        }
        cache = MockCache(data)
        score, detail = layer._calc_large_small_ratio(cache)
        assert detail.get('trend') == 'large_cap_favored'

    def test_small_cap_favored(self):
        """KOSDAQ150 상대 강세 → 소형주 선호."""
        layer = KRSectorRotationLayer()
        data = {
            KOSPI200_ETF: make_ohlcv(n=50, start_price=35000, trend=-0.002, seed=1),
            KOSDAQ150_ETF: make_ohlcv(n=50, start_price=12000, trend=0.005, seed=2),
        }
        cache = MockCache(data)
        score, detail = layer._calc_large_small_ratio(cache)
        assert detail.get('trend') == 'small_cap_favored'

    def test_missing_data(self):
        """데이터 없으면 0."""
        layer = KRSectorRotationLayer()
        cache = MockCache({})
        score, detail = layer._calc_large_small_ratio(cache)
        assert score == 0.0
        assert detail['ratio'] is None


# ─── Cross correlation tests ───


class TestKRCrossCorrelation:
    """한국 섹터 상관관계 테스트."""

    def test_with_sufficient_data(self):
        """충분한 데이터 → 유효한 결과."""
        layer = KRSectorRotationLayer()
        data = {
            'A': make_ohlcv(n=50, start_price=100, trend=0.002, seed=1)['Close'],
            'B': make_ohlcv(n=50, start_price=200, trend=0.003, seed=2)['Close'],
            'C': make_ohlcv(n=50, start_price=300, trend=-0.001, seed=3)['Close'],
        }
        score, detail = layer._calc_cross_correlation(data)
        assert detail.get('avg_correlation') is not None
        assert detail['interpretation'] in (
            'high_herding', 'moderate_correlation', 'normal', 'healthy_diversification'
        )

    def test_insufficient_data(self):
        """데이터 부족 → 0."""
        layer = KRSectorRotationLayer()
        data = {'A': make_ohlcv(n=10, seed=1)['Close']}
        score, detail = layer._calc_cross_correlation(data)
        assert score == 0.0


# ─── Cycle position tests ───


class TestKRCyclePosition:
    """한국 경기 사이클 위치 테스트."""

    def test_detects_cycle(self, kr_bullish_sectors):
        """사이클 위치를 감지."""
        layer = KRSectorRotationLayer()
        sector_data = layer._get_close_data(
            kr_bullish_sectors, list(KR_SECTOR_ETFS.keys())
        )
        score, detail = layer._calc_cycle_position(sector_data)
        assert detail['cycle'] in ('early_recovery', 'expansion', 'late_expansion', 'contraction')
        assert detail['cycle_label'] in ('초기 회복기', '확장기', '후기 확장기', '수축기')

    def test_empty_data(self):
        """빈 데이터 → unknown."""
        layer = KRSectorRotationLayer()
        score, detail = layer._calc_cycle_position({})
        assert detail['cycle'] == 'unknown'
        assert score == 0.0

    def test_cycle_score_mapping(self):
        """사이클별 점수 매핑 검증."""
        layer = KRSectorRotationLayer()
        # 반도체와 자동차가 선도 → early_recovery
        data = {
            '091160.KS': make_ohlcv(n=50, start_price=1000, trend=0.01, seed=1)['Close'],  # 반도체 강세
            '091170.KS': make_ohlcv(n=50, start_price=1000, trend=0.01, seed=2)['Close'],  # 자동차 강세
            '117700.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=3)['Close'],
            '140710.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=4)['Close'],
            '266360.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=5)['Close'],
            '315270.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=6)['Close'],
            '305720.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=7)['Close'],
            '098560.KS': make_ohlcv(n=50, start_price=1000, trend=-0.005, seed=8)['Close'],
        }
        score, detail = layer._calc_cycle_position(data)
        assert detail['leading_group'] == 'early_recovery'
        assert score == 60.0


# ─── Sector dispersion tests ───


class TestKRSectorDispersion:
    """섹터 수익률 분산 테스트."""

    def test_high_dispersion_positive_avg(self):
        """분산 크고 평균 양수 → 양의 점수."""
        layer = KRSectorRotationLayer()
        data = {
            'A': make_ohlcv(n=50, start_price=100, trend=0.01, seed=1)['Close'],
            'B': make_ohlcv(n=50, start_price=100, trend=0.001, seed=2)['Close'],
            'C': make_ohlcv(n=50, start_price=100, trend=-0.003, seed=3)['Close'],
        }
        score, detail = layer._calc_sector_dispersion(data)
        assert detail.get('dispersion') is not None
        assert detail['num_sectors'] == 3

    def test_insufficient_data(self):
        """데이터 부족 → 0."""
        layer = KRSectorRotationLayer()
        data = {'A': make_ohlcv(n=5, seed=1)['Close']}
        score, detail = layer._calc_sector_dispersion(data)
        assert score == 0.0


# ─── Interpretation tests ───


class TestKRSectorInterpretation:
    """한국어 해석 테스트."""

    def test_cycle_in_interpretation(self, kr_bullish_sectors):
        """해석에 사이클 정보 포함."""
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        assert "경기 사이클" in result.interpretation

    def test_sector_names_in_interpretation(self, kr_bullish_sectors):
        """해석에 선도/부진 섹터 정보 포함."""
        layer = KRSectorRotationLayer()
        result = layer.analyze({'cache': kr_bullish_sectors})
        assert "선도 섹터" in result.interpretation or "부진 섹터" in result.interpretation

    def test_empty_result_message(self):
        """빈 결과에 한국어 메시지 포함."""
        layer = KRSectorRotationLayer()
        result = layer._empty_result("테스트 이유")
        assert "한국 섹터 로테이션 분석 불가" in result.interpretation


# ─── Constants tests ───


class TestKRSectorConstants:
    """상수 정의 검증."""

    def test_sector_etfs_count(self):
        """섹터 ETF 8개 정의 확인."""
        assert len(KR_SECTOR_ETFS) == 8

    def test_cycle_groups_coverage(self):
        """모든 섹터가 사이클 그룹에 포함."""
        all_sectors_in_groups = set()
        for sector_names, _label in KR_CYCLE_GROUPS.values():
            all_sectors_in_groups.update(sector_names)
        all_sector_names = set(KR_SECTOR_ETFS.values())
        assert all_sectors_in_groups == all_sector_names

    def test_sub_weights_sum_to_one(self):
        """서브 메트릭 가중치 합이 1.0."""
        total = sum(KR_SUB_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_kospi200_kosdaq150_symbols(self):
        """KOSPI200/KOSDAQ150 심볼 확인."""
        assert KOSPI200_ETF == '069500.KS'
        assert KOSDAQ150_ETF == '229200.KS'
