"""
Tests for data_fetcher.py - MarketDataCache with mocked yfinance.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.data_fetcher import (
    LAYER_SYMBOLS,
    MarketDataCache,
    _get_all_symbols,
)


# ─── LAYER_SYMBOLS tests ───


class TestLayerSymbols:
    """LAYER_SYMBOLS 상수 테스트."""

    def test_required_categories(self):
        """필수 카테고리가 존재."""
        expected = {
            'yield_curve', 'credit_spread', 'dollar', 'manufacturing',
            'vix', 'vix_etf', 'breadth_stocks', 'factors', 'sectors',
            'indices', 'sentiment_proxies',
        }
        assert expected.issubset(set(LAYER_SYMBOLS.keys()))

    def test_breadth_stocks_count(self):
        """breadth_stocks가 25개."""
        assert len(LAYER_SYMBOLS['breadth_stocks']) == 25

    def test_sectors_count(self):
        """sectors가 11개."""
        assert len(LAYER_SYMBOLS['sectors']) == 11

    def test_all_symbols_are_strings(self):
        """모든 심볼이 문자열."""
        for category, symbols in LAYER_SYMBOLS.items():
            for sym in symbols:
                assert isinstance(sym, str), f"{category}: {sym}"


class TestGetAllSymbols:
    """_get_all_symbols() 테스트."""

    def test_no_duplicates(self):
        """중복 없이 합산."""
        all_syms = _get_all_symbols()
        assert len(all_syms) == len(set(all_syms))

    def test_includes_key_symbols(self):
        """주요 심볼 포함 확인."""
        all_syms = _get_all_symbols()
        for sym in ['SPY', 'TLT', 'HYG', '^VIX', 'AAPL']:
            assert sym in all_syms


# ─── MarketDataCache tests ───


class TestMarketDataCache:
    """MarketDataCache 클래스 테스트."""

    def test_init_defaults(self):
        """기본 초기화 값 확인."""
        cache = MarketDataCache()
        assert cache.period == '6mo'
        assert cache.interval == '1d'
        assert cache.is_fetched is False
        assert cache.available_symbols == []

    def test_init_custom(self):
        """커스텀 초기화 값."""
        cache = MarketDataCache(period='1y', interval='1wk')
        assert cache.period == '1y'
        assert cache.interval == '1wk'

    def test_get_before_fetch(self):
        """fetch() 전에 get()하면 None."""
        cache = MarketDataCache()
        assert cache.get('SPY') is None

    def test_get_many_before_fetch(self):
        """fetch() 전에 get_many()하면 빈 딕셔너리."""
        cache = MarketDataCache()
        assert cache.get_many(['SPY', 'QQQ']) == {}

    @patch('trading_bot.market_intelligence.data_fetcher._has_yfinance', False)
    def test_fetch_without_yfinance(self):
        """yfinance 미설치 시 False 반환."""
        cache = MarketDataCache()
        result = cache.fetch()
        assert result is False
        assert cache.is_fetched is False

    @patch('trading_bot.market_intelligence.data_fetcher._has_yfinance', True)
    @patch('trading_bot.market_intelligence.data_fetcher.yf')
    def test_fetch_empty_result(self, mock_yf):
        """yf.download()이 빈 결과를 반환."""
        mock_yf.download.return_value = pd.DataFrame()
        cache = MarketDataCache()
        result = cache.fetch()
        assert result is False

    @patch('trading_bot.market_intelligence.data_fetcher._has_yfinance', True)
    @patch('trading_bot.market_intelligence.data_fetcher.yf')
    def test_fetch_exception(self, mock_yf):
        """yf.download() 예외 처리."""
        mock_yf.download.side_effect = Exception("network error")
        cache = MarketDataCache()
        result = cache.fetch()
        assert result is False

    @patch('trading_bot.market_intelligence.data_fetcher._has_yfinance', True)
    @patch('trading_bot.market_intelligence.data_fetcher.yf')
    def test_fetch_single_symbol_multiindex(self, mock_yf):
        """복수 심볼 MultiIndex 결과 파싱."""
        dates = pd.date_range('2024-01-01', periods=10)

        # MultiIndex columns 시뮬레이션
        arrays = [
            ['SPY', 'SPY', 'SPY', 'SPY', 'SPY',
             'QQQ', 'QQQ', 'QQQ', 'QQQ', 'QQQ'],
            ['Open', 'High', 'Low', 'Close', 'Volume',
             'Open', 'High', 'Low', 'Close', 'Volume'],
        ]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples)

        data = np.random.RandomState(42).uniform(100, 200, (10, 10))
        df = pd.DataFrame(data, index=dates, columns=index)

        mock_yf.download.return_value = df

        cache = MarketDataCache()
        # 심볼 리스트를 최소화하여 테스트
        result = cache.fetch(stock_symbols=[])
        assert result is True
        assert cache.is_fetched is True

        # SPY, QQQ가 파싱되었는지 확인
        spy_data = cache.get('SPY')
        assert spy_data is not None
        assert 'Close' in spy_data.columns

    @patch('trading_bot.market_intelligence.data_fetcher._has_yfinance', True)
    @patch('trading_bot.market_intelligence.data_fetcher.yf')
    def test_fetch_with_additional_symbols(self, mock_yf):
        """추가 심볼 포함 다운로드."""
        mock_yf.download.return_value = pd.DataFrame()

        cache = MarketDataCache()
        cache.fetch(stock_symbols=['CUSTOM1', 'CUSTOM2'])

        # download 호출 시 추가 심볼 포함 확인
        call_args = mock_yf.download.call_args
        tickers = call_args[1]['tickers']
        assert 'CUSTOM1' in tickers
        assert 'CUSTOM2' in tickers

    def test_parse_single_symbol_result(self):
        """단일 심볼 결과 파싱 테스트."""
        dates = pd.date_range('2024-01-01', periods=10)
        df = pd.DataFrame({
            'Open': np.random.uniform(90, 110, 10),
            'High': np.random.uniform(100, 120, 10),
            'Low': np.random.uniform(80, 100, 10),
            'Close': np.random.uniform(90, 110, 10),
            'Volume': np.random.uniform(1e6, 1e7, 10),
        }, index=dates)

        cache = MarketDataCache()
        cache._parse_download_result(df, ['SPY'])

        assert 'SPY' in cache.available_symbols
        spy = cache.get('SPY')
        assert spy is not None
        assert len(spy) == 10

    def test_get_returns_none_for_missing(self):
        """존재하지 않는 심볼은 None 반환."""
        cache = MarketDataCache()
        cache._data = {'SPY': pd.DataFrame({'Close': [100]})}
        assert cache.get('NONEXISTENT') is None

    def test_get_many_filters_missing(self):
        """get_many()는 존재하지 않는 심볼을 제외."""
        cache = MarketDataCache()
        cache._data = {
            'SPY': pd.DataFrame({'Close': [100]}),
            'QQQ': pd.DataFrame({'Close': [200]}),
        }
        result = cache.get_many(['SPY', 'NONEXISTENT', 'QQQ'])
        assert len(result) == 2
        assert 'SPY' in result
        assert 'QQQ' in result
        assert 'NONEXISTENT' not in result

    def test_available_symbols_property(self):
        """available_symbols 프로퍼티 테스트."""
        cache = MarketDataCache()
        cache._data = {
            'A': pd.DataFrame(),
            'B': pd.DataFrame(),
        }
        syms = cache.available_symbols
        assert set(syms) == {'A', 'B'}
