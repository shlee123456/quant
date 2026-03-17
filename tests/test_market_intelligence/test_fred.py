"""
Tests for FRED data integration (Phase 4).

FRED API를 primary 데이터 소스로 사용하고, ETF 프록시로 폴백하는 로직을 검증합니다.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from trading_bot.market_intelligence.fred_fetcher import FREDDataFetcher, FRED_SERIES
from trading_bot.market_intelligence.data_fetcher import MarketDataCache
from trading_bot.market_intelligence.layer1_macro_regime import MacroRegimeLayer

from .conftest import MockCache, make_ohlcv


# ─── Helper ───

def _make_fred_series(n: int = 100, start: float = 1.0, trend: float = 0.01, seed: int = 42) -> pd.Series:
    """테스트용 FRED 시계열 생성."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq='B')
    values = start + np.cumsum(rng.normal(trend, 0.05, n))
    return pd.Series(values, index=dates)


class FREDMockCache(MockCache):
    """FRED 데이터를 지원하는 MockCache."""

    def __init__(self, data=None, fred_data=None):
        super().__init__(data)
        self._fred_data = fred_data or {}

    def get_fred(self, key: str):
        return self._fred_data.get(key)


# ─── FREDDataFetcher tests ───


class TestFREDDataFetcherInit:
    """FREDDataFetcher 초기화 테스트."""

    def test_disabled_without_key(self):
        """API 키가 없으면 is_available=False."""
        with patch.dict('os.environ', {}, clear=True):
            fetcher = FREDDataFetcher(api_key=None)
        assert fetcher.is_available is False

    def test_disabled_without_package(self):
        """fredapi 미설치 시 graceful 비활성화."""
        with patch.dict('os.environ', {'FRED_API_KEY': 'test_key'}):
            with patch('builtins.__import__', side_effect=_import_no_fredapi):
                fetcher = FREDDataFetcher(api_key='test_key')
        assert fetcher.is_available is False

    def test_enabled_with_key_and_package(self):
        """API 키 + fredapi 패키지 있으면 활성화."""
        mock_fred_cls = MagicMock()
        mock_fred_instance = MagicMock()
        mock_fred_cls.return_value = mock_fred_instance

        with patch.dict('sys.modules', {'fredapi': MagicMock(Fred=mock_fred_cls)}):
            fetcher = FREDDataFetcher(api_key='test_key')

        assert fetcher.is_available is True


class TestFREDFetchSeries:
    """fetch_series() 테스트."""

    def test_returns_none_when_unavailable(self):
        """비활성 상태에서 None 반환."""
        fetcher = FREDDataFetcher(api_key=None)
        assert fetcher.fetch_series('T10Y2Y') is None

    def test_fetch_series_mock(self):
        """Mock fredapi로 시리즈 반환 확인."""
        mock_data = _make_fred_series(50, start=0.5)
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = mock_data

        fetcher = FREDDataFetcher.__new__(FREDDataFetcher)
        fetcher._api_key = 'test'
        fetcher._fred = mock_fred
        fetcher._available = True

        result = fetcher.fetch_series('T10Y2Y', observation_start='2024-01-01')
        assert result is not None
        assert len(result) == 50
        mock_fred.get_series.assert_called_once_with(
            'T10Y2Y', observation_start='2024-01-01'
        )

    def test_fetch_series_handles_exception(self):
        """API 예외 시 None 반환."""
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = Exception("API error")

        fetcher = FREDDataFetcher.__new__(FREDDataFetcher)
        fetcher._api_key = 'test'
        fetcher._fred = mock_fred
        fetcher._available = True

        result = fetcher.fetch_series('T10Y2Y')
        assert result is None


class TestFREDFetchAll:
    """fetch_all() 테스트."""

    def test_returns_empty_when_unavailable(self):
        """비활성 상태에서 빈 dict 반환."""
        fetcher = FREDDataFetcher(api_key=None)
        assert fetcher.fetch_all() == {}

    def test_fetch_all_mock(self):
        """Mock fredapi로 모든 시리즈 로드."""
        mock_fred = MagicMock()

        # 각 시리즈에 대해 데이터 반환
        def mock_get_series(series_id, **kwargs):
            return _make_fred_series(30, start=1.0, seed=hash(series_id) % 1000)

        mock_fred.get_series.return_value = _make_fred_series(30)
        mock_fred.get_series.side_effect = mock_get_series

        fetcher = FREDDataFetcher.__new__(FREDDataFetcher)
        fetcher._api_key = 'test'
        fetcher._fred = mock_fred
        fetcher._available = True

        results = fetcher.fetch_all()
        assert len(results) == len(FRED_SERIES)
        for key in FRED_SERIES:
            assert key in results
            assert isinstance(results[key], pd.Series)


# ─── MarketDataCache FRED integration tests ───


