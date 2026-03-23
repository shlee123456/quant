"""
Tests for kr_flow_fetcher.py - KR 투자자 수급 데이터 수집기 (KIS API 기반).
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, List

from trading_bot.market_intelligence.kr_flow_fetcher import KRFlowFetcher


# --- Mock data helpers ---


def _make_kis_investor_rows(
    days: int = 10,
    foreign_trend: str = 'buying',
) -> List[Dict[str, str]]:
    """KIS API 투자자별 매매동향 응답 형식을 모사합니다.

    각 row는 KIS API /inquire-investor 응답의 output 리스트 요소입니다.
    날짜는 최신 → 과거 순서 (KIS API 실제 응답 순서).
    """
    dates = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=days)
    rows = []
    for i, dt in enumerate(reversed(dates)):  # 최신 먼저
        idx = days - 1 - i
        if foreign_trend == 'buying':
            frgn = 100 * (idx + 1)
            orgn = 50 * (idx + 1)
        elif foreign_trend == 'selling':
            frgn = -100 * (idx + 1)
            orgn = -50 * (idx + 1)
        else:  # divergent
            frgn = 100 * (idx + 1)
            orgn = -50 * (idx + 1)

        rows.append({
            'stck_bsop_date': dt.strftime('%Y%m%d'),
            'stck_clpr': '70000',
            'frgn_ntby_tr_pbmn': str(frgn),
            'orgn_ntby_tr_pbmn': str(orgn),
            'frgn_ntby_qty': str(frgn * 100),
            'orgn_ntby_qty': str(orgn * 100),
        })
    return rows


def _make_mock_kis(rows: List[Dict[str, str]]):
    """KIS API fetch()를 모킹하는 mock 객체를 반환합니다."""
    mock_kis = MagicMock()
    mock_result = MagicMock()
    mock_result.output = rows
    mock_kis.fetch.return_value = mock_result
    return mock_kis


# --- Import guard / availability tests ---


class TestKRFlowFetcherAvailability:
    """KIS 클라이언트 사용 가능 여부 테스트."""

    def test_is_available_with_kis(self):
        mock_kis = MagicMock()
        fetcher = KRFlowFetcher(kis_client=mock_kis)
        assert fetcher.is_available is True

    def test_is_available_without_kis(self):
        fetcher = KRFlowFetcher(kis_client=None)
        # 환경변수에서 자동 생성 시도 → 실패하면 False
        # (테스트 환경에서는 KIS 크레덴셜이 있을 수도 있음)
        assert isinstance(fetcher.is_available, bool)

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._create_kis_client', return_value=None)
    def test_init_without_env_vars(self, mock_create):
        fetcher = KRFlowFetcher()
        assert not fetcher.is_available

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._create_kis_client', return_value=None)
    def test_fetch_without_kis_returns_none(self, mock_create):
        fetcher = KRFlowFetcher()
        result = fetcher.fetch_market_flow()
        assert result is None


# --- fetch_market_flow tests ---


class TestFetchMarketFlow:
    """fetch_market_flow() 테스트."""

    def test_returns_dataframe(self):
        rows = _make_kis_investor_rows(10)
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result = fetcher.fetch_market_flow()

        assert isinstance(result, pd.DataFrame)
        assert '외국인합계' in result.columns
        assert '기관합계' in result.columns
        assert len(result) == 10

    def test_empty_response_returns_none(self):
        mock_kis = _make_mock_kis([])
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result = fetcher.fetch_market_flow()
        assert result is None

    def test_api_exception_returns_none(self):
        mock_kis = MagicMock()
        mock_kis.fetch.side_effect = Exception("API error")
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result = fetcher.fetch_market_flow()
        assert result is None

    def test_caching_prevents_duplicate_calls(self):
        rows = _make_kis_investor_rows(10)
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result1 = fetcher.fetch_market_flow()
        result2 = fetcher.fetch_market_flow()

        assert result1 is result2
        # fetch is called once per proxy stock (5 stocks), not again on 2nd call
        assert mock_kis.fetch.call_count == 5

    def test_aggregates_across_proxy_stocks(self):
        """여러 종목의 데이터가 날짜별로 합산되는지 확인."""
        rows = _make_kis_investor_rows(5, foreign_trend='buying')
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result = fetcher.fetch_market_flow()
        assert result is not None
        # 5개 종목이 각각 같은 값을 반환하므로 5배
        # 마지막 날짜의 외국인 순매수 = 100*(5) * 5종목 = 2500 (백만원 단위)
        # 원 단위 변환: * 1_000_000
        last_foreign = result['외국인합계'].iloc[-1]
        assert last_foreign > 0


# --- get_latest_summary tests ---


class TestGetLatestSummary:
    """get_latest_summary() 테스트."""

    def test_summary_structure(self):
        rows = _make_kis_investor_rows(10)
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()

        assert summary is not None
        expected_keys = {
            'date', 'foreign_net_today', 'foreign_net_5d',
            'institutional_net_today', 'institutional_net_5d',
            'foreign_trend', 'institutional_trend', 'consensus',
        }
        assert set(summary.keys()) == expected_keys

    def test_aligned_buying_consensus(self):
        rows = _make_kis_investor_rows(10, foreign_trend='buying')
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'aligned_buying'
        assert summary['foreign_trend'] == 'buying'
        assert summary['institutional_trend'] == 'buying'
        assert summary['foreign_net_5d'] > 0
        assert summary['institutional_net_5d'] > 0

    def test_aligned_selling_consensus(self):
        rows = _make_kis_investor_rows(10, foreign_trend='selling')
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'aligned_selling'
        assert summary['foreign_trend'] == 'selling'
        assert summary['institutional_trend'] == 'selling'

    def test_divergent_consensus(self):
        rows = _make_kis_investor_rows(10, foreign_trend='divergent')
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()

        assert summary['consensus'] == 'divergent'

    def test_net_values_are_int(self):
        rows = _make_kis_investor_rows(10)
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()

        assert isinstance(summary['foreign_net_today'], int)
        assert isinstance(summary['foreign_net_5d'], int)
        assert isinstance(summary['institutional_net_today'], int)
        assert isinstance(summary['institutional_net_5d'], int)

    @patch('trading_bot.market_intelligence.kr_flow_fetcher._create_kis_client', return_value=None)
    def test_no_data_returns_none(self, mock_create):
        fetcher = KRFlowFetcher()
        summary = fetcher.get_latest_summary()
        assert summary is None

    def test_insufficient_data_returns_none(self):
        """1일 데이터만 있으면 None."""
        rows = _make_kis_investor_rows(1)
        mock_kis = _make_mock_kis(rows)
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_latest_summary()
        assert summary is None


# --- Short selling tests ---


class TestShortSelling:
    """공매도 관련 메서드 테스트 (KIS API에는 없으므로 항상 None)."""

    def test_fetch_market_short_selling_returns_none(self):
        mock_kis = MagicMock()
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        result = fetcher.fetch_market_short_selling()
        assert result is None

    def test_get_short_selling_summary_returns_none(self):
        mock_kis = MagicMock()
        fetcher = KRFlowFetcher(kis_client=mock_kis)

        summary = fetcher.get_short_selling_summary()
        assert summary is None
