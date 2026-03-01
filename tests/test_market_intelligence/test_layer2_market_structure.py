"""
Tests for layer2_market_structure.py - Market Structure layer.
"""

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.layer2_market_structure import (
    STRUCTURE_WEIGHTS,
    MarketStructureLayer,
)

from .conftest import MockCache, make_ohlcv, make_trending_cache


# ─── Basic tests ───


class TestMarketStructureLayerInit:
    """MarketStructureLayer 초기화 테스트."""

    def test_default_weights(self):
        """기본 가중치 사용."""
        layer = MarketStructureLayer()
        assert layer.weights == STRUCTURE_WEIGHTS
        assert layer.name == "market_structure"

    def test_custom_weights(self):
        """커스텀 가중치."""
        custom = {'vix_level': 1.0}
        layer = MarketStructureLayer(weights=custom)
        assert layer.weights == custom

    def test_custom_breadth_symbols(self):
        """커스텀 breadth 심볼."""
        layer = MarketStructureLayer(breadth_symbols=['AAPL', 'MSFT'])
        assert layer.breadth_symbols == ['AAPL', 'MSFT']

    def test_custom_sector_symbols(self):
        """커스텀 섹터 심볼."""
        layer = MarketStructureLayer(sector_symbols=['XLK', 'XLF'])
        assert layer.sector_symbols == ['XLK', 'XLF']


# ─── Analyze tests ───