class TestCacheGetFRED:
    """MarketDataCache.get_fred() 테스트."""

    def test_get_fred_returns_data(self):
        """FRED 데이터가 로드되면 get_fred() 반환."""
        cache = MarketDataCache()
        test_series = _make_fred_series(50)
        cache._fred_data = {'yield_spread': test_series}

        result = cache.get_fred('yield_spread')
        assert result is not None
        assert len(result) == 50

    def test_get_fred_missing_returns_none(self):
        """존재하지 않는 키는 None 반환."""
        cache = MarketDataCache()
        cache._fred_data = {}
        assert cache.get_fred('nonexistent') is None

    def test_get_fred_empty_by_default(self):
        """초기 상태에서 FRED 데이터 없음."""
        cache = MarketDataCache()
        assert cache.get_fred('yield_spread') is None


# ─── Layer 1 FRED primary / ETF fallback tests ───


class TestYieldCurveFRED:
    """수익률 곡선: FRED primary, ETF fallback."""

    def test_fred_primary(self):
        """FRED T10Y2Y 데이터 있으면 FRED 사용."""
        layer = MacroRegimeLayer()

        # steepening 스프레드 (양의 추세)
        fred_spread = _make_fred_series(100, start=0.5, trend=0.02, seed=10)
        cache = FREDMockCache(fred_data={'yield_spread': fred_spread})

        score, detail = layer._score_yield_curve(cache)
        assert not np.isnan(score)
        assert detail['source'] == 'FRED_T10Y2Y'

    def test_etf_fallback_no_fred(self):
        """FRED 없으면 ETF 폴백."""
        layer = MacroRegimeLayer()

        tlt = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=1)
        shy = make_ohlcv(n=100, start_price=80, trend=0.0, volatility=0.005, seed=2)

        # get_fred 지원하지만 데이터 없는 캐시
        cache = FREDMockCache(
            data={'TLT': tlt, 'SHY': shy},
            fred_data={},
        )

        score, detail = layer._score_yield_curve(cache)
        assert not np.isnan(score)
        assert detail.get('source') in ('TNX_FVX', 'TLT_SHY', None)
        # FRED가 아닌 ETF 소스여야 함
        assert detail.get('source') != 'FRED_T10Y2Y'

    def test_etf_fallback_no_get_fred(self):
        """get_fred() 메서드 없는 캐시에서도 정상 작동."""
        layer = MacroRegimeLayer()

        tlt = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=1)
        shy = make_ohlcv(n=100, start_price=80, trend=0.0, volatility=0.005, seed=2)

        # 일반 MockCache (get_fred 없음)
        cache = MockCache({'TLT': tlt, 'SHY': shy})

        score, detail = layer._score_yield_curve(cache)
        assert not np.isnan(score)


class TestCreditSpreadFRED:
    """신용 스프레드: FRED primary, ETF fallback."""

    def test_fred_primary(self):
        """FRED OAS 데이터 있으면 FRED 사용."""
        layer = MacroRegimeLayer()

        # OAS 하락 (신용 개선) = bullish
        fred_oas = _make_fred_series(100, start=400, trend=-2.0, seed=20)
        cache = FREDMockCache(fred_data={'credit_spread': fred_oas})

        score, detail = layer._score_credit_spread(cache)
        assert not np.isnan(score)
        assert detail['source'] == 'FRED_BAMLH0A0HYM2'

    def test_etf_fallback(self):
        """FRED 없으면 HYG/IEI 폴백."""
        layer = MacroRegimeLayer()

        hyg = make_ohlcv(n=100, start_price=80, trend=0.005, volatility=0.005, seed=10)
        iei = make_ohlcv(n=100, start_price=110, trend=0.0, volatility=0.005, seed=11)

        cache = FREDMockCache(
            data={'HYG': hyg, 'IEI': iei},
            fred_data={},
        )

        score, detail = layer._score_credit_spread(cache)
        assert not np.isnan(score)
        assert detail.get('source') != 'FRED_BAMLH0A0HYM2'


