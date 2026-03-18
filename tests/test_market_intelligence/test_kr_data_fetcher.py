"""
Tests for kr_data_fetcher.py — KRMarketDataCache with mocked yfinance.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.kr_data_fetcher import (
    KR_LAYER_SYMBOLS,
    KRMarketDataCache,
    _get_kr_all_symbols,
)

from .conftest import MockCache, make_ohlcv


# ─── KR_LAYER_SYMBOLS tests ───


class TestKRLayerSymbols:
    """KR_LAYER_SYMBOLS 상수 테스트."""

    def test_required_categories(self):
        """필수 카테고리가 존재."""
        expected = {
            'indices', 'vix', 'breadth_stocks', 'sectors',
            'bond_proxies', 'sentiment_proxies', 'fx',
        }
        assert expected.issubset(set(KR_LAYER_SYMBOLS.keys()))

    def test_indices_contains_kospi_kosdaq(self):
        """indices에 KOSPI, KOSDAQ 포함."""
        assert '^KS11' in KR_LAYER_SYMBOLS['indices']
        assert '^KQ11' in KR_LAYER_SYMBOLS['indices']

    def test_vix_contains_vkospi(self):
        """vix에 VKOSPI 포함."""
        assert '^VKOSPI' in KR_LAYER_SYMBOLS['vix']

    def test_breadth_stocks_count(self):
        """breadth_stocks가 25개."""
        assert len(KR_LAYER_SYMBOLS['breadth_stocks']) == 25

    def test_sectors_count(self):
        """sectors가 8개."""
        assert len(KR_LAYER_SYMBOLS['sectors']) == 8

    def test_bond_proxies_count(self):
        """bond_proxies가 2개."""
        assert len(KR_LAYER_SYMBOLS['bond_proxies']) == 2

    def test_fx_contains_usdkrw(self):
        """fx에 USDKRW=X 포함."""
        assert 'USDKRW=X' in KR_LAYER_SYMBOLS['fx']

    def test_all_symbols_are_strings(self):
        """모든 심볼이 문자열."""
        for category, symbols in KR_LAYER_SYMBOLS.items():
            for sym in symbols:
                assert isinstance(sym, str), f"{category}: {sym}"

    def test_breadth_stocks_are_kr_tickers(self):
        """breadth_stocks 심볼이 .KS 접미사를 가짐."""
        for sym in KR_LAYER_SYMBOLS['breadth_stocks']:
            assert sym.endswith('.KS'), f"{sym}은 .KS로 끝나지 않음"

    def test_samsung_electronics_included(self):
        """삼성전자(005930.KS) 포함 확인."""
        assert '005930.KS' in KR_LAYER_SYMBOLS['breadth_stocks']


# ─── _get_kr_all_symbols tests ───


class TestGetKRAllSymbols:
    """_get_kr_all_symbols() 테스트."""

    def test_no_duplicates(self):
        """중복 없이 합산."""
        all_syms = _get_kr_all_symbols()
        assert len(all_syms) == len(set(all_syms))

    def test_includes_key_symbols(self):
        """주요 심볼 포함 확인."""
        all_syms = _get_kr_all_symbols()
        for sym in ['^KS11', '^KQ11', '^VKOSPI', '005930.KS', 'USDKRW=X']:
            assert sym in all_syms

    def test_returns_list(self):
        """리스트 타입 반환."""
        result = _get_kr_all_symbols()
        assert isinstance(result, list)

    def test_total_count(self):
        """전체 심볼 수가 합리적 범위."""
        all_syms = _get_kr_all_symbols()
        # indices(2) + vix(1) + breadth(25) + sectors(8) + bond(2) + sentiment(1) + fx(1) = 40
        # GLD는 sentiment_proxies에 있어 US 심볼과 겹칠 수 있지만 KR에선 독립
        assert len(all_syms) >= 35


# ─── KRMarketDataCache tests ───


class TestKRMarketDataCache:
    """KRMarketDataCache 클래스 테스트."""

    def test_init_defaults(self):
        """기본 초기화 값 확인."""
        cache = KRMarketDataCache()
        assert cache.period == '1y'
        assert cache.interval == '1d'
        assert cache.is_fetched is False
        assert cache.available_symbols == []

    def test_init_custom(self):
        """커스텀 초기화 값."""
        cache = KRMarketDataCache(period='6mo', interval='1wk')
        assert cache.period == '6mo'
        assert cache.interval == '1wk'

    def test_inherits_market_data_cache(self):
        """MarketDataCache를 상속."""
        from trading_bot.market_intelligence.data_fetcher import MarketDataCache
        cache = KRMarketDataCache()
        assert isinstance(cache, MarketDataCache)

    def test_get_before_fetch(self):
        """fetch() 전에 get()하면 None."""
        cache = KRMarketDataCache()
        assert cache.get('^KS11') is None

    def test_get_many_before_fetch(self):
        """fetch() 전에 get_many()하면 빈 딕셔너리."""
        cache = KRMarketDataCache()
        assert cache.get_many(['^KS11', '^KQ11']) == {}

    def test_get_all_symbols_override(self):
        """_get_all_symbols()가 KR 심볼 반환."""
        cache = KRMarketDataCache()
        symbols = cache._get_all_symbols()
        assert '^KS11' in symbols
        assert '005930.KS' in symbols
        # US 전용 심볼은 없어야 함
        assert 'SPY' not in symbols
        assert 'AAPL' not in symbols

    @patch('trading_bot.market_intelligence.kr_data_fetcher.yf', create=True)
    def test_fetch_empty_result(self, mock_yf):
        """yf.download()이 빈 결과를 반환."""
        import sys
        # yfinance mock
        mock_module = MagicMock()
        mock_module.download.return_value = pd.DataFrame()
        sys.modules['yfinance'] = mock_module

        try:
            cache = KRMarketDataCache()
            result = cache.fetch()
            assert result is False
        finally:
            del sys.modules['yfinance']

    @patch('trading_bot.market_intelligence.kr_data_fetcher.yf', create=True)
    def test_fetch_exception(self, mock_yf):
        """yf.download() 예외 처리."""
        import sys
        mock_module = MagicMock()
        mock_module.download.side_effect = Exception("network error")
        sys.modules['yfinance'] = mock_module

        try:
            cache = KRMarketDataCache()
            result = cache.fetch()
            assert result is False
        finally:
            del sys.modules['yfinance']

    def test_get_bok_returns_none_by_default(self):
        """BOK 데이터 없을 때 None 반환."""
        cache = KRMarketDataCache()
        assert cache.get_bok('base_rate') is None

    def test_get_bok_returns_data(self):
        """BOK 데이터가 있을 때 반환."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2024-01-01', periods=10, freq='MS')
        test_series = pd.Series([3.5] * 10, index=dates)
        cache._bok_data = {'base_rate': test_series}

        result = cache.get_bok('base_rate')
        assert result is not None
        assert len(result) == 10

    def test_get_bok_missing_key(self):
        """존재하지 않는 BOK 키는 None."""
        cache = KRMarketDataCache()
        cache._bok_data = {'base_rate': pd.Series([3.5])}
        assert cache.get_bok('nonexistent') is None


