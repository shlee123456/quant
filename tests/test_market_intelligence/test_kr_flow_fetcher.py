"""
Tests for kr_flow_fetcher.py - KR 투자자 수급 데이터 수집기.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from typing import Dict

from trading_bot.market_intelligence.kr_flow_fetcher import (
    KRFlowFetcher,
    _has_pykrx,
)


# ─── Mock data helpers ───


def _make_mock_flow_df(days: int = 10, foreign_trend: str = 'buying') -> pd.DataFrame:
    """테스트용 수급 DataFrame 생성.

    pykrx.stock.get_market_trading_value_by_date() 반환 형식을 모사합니다.
    """
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=days, freq='B')

    if foreign_trend == 'buying':
        foreign_vals = [1_000_000_000 * (i + 1) for i in range(days)]
        inst_vals = [500_000_000 * (i + 1) for i in range(days)]
    elif foreign_trend == 'selling':
        foreign_vals = [-1_000_000_000 * (i + 1) for i in range(days)]
        inst_vals = [-500_000_000 * (i + 1) for i in range(days)]
    else:  # divergent
        foreign_vals = [1_000_000_000 * (i + 1) for i in range(days)]
        inst_vals = [-500_000_000 * (i + 1) for i in range(days)]

    df = pd.DataFrame({
        '기관합계': inst_vals,
        '기타법인': [100_000_000] * days,
        '개인': [-500_000_000] * days,
        '외국인합계': foreign_vals,
        '전체': [0] * days,
    }, index=dates)

    return df


# ─── Import guard tests ───


class TestKRFlowFetcherImportGuard:
    """pykrx import guard 테스트."""

    def test_has_pykrx_flag_is_bool(self):
        assert isinstance(_has_pykrx, bool)

    def test_is_available_property(self):
        fetcher = KRFlowFetcher()
        assert fetcher.is_available == _has_pykrx

    def test_init_without_pykrx(self):
        """pykrx 없어도 초기화 성공."""
        with patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', False):
            fetcher = KRFlowFetcher()
            assert not fetcher.is_available

    def test_fetch_without_pykrx_returns_none(self):
        """pykrx 미설치 시 fetch_market_flow는 None 반환."""
        with patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', False):
            fetcher = KRFlowFetcher()
            result = fetcher.fetch_market_flow()
            assert result is None


# ─── fetch_market_flow tests ───


class TestFetchMarketFlow:
    """fetch_market_flow() 테스트."""

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_returns_dataframe(self, mock_stock):
        mock_df = _make_mock_flow_df(10)
        mock_stock.get_market_trading_value_by_date.return_value = mock_df

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_flow()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 10

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_empty_dataframe_returns_none(self, mock_stock):
        mock_stock.get_market_trading_value_by_date.return_value = pd.DataFrame()

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_flow()
        assert result is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_exception_returns_none(self, mock_stock):
        mock_stock.get_market_trading_value_by_date.side_effect = Exception("API error")

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_flow()
        assert result is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_caching_prevents_duplicate_calls(self, mock_stock):
        """인스턴스 캐싱: 두 번째 호출은 pykrx를 다시 호출하지 않음."""
        mock_df = _make_mock_flow_df(10)
        mock_stock.get_market_trading_value_by_date.return_value = mock_df

        fetcher = KRFlowFetcher()
        result1 = fetcher.fetch_market_flow()
        result2 = fetcher.fetch_market_flow()

        assert result1 is result2  # 같은 객체
        assert mock_stock.get_market_trading_value_by_date.call_count == 1


# ─── get_latest_summary tests ───


class TestGetLatestSummary:
    """get_latest_summary() 테스트."""

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_summary_structure(self, mock_stock):
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(10)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()

        assert summary is not None
        expected_keys = {
            'date', 'foreign_net_today', 'foreign_net_5d',
            'institutional_net_today', 'institutional_net_5d',
            'foreign_trend', 'institutional_trend', 'consensus',
        }
        assert set(summary.keys()) == expected_keys

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_aligned_buying_consensus(self, mock_stock):
        """외국인+기관 모두 5일 순매수 → aligned_buying."""
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(
            10, foreign_trend='buying'
        )

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'aligned_buying'
        assert summary['foreign_trend'] == 'buying'
        assert summary['institutional_trend'] == 'buying'
        assert summary['foreign_net_5d'] > 0
        assert summary['institutional_net_5d'] > 0

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_aligned_selling_consensus(self, mock_stock):
        """외국인+기관 모두 5일 순매도 → aligned_selling."""
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(
            10, foreign_trend='selling'
        )

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'aligned_selling'
        assert summary['foreign_trend'] == 'selling'
        assert summary['institutional_trend'] == 'selling'

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_divergent_consensus(self, mock_stock):
        """외국인 매수, 기관 매도 → divergent."""
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(
            10, foreign_trend='divergent'
        )

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'divergent'

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_net_values_are_int(self, mock_stock):
        """순매수 값은 정수형."""
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(10)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()

        assert isinstance(summary['foreign_net_today'], int)
        assert isinstance(summary['foreign_net_5d'], int)
        assert isinstance(summary['institutional_net_today'], int)
        assert isinstance(summary['institutional_net_5d'], int)

    def test_no_data_returns_none(self):
        """데이터 없으면 None 반환."""
        with patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', False):
            fetcher = KRFlowFetcher()
            summary = fetcher.get_latest_summary()
            assert summary is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_insufficient_data_returns_none(self, mock_stock):
        """1일 데이터만 있으면 None."""
        mock_stock.get_market_trading_value_by_date.return_value = _make_mock_flow_df(1)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()
        assert summary is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_unrecognized_columns_returns_none(self, mock_stock):
        """컬럼명에 외국인/기관이 없으면 None."""
        dates = pd.date_range(end='2026-03-23', periods=10, freq='B')
        bad_df = pd.DataFrame({'colA': range(10), 'colB': range(10)}, index=dates)
        mock_stock.get_market_trading_value_by_date.return_value = bad_df

        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()
        assert summary is None


# ─── Mock data for short selling ───


def _make_mock_short_df(days: int = 10, short_ratio: float = 0.03) -> pd.DataFrame:
    """테스트용 공매도 DataFrame 생성."""
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=days, freq='B')
    total_volume = [1_000_000_000] * days
    short_volume = [int(v * short_ratio) for v in total_volume]

    return pd.DataFrame({
        '공매도': short_volume,
        '매수': [500_000_000] * days,
        '합계': total_volume,
    }, index=dates)


# ─── fetch_market_short_selling tests ───


class TestFetchMarketShortSelling:
    """fetch_market_short_selling() 테스트."""

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_returns_dataframe(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(10)

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_short_selling()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 10

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_empty_returns_none(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = pd.DataFrame()

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_short_selling()
        assert result is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_exception_returns_none(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.side_effect = Exception("error")

        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_short_selling()
        assert result is None

    def test_without_pykrx_returns_none(self):
        with patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', False):
            fetcher = KRFlowFetcher()
            result = fetcher.fetch_market_short_selling()
            assert result is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_caching(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(10)

        fetcher = KRFlowFetcher()
        r1 = fetcher.fetch_market_short_selling()
        r2 = fetcher.fetch_market_short_selling()
        assert r1 is r2
        assert mock_stock.get_shorting_volume_by_date.call_count == 1


# ─── get_short_selling_summary tests ───


class TestGetShortSellingSummary:
    """get_short_selling_summary() 테스트."""

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_summary_structure(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(10)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_short_selling_summary()

        assert summary is not None
        assert set(summary.keys()) == {'short_ratio_today', 'short_ratio_5d_avg', 'trend'}

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_ratio_is_float(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(10, short_ratio=0.05)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_short_selling_summary()

        assert isinstance(summary['short_ratio_today'], float)
        assert isinstance(summary['short_ratio_5d_avg'], float)
        assert 0.0 <= summary['short_ratio_today'] <= 1.0

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_trend_values(self, mock_stock):
        """trend는 increasing, decreasing, stable 중 하나."""
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(10)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_short_selling_summary()

        assert summary['trend'] in ('increasing', 'decreasing', 'stable')

    def test_no_data_returns_none(self):
        with patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', False):
            fetcher = KRFlowFetcher()
            summary = fetcher.get_short_selling_summary()
            assert summary is None

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._has_pykrx', True)
    @patch('trading_bot.market_intelligence.kr_flow_fetcher._pykrx_stock')
    def test_insufficient_data_returns_none(self, mock_stock):
        mock_stock.get_shorting_volume_by_date.return_value = _make_mock_short_df(1)

        fetcher = KRFlowFetcher()
        summary = fetcher.get_short_selling_summary()
        assert summary is None