class TestManufacturingFRED:
    """제조업: FRED primary, ETF fallback."""

    def test_fred_pmi_expanding(self):
        """PMI > 50 → 양의 점수."""
        layer = MacroRegimeLayer()

        # PMI가 52에서 55로 상승
        dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=10, freq='MS')
        pmi = pd.Series([50, 51, 52, 53, 54, 53, 52, 53, 54, 55], index=dates)

        cache = FREDMockCache(fred_data={'manufacturing': pmi})

        score, detail = layer._score_manufacturing(cache)
        assert score > 0
        assert detail['source'] == 'FRED_NAPM'
        assert detail['current_pmi'] == 55.0
        assert detail['direction'] == 'improving'

    def test_fred_pmi_contracting(self):
        """PMI < 50 → 음의 점수."""
        layer = MacroRegimeLayer()

        dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=10, freq='MS')
        pmi = pd.Series([50, 49, 48, 47, 46, 47, 46, 45, 44, 43], index=dates)

        cache = FREDMockCache(fred_data={'manufacturing': pmi})

        score, detail = layer._score_manufacturing(cache)
        assert score < 0
        assert detail['source'] == 'FRED_NAPM'
        assert detail['direction'] == 'declining'

    def test_etf_fallback(self):
        """FRED 없으면 XLI/IWM/SPY 폴백."""
        layer = MacroRegimeLayer()

        xli = make_ohlcv(n=100, start_price=100, trend=0.005, volatility=0.005, seed=30)
        iwm = make_ohlcv(n=100, start_price=200, trend=0.005, volatility=0.005, seed=31)
        spy = make_ohlcv(n=100, start_price=450, trend=0.001, volatility=0.005, seed=32)

        cache = FREDMockCache(
            data={'XLI': xli, 'IWM': iwm, 'SPY': spy},
            fred_data={},
        )

        score, detail = layer._score_manufacturing(cache)
        assert not np.isnan(score)
        assert detail.get('source') != 'FRED_NAPM'


class TestFedExpectationsFRED:
    """연준 기대: FRED primary, ETF fallback."""

    def test_fred_dgs2_declining(self):
        """2년물 금리 하락 → 양의 점수 (비둘기파)."""
        layer = MacroRegimeLayer()

        # 금리 하락 추세
        fred_dgs2 = _make_fred_series(100, start=5.0, trend=-0.02, seed=40)
        cache = FREDMockCache(fred_data={'fed_rate_2y': fred_dgs2})

        score, detail = layer._score_fed_expectations(cache)
        assert not np.isnan(score)
        assert detail['source'] == 'FRED_DGS2'
        # 금리 하락 = dovish = bullish → 양의 점수
        assert score > 0

    def test_fred_dgs2_rising(self):
        """2년물 금리 상승 → 음의 점수 (매파)."""
        layer = MacroRegimeLayer()

        # 금리 상승 추세
        fred_dgs2 = _make_fred_series(100, start=3.0, trend=0.02, seed=41)
        cache = FREDMockCache(fred_data={'fed_rate_2y': fred_dgs2})

        score, detail = layer._score_fed_expectations(cache)
        assert not np.isnan(score)
        assert detail['source'] == 'FRED_DGS2'
        # 금리 상승 = hawkish = bearish → 음의 점수
        assert score < 0

    def test_etf_fallback(self):
        """FRED 없으면 SHY 폴백."""
        layer = MacroRegimeLayer()

        shy = make_ohlcv(n=100, start_price=82, trend=0.005, volatility=0.005, seed=40)
        cache = FREDMockCache(
            data={'SHY': shy},
            fred_data={},
        )

        score, detail = layer._score_fed_expectations(cache)
        assert not np.isnan(score)
        assert detail.get('source') != 'FRED_DGS2'


# ─── FRED helper method unit tests ───


class TestFREDHelperMethods:
    """FRED 헬퍼 메서드 단위 테스트."""

    def test_yield_curve_fred_score_range(self):
        """_score_yield_curve_fred 점수 범위 -100~100."""
        layer = MacroRegimeLayer()
        spread = _make_fred_series(50, start=0.5, trend=0.01, seed=1)
        score, detail = layer._score_yield_curve_fred(spread)
        assert -100.0 <= score <= 100.0
        assert 'current_spread' in detail
        assert 'ma20_spread' in detail

    def test_credit_spread_fred_score_range(self):
        """_score_credit_spread_fred 점수 범위 -100~100."""
        layer = MacroRegimeLayer()
        oas = _make_fred_series(50, start=400, trend=-1.0, seed=2)
        score, detail = layer._score_credit_spread_fred(oas)
        assert -100.0 <= score <= 100.0
        assert 'current_oas' in detail

    def test_manufacturing_fred_at_50(self):
        """PMI = 50 → 점수 ~ 0."""
        layer = MacroRegimeLayer()
        dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=5, freq='MS')
        pmi = pd.Series([50.0, 50.0, 50.0, 50.0, 50.0], index=dates)
        score, detail = layer._score_manufacturing_fred(pmi)
        assert -15.0 <= score <= 15.0  # 약간의 방향성 영향

    def test_fed_expectations_fred_score_range(self):
        """_score_fed_expectations_fred 점수 범위 -100~100."""
        layer = MacroRegimeLayer()
        dgs2 = _make_fred_series(50, start=4.0, trend=0.0, seed=3)
        score, detail = layer._score_fed_expectations_fred(dgs2)
        assert -100.0 <= score <= 100.0
        assert 'current_yield' in detail


# ─── Import helper for mocking ───


def _import_no_fredapi(name, *args, **kwargs):
    """fredapi import 시 ImportError를 발생시키는 mock."""
    if name == 'fredapi':
        raise ImportError("No module named 'fredapi'")
    return original_import(name, *args, **kwargs)


import builtins
original_import = builtins.__import__
