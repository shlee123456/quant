"""데이터 품질 (freshness + completeness) 통합 테스트."""

import math
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from trading_bot.market_intelligence.base_layer import LayerResult
from trading_bot.market_intelligence.data_fetcher import MarketDataCache
from trading_bot.market_intelligence.market_analysis_prompt import (
    _build_data_quality_callout,
)
from .conftest import MockCache, make_trending_cache


# ── LayerResult 새 필드 테스트 ──

class TestLayerResultNewFields:
    def test_default_values(self):
        """기본값 확인: 기존 코드 호환."""
        r = LayerResult(
            layer_name="test", score=10.0, signal="bullish", confidence=0.8
        )
        assert r.avg_freshness == 1.0
        assert r.data_symbols_used == 0
        assert r.data_symbols_expected == 0

    def test_to_dict_has_new_keys(self):
        """to_dict()에 avg_freshness, data_completeness 키 존재."""
        r = LayerResult(
            layer_name="test", score=10.0, signal="bullish", confidence=0.8,
            avg_freshness=0.85, data_symbols_used=4, data_symbols_expected=5,
        )
        d = r.to_dict()
        assert 'avg_freshness' in d
        assert d['avg_freshness'] == 0.85
        assert 'data_completeness' in d
        assert d['data_completeness'] == 0.8  # 4/5

    def test_data_completeness_zero_expected(self):
        """data_symbols_expected=0일 때 ZeroDivision 방지."""
        r = LayerResult(
            layer_name="test", score=0.0, signal="neutral", confidence=0.0,
            data_symbols_used=0, data_symbols_expected=0,
        )
        d = r.to_dict()
        assert d['data_completeness'] == 0.0


# ── MarketDataCache freshness 테스트 ──

class TestCacheFreshness:
    def _make_cache_with_data(self, days_old: int = 0) -> MarketDataCache:
        """지정된 일수만큼 오래된 데이터를 가진 캐시 생성."""
        cache = MarketDataCache()
        end_date = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=days_old)
        dates = pd.date_range(end=end_date, periods=100, freq='B')
        df = pd.DataFrame(
            {'Close': np.random.randn(100).cumsum() + 100},
            index=dates,
        )
        cache._data = {'TEST': df}
        cache._fred_data = {}
        return cache

    def test_avg_freshness_excludes_missing(self):
        """데이터 없는 심볼은 평균에서 제외."""
        cache = self._make_cache_with_data(days_old=0)
        result = cache.avg_freshness_for_symbols(['TEST', 'MISSING1', 'MISSING2'])
        assert result == pytest.approx(1.0, abs=0.1)

    def test_avg_freshness_all_missing(self):
        """모든 심볼에 데이터 없으면 1.0."""
        cache = MarketDataCache()
        cache._data = {}
        result = cache.avg_freshness_for_symbols(['A', 'B', 'C'])
        assert result == 1.0

    def test_fred_freshness_daily_series(self):
        """일간 FRED 시리즈: 3일 경과 → 0.7."""
        cache = MarketDataCache()
        cache._fred_data = {}
        end_date = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=3)
        dates = pd.date_range(end=end_date, periods=50, freq='D')
        cache._fred_data['yield_spread'] = pd.Series(np.random.randn(50), index=dates)
        assert cache.fred_freshness('yield_spread') == pytest.approx(0.7, abs=0.05)

    def test_fred_freshness_weekly_series(self):
        """주간 FRED 시리즈: 10일 경과 → 0.5."""
        cache = MarketDataCache()
        cache._fred_data = {}
        end_date = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=10)
        dates = pd.date_range(end=end_date, periods=50, freq='D')
        cache._fred_data['unemployment'] = pd.Series(np.random.randn(50), index=dates)
        assert cache.fred_freshness('unemployment') == pytest.approx(0.5, abs=0.05)

    def test_fred_freshness_monthly_series(self):
        """월간 FRED 시리즈: 20일 경과 → 0.6."""
        cache = MarketDataCache()
        cache._fred_data = {}
        end_date = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=20)
        dates = pd.date_range(end=end_date, periods=50, freq='D')
        cache._fred_data['manufacturing'] = pd.Series(np.random.randn(50), index=dates)
        assert cache.fred_freshness('manufacturing') == pytest.approx(0.6, abs=0.05)

    def test_fred_freshness_no_data(self):
        """FRED 데이터 없으면 0.0."""
        cache = MarketDataCache()
        cache._fred_data = {}
        assert cache.fred_freshness('nonexistent') == 0.0


# ── 레이어 freshness 테스트 ──

class TestLayerFreshness:
    def test_each_layer_populates_freshness(self, bullish_cache):
        """5개 레이어 각각 avg_freshness > 0 확인."""
        from trading_bot.market_intelligence.layer1_macro_regime import MacroRegimeLayer
        from trading_bot.market_intelligence.layer2_market_structure import MarketStructureLayer
        from trading_bot.market_intelligence.layer3_sector_rotation import SectorRotationLayer
        from trading_bot.market_intelligence.layer4_technicals import TechnicalsLayer
        from trading_bot.market_intelligence.layer5_sentiment import SentimentLayer

        context = {
            'cache': bullish_cache,
            'stocks': {},
            'news': None,
            'fear_greed': None,
            'stock_symbols': ['AAPL', 'MSFT'],
        }

        layers = [
            MacroRegimeLayer(),
            MarketStructureLayer(),
            SectorRotationLayer(),
            TechnicalsLayer(),
            SentimentLayer(),
        ]

        for layer in layers:
            result = layer.analyze(context)
            assert result.avg_freshness > 0, f"{result.layer_name} freshness should be > 0"
            assert result.avg_freshness <= 1.0, f"{result.layer_name} freshness should be <= 1.0"

    def test_empty_result_defaults(self):
        """Layer 3/4 _empty_result: 기본값 유지."""
        from trading_bot.market_intelligence.layer3_sector_rotation import SectorRotationLayer
        from trading_bot.market_intelligence.layer4_technicals import TechnicalsLayer

        l3 = SectorRotationLayer()
        r3 = l3._empty_result("test reason")
        assert r3.score == 0.0
        assert r3.confidence == 0.0
        assert r3.avg_freshness == 1.0  # 기본값

        l4 = TechnicalsLayer()
        r4 = l4._empty_result("test reason")
        assert r4.score == 0.0
        assert r4.confidence == 0.0
        assert r4.avg_freshness == 1.0  # 기본값


# ── Notion callout 테스트 ──

class TestDataQualityCallout:
    def test_green_callout(self):
        """완전 + 신선 → 녹색 callout."""
        intel = {
            'data_quality': {
                'layer_completeness': 1.0,
                'avg_freshness': 0.9,
                'layers_contributing': ['a', 'b', 'c', 'd', 'e'],
                'layers_missing': [],
            }
        }
        result = _build_data_quality_callout(intel)
        assert '\u2705' in result
        assert 'green_bg' in result

    def test_warning_callout(self):
        """불완전 → 주황 callout."""
        intel = {
            'data_quality': {
                'layer_completeness': 0.6,
                'avg_freshness': 0.7,
                'layers_contributing': ['a', 'b', 'c'],
                'layers_missing': ['macro_regime', 'sentiment'],
            }
        }
        result = _build_data_quality_callout(intel)
        assert '\u26a0\ufe0f' in result
        assert 'orange_bg' in result
        assert '3/5' in result

    def test_no_data_quality(self):
        """data_quality 없으면 빈 문자열."""
        result = _build_data_quality_callout({})
        assert result == ""