# ─── KOSPI MA200 테스트 ───


class TestKospiMA200:
    """kospi_ma200_status() 테스트."""

    def test_empty_data(self):
        """데이터 없으면 빈 딕셔너리."""
        cache = KRMarketDataCache()
        assert cache.kospi_ma200_status() == {}

    def test_insufficient_data(self):
        """200일 미만 데이터면 빈 딕셔너리."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2024-01-01', periods=100)
        cache._data = {
            '^KS11': pd.DataFrame({
                'Close': np.random.uniform(2500, 2600, 100),
            }, index=dates),
        }
        assert cache.kospi_ma200_status() == {}

    def test_bullish_regime(self):
        """현재가 > MA200 -> long_term_bullish."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2023-01-01', periods=250, freq='B')
        # 강한 상승 추세
        prices = 2500 + np.arange(250) * 2.0
        cache._data = {
            '^KS11': pd.DataFrame({'Close': prices}, index=dates),
        }

        result = cache.kospi_ma200_status()
        assert result != {}
        assert result['above_ma200'] is True
        assert result['regime'] == 'long_term_bullish'
        assert result['distance_pct'] > 0
        assert 'current_price' in result
        assert 'ma200' in result

    def test_bearish_regime(self):
        """현재가 < MA200 -> long_term_bearish."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2023-01-01', periods=250, freq='B')
        # 강한 하락 추세
        prices = 2800 - np.arange(250) * 2.0
        cache._data = {
            '^KS11': pd.DataFrame({'Close': prices}, index=dates),
        }

        result = cache.kospi_ma200_status()
        assert result != {}
        assert result['above_ma200'] is False
        assert result['regime'] == 'long_term_bearish'
        assert result['distance_pct'] < 0

    def test_result_keys(self):
        """반환 딕셔너리 키 확인."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2023-01-01', periods=250, freq='B')
        prices = [2600.0] * 250
        cache._data = {
            '^KS11': pd.DataFrame({'Close': prices}, index=dates),
        }

        result = cache.kospi_ma200_status()
        expected_keys = {'above_ma200', 'current_price', 'ma200', 'distance_pct', 'regime'}
        assert set(result.keys()) == expected_keys

    def test_distance_pct_calculation(self):
        """distance_pct 계산 정확성."""
        cache = KRMarketDataCache()
        dates = pd.date_range('2023-01-01', periods=250, freq='B')
        # 일정한 가격 (MA200 = 가격 자체)
        prices = [2600.0] * 250
        cache._data = {
            '^KS11': pd.DataFrame({'Close': prices}, index=dates),
        }

        result = cache.kospi_ma200_status()
        assert result['distance_pct'] == 0.0
        assert result['current_price'] == 2600.0
        assert result['ma200'] == 2600.0