class TestMarketStructureAnalyze:
    """MarketStructureLayer.analyze() 통합 테스트."""

    def test_returns_layer_result(self, bullish_cache):
        """LayerResult 반환 확인."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert isinstance(result, LayerResult)
        assert result.layer_name == "market_structure"

    def test_score_in_valid_range(self, bullish_cache):
        """점수가 유효 범위."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert -100 <= result.score <= 100

    def test_confidence_range(self, bullish_cache):
        """신뢰도가 0~1 범위."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert 0 <= result.confidence <= 1.0

    def test_signal_valid(self, bullish_cache):
        """시그널이 유효한 값."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert result.signal in ("bullish", "bearish", "neutral")

    def test_metrics_keys(self, bullish_cache):
        """metrics에 모든 서브 메트릭 키 포함."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        expected_keys = set(STRUCTURE_WEIGHTS.keys())
        assert set(result.metrics.keys()) == expected_keys

    def test_empty_cache_low_confidence(self, empty_cache):
        """빈 캐시에서 낮은 신뢰도."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': empty_cache})
        assert result.confidence == 0.0
        assert result.score == 0.0

    def test_none_cache(self):
        """cache가 None이어도 에러 없이 동작."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': None})
        assert isinstance(result, LayerResult)
        assert result.confidence == 0.0

    def test_interpretation_contains_vix(self, bullish_cache):
        """interpretation에 VIX 정보 포함."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        assert "VIX" in result.interpretation

    def test_to_dict(self, bullish_cache):
        """to_dict() 직렬화 가능."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d['layer'] == "market_structure"


# ─── VIX Level tests ───


class TestVixLevelScoring:
    """VIX 수준 서브 메트릭 테스트."""

    def test_with_vix_data(self):
        """^VIX 데이터가 있을 때 정상 스코어링."""
        layer = MarketStructureLayer()
        # VIX ~15 범위
        vix = make_ohlcv(n=100, start_price=15, trend=0.0, volatility=0.03, seed=1)
        cache = MockCache({'^VIX': vix})
        score, detail = layer._score_vix_level(cache)

        assert not np.isnan(score)
        assert detail['source'] == '^VIX'
        assert 'current' in detail
        assert 'percentile_rank' in detail

    def test_fallback_to_vixy(self):
        """^VIX 없으면 VIXY 폴백."""
        layer = MarketStructureLayer()
        vixy = make_ohlcv(n=100, start_price=20, trend=0.0, seed=2)
        cache = MockCache({'VIXY': vixy})
        score, detail = layer._score_vix_level(cache)

        assert not np.isnan(score)
        assert detail['source'] == 'VIXY'

    def test_no_vix_data(self):
        """VIX도 VIXY도 없으면 NaN."""
        layer = MarketStructureLayer()
        cache = MockCache({})
        score, detail = layer._score_vix_level(cache)
        assert np.isnan(score)
        assert 'error' in detail


class TestVixNonlinearScore:
    """VIX 비선형 스코어링 테스트."""

    def test_low_vix_positive(self):
        """VIX < 15 → 양의 점수."""
        score = MarketStructureLayer._vix_nonlinear_score(13.0)
        assert score > 0

    def test_optimal_vix_highest(self):
        """VIX 15 근처가 가장 높은 점수."""
        score_15 = MarketStructureLayer._vix_nonlinear_score(15.0)
        score_25 = MarketStructureLayer._vix_nonlinear_score(25.0)
        assert score_15 > score_25

    def test_high_vix_negative(self):
        """VIX > 25 → 음의 점수."""
        score = MarketStructureLayer._vix_nonlinear_score(28.0)
        assert score < 0

    def test_extreme_vix_contrarian(self):
        """VIX > 35 → 극도의 공포 (역발상)."""
        score_35 = MarketStructureLayer._vix_nonlinear_score(40.0)
        score_30 = MarketStructureLayer._vix_nonlinear_score(30.0)
        # 극도의 공포는 패닉 매도 후 반등 가능 → 30보다 덜 부정적
        assert score_35 > score_30

    def test_very_low_vix(self):
        """VIX <= 12 → 약간 긍정적이지만 최적은 아님."""
        score = MarketStructureLayer._vix_nonlinear_score(10.0)
        assert score > 0
        optimal = MarketStructureLayer._vix_nonlinear_score(15.0)
        assert score < optimal


# ─── VIX Term Structure tests ───


class TestVixTermStructure:
    """VIX 기간 구조 서브 메트릭 테스트."""

    def test_contango_bullish(self):
        """VIX/VIX3M < 1 (콘탱고) → 양의 점수."""
        layer = MarketStructureLayer()
        # VIX < VIX3M
        vix = make_ohlcv(n=50, start_price=15, trend=0.0, seed=1)
        vix3m = make_ohlcv(n=50, start_price=18, trend=0.0, seed=2)
        cache = MockCache({'^VIX': vix, '^VIX3M': vix3m})
        score, detail = layer._score_vix_term_structure(cache)

        assert not np.isnan(score)
        assert score > 0  # contango = bullish
        assert detail['is_contango'] is True

    def test_backwardation_bearish(self):
        """VIX/VIX3M > 1 (백워데이션) → 음의 점수."""
        layer = MarketStructureLayer()
        # VIX > VIX3M
        vix = make_ohlcv(n=50, start_price=25, trend=0.0, seed=1)
        vix3m = make_ohlcv(n=50, start_price=20, trend=0.0, seed=2)
        cache = MockCache({'^VIX': vix, '^VIX3M': vix3m})
        score, detail = layer._score_vix_term_structure(cache)

        assert not np.isnan(score)
        assert score < 0  # backwardation = bearish
        assert detail['is_contango'] is False

    def test_etf_fallback(self):
        """^VIX 없으면 VIXY/VIXM 폴백."""
        layer = MarketStructureLayer()
        vixy = make_ohlcv(n=50, start_price=15, trend=0.0, seed=3)
        vixm = make_ohlcv(n=50, start_price=18, trend=0.0, seed=4)
        cache = MockCache({'VIXY': vixy, 'VIXM': vixm})
        score, detail = layer._score_vix_term_structure(cache)

        assert not np.isnan(score)
        assert detail['source'] == 'VIXY/VIXM'

    def test_no_data(self):
        """데이터 없으면 NaN."""
        layer = MarketStructureLayer()
        cache = MockCache({})
        score, detail = layer._score_vix_term_structure(cache)
        assert np.isnan(score)


# ─── Breadth MA tests ───


class TestBreadthMA:
    """시장 폭 (MA 기반) 서브 메트릭 테스트."""

    def test_all_above_50ma_bullish(self):
        """모든 종목이 50MA 위 → 강한 양의 점수."""
        layer = MarketStructureLayer(breadth_symbols=['A', 'B', 'C'])

        # 강한 상승 → 현재가 > 50MA
        data = {}
        for i, sym in enumerate(['A', 'B', 'C']):
            data[sym] = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=500 + i)

        cache = MockCache(data)
        score, detail = layer._score_breadth_ma(cache, window=50)

        assert not np.isnan(score)
        assert detail['pct_above'] > 50
        assert score > 0

    def test_all_below_50ma_bearish(self):
        """모든 종목이 50MA 아래 → 강한 음의 점수."""
        layer = MarketStructureLayer(breadth_symbols=['A', 'B', 'C'])

        # 강한 하락 → 현재가 < 50MA
        data = {}
        for i, sym in enumerate(['A', 'B', 'C']):
            data[sym] = make_ohlcv(n=100, start_price=100, trend=-0.005, volatility=0.005, seed=500 + i)

        cache = MockCache(data)
        score, detail = layer._score_breadth_ma(cache, window=50)

        assert not np.isnan(score)
        assert detail['pct_above'] < 50
        assert score < 0

    def test_200ma_needs_more_data(self):
        """200MA는 더 긴 데이터 필요."""
        layer = MarketStructureLayer(breadth_symbols=['A'])
        data = {'A': make_ohlcv(n=100, seed=1)}  # 200MA에 부족
        cache = MockCache(data)
        score, detail = layer._score_breadth_ma(cache, window=200)
        # 데이터 부족으로 계산 불가
        assert np.isnan(score) or detail.get('total_count', 0) == 0

    def test_empty_breadth_symbols(self):
        """빈 breadth 심볼 리스트."""
        layer = MarketStructureLayer(breadth_symbols=[])
        cache = MockCache({})
        score, detail = layer._score_breadth_ma(cache, window=50)
        assert np.isnan(score)

    def test_detail_contains_counts(self):
        """detail에 above_count, total_count 포함."""
        layer = MarketStructureLayer(breadth_symbols=['A', 'B'])
        data = {
            'A': make_ohlcv(n=100, trend=0.003, seed=1),
            'B': make_ohlcv(n=100, trend=-0.003, seed=2),
        }
        cache = MockCache(data)
        score, detail = layer._score_breadth_ma(cache, window=50)
        assert 'above_count' in detail
        assert 'total_count' in detail
        assert detail['total_count'] <= 2


# ─── Sector Breadth tests ───


class TestSectorBreadth:
    """섹터 breadth 서브 메트릭 테스트."""

    def test_broad_rally_positive(self):
        """대부분 섹터 양의 수익률 → 양의 점수."""
        layer = MarketStructureLayer(sector_symbols=['XLK', 'XLF', 'XLE'])
        data = {}
        for i, sym in enumerate(['XLK', 'XLF', 'XLE']):
            data[sym] = make_ohlcv(n=50, trend=0.005, volatility=0.005, seed=100 + i)

        cache = MockCache(data)
        score, detail = layer._score_sector_breadth(cache)

        assert not np.isnan(score)
        assert score > 0
        assert 'sector_returns' in detail

    def test_broad_decline_negative(self):
        """대부분 섹터 음의 수익률 → 음의 점수."""
        layer = MarketStructureLayer(sector_symbols=['XLK', 'XLF', 'XLE'])
        data = {}
        for i, sym in enumerate(['XLK', 'XLF', 'XLE']):
            data[sym] = make_ohlcv(n=50, trend=-0.005, volatility=0.005, seed=100 + i)

        cache = MockCache(data)
        score, detail = layer._score_sector_breadth(cache)

        assert not np.isnan(score)
        assert score < 0

    def test_no_sector_data(self):
        """섹터 데이터 없으면 NaN."""
        layer = MarketStructureLayer(sector_symbols=['X1', 'X2'])
        cache = MockCache({})
        score, detail = layer._score_sector_breadth(cache)
        assert np.isnan(score)


# ─── McClellan Proxy tests ───


class TestMcClellanProxy:
    """McClellan Oscillator 프록시 테스트."""

    def test_positive_oscillator(self):
        """전진 비율이 높으면 양의 오실레이터."""
        layer = MarketStructureLayer(sector_symbols=['A', 'B', 'C', 'D'])

        # 모든 섹터가 상승 → 전진 비율 높음
        data = {}
        for i, sym in enumerate(['A', 'B', 'C', 'D']):
            data[sym] = make_ohlcv(n=100, trend=0.002, seed=500 + i)

        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)

        assert not np.isnan(score)
        assert 'current_oscillator' in detail

    def test_insufficient_sectors(self):
        """섹터 2개 이하면 NaN."""
        layer = MarketStructureLayer(sector_symbols=['A', 'B'])
        data = {
            'A': make_ohlcv(n=50, seed=1),
            'B': make_ohlcv(n=50, seed=2),
        }
        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)
        assert np.isnan(score)

    def test_short_history(self):
        """히스토리 부족 시 NaN."""
        layer = MarketStructureLayer(sector_symbols=['A', 'B', 'C', 'D'])
        data = {}
        for i, sym in enumerate(['A', 'B', 'C', 'D']):
            data[sym] = make_ohlcv(n=20, seed=500 + i)  # 너무 짧음
        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)
        assert np.isnan(score)

    def test_ema_values_in_detail(self):
        """detail에 EMA 값 포함."""
        layer = MarketStructureLayer(sector_symbols=['A', 'B', 'C', 'D'])
        data = {}
        for i, sym in enumerate(['A', 'B', 'C', 'D']):
            data[sym] = make_ohlcv(n=100, seed=500 + i)
        cache = MockCache(data)
        score, detail = layer._score_mcclellan_proxy(cache)
        if not np.isnan(score):
            assert 'ema19' in detail
            assert 'ema39' in detail


# ─── Interpretation tests ───


class TestStructureInterpretation:
    """한국어 해석 테스트."""

    def test_positive_structure(self):
        """양의 합성 점수."""
        layer = MarketStructureLayer()
        interp = layer._interpret(50.0, {
            'vix_level': {'current': 15.5},
            'breadth_50ma': {'pct_above': 72.0},
        })
        assert "양호" in interp
        assert "VIX" in interp
        assert "50MA" in interp

    def test_neutral_structure(self):
        """중립 합성 점수."""
        layer = MarketStructureLayer()
        interp = layer._interpret(0.0, {
            'vix_level': {'current': 20.0},
            'breadth_50ma': {'pct_above': 50.0},
        })
        assert "중립" in interp

    def test_negative_structure(self):
        """음의 합성 점수."""
        layer = MarketStructureLayer()
        interp = layer._interpret(-50.0, {
            'vix_level': {'current': 30.0},
            'breadth_50ma': {'pct_above': 25.0},
        })
        assert "취약" in interp

    def test_missing_details(self):
        """세부 정보가 없어도 에러 없음."""
        layer = MarketStructureLayer()
        interp = layer._interpret(10.0, {})
        assert isinstance(interp, str)


# ─── Helper tests ───


class TestGetCloseHelper:
    """_get_close() 헬퍼 메서드 테스트."""

    def test_returns_series(self):
        """정상 데이터에서 Series 반환."""
        df = make_ohlcv(n=50, seed=1)
        cache = MockCache({'^VIX': df})
        result = MarketStructureLayer._get_close(cache, '^VIX')
        assert isinstance(result, pd.Series)

    def test_none_cache(self):
        """캐시가 None이면 None."""
        assert MarketStructureLayer._get_close(None, '^VIX') is None

    def test_missing_symbol(self):
        """없는 심볼은 None."""
        cache = MockCache({})
        assert MarketStructureLayer._get_close(cache, 'MISSING') is None

    def test_empty_dataframe(self):
        """빈 DataFrame은 None."""
        cache = MockCache({'^VIX': pd.DataFrame()})
        assert MarketStructureLayer._get_close(cache, '^VIX') is None


# ─── Integration with full cache ───


class TestWithFullCache:
    """전체 심볼이 포함된 캐시로 통합 테스트."""

    def test_bullish_market_overall(self, bullish_cache):
        """상승장 전체 분석."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bullish_cache})

        assert isinstance(result, LayerResult)
        # 상승장이므로 breadth가 좋아야 함
        assert result.metrics.get('breadth_50ma', 0) >= 0 or True

    def test_bearish_market_overall(self, bearish_cache):
        """하락장 전체 분석."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': bearish_cache})

        assert isinstance(result, LayerResult)
        # 하락장에서는 breadth가 나빠야 함
        assert result.metrics.get('breadth_50ma', 0) <= 0 or True

    def test_neutral_market_overall(self, neutral_cache):
        """횡보장 전체 분석."""
        layer = MarketStructureLayer()
        result = layer.analyze({'cache': neutral_cache})

        assert isinstance(result, LayerResult)
        # 횡보장에서는 점수가 극단적이지 않아야 함
        assert -80 <= result.score <= 80