# ─── freshness 상속 테스트 ───


class TestKRCacheFreshness:
    """부모 클래스로부터 상속받은 freshness 기능 테스트."""

    def test_freshness_multiplier_no_data(self):
        """데이터 없는 심볼은 0.0."""
        cache = KRMarketDataCache()
        assert cache.freshness_multiplier('^KS11') == 0.0

    def test_freshness_multiplier_with_data(self):
        """데이터가 있으면 0.3 이상."""
        cache = KRMarketDataCache()
        dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=10, freq='B')
        cache._data = {
            '^KS11': pd.DataFrame({
                'Close': [2600.0] * 10,
            }, index=dates),
        }
        freshness = cache.freshness_multiplier('^KS11')
        assert 0.3 <= freshness <= 1.0

    def test_available_symbols(self):
        """available_symbols 프로퍼티."""
        cache = KRMarketDataCache()
        cache._data = {
            '^KS11': pd.DataFrame(),
            '005930.KS': pd.DataFrame(),
        }
        syms = cache.available_symbols
        assert set(syms) == {'^KS11', '005930.KS'}


# ─── BOK 통합 테스트 ───


class TestKRCacheBOKIntegration:
    """BOK fetcher 통합 테스트."""

    def test_init_without_bok_fetcher(self):
        """bok_fetcher 없이 초기화."""
        cache = KRMarketDataCache()
        assert cache._bok_fetcher is None
        assert cache._bok_data == {}

    def test_init_with_bok_fetcher(self):
        """bok_fetcher와 함께 초기화."""
        mock_bok = MagicMock()
        mock_bok.is_available = True
        cache = KRMarketDataCache(bok_fetcher=mock_bok)
        assert cache._bok_fetcher is mock_bok
