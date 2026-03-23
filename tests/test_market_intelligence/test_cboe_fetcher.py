"""
Tests for cboe_fetcher.py -- CBOE Put/Call Ratio 데이터 수집기.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.market_intelligence.cboe_fetcher import (
    CBOEFetcher,
    _FALLBACK_URL,
    _PRIMARY_URL,
)


# ─── Helper ───


def _make_csv_text(n: int = 30, start_pcr: float = 0.85) -> str:
    """테스트용 CBOE CSV 텍스트 생성."""
    lines = ["TRADE_DATE,CALL_VOLUME,PUT_VOLUME,TOTAL_VOLUME,P/C_RATIO"]
    import datetime

    base_date = datetime.date(2026, 3, 1)
    pcr = start_pcr
    for i in range(n):
        d = base_date + datetime.timedelta(days=i)
        calls = 1_000_000 + i * 10_000
        puts = int(calls * pcr)
        total = calls + puts
        lines.append(f"{d.strftime('%m/%d/%Y')},{calls},{puts},{total},{pcr:.4f}")
        pcr += 0.005
    return "\n".join(lines)


def _make_csv_no_pcr_col(n: int = 10) -> str:
    """PCR 컬럼 없고 put/call volume만 있는 CSV."""
    lines = ["DATE,CALL_VOLUME,PUT_VOLUME"]
    import datetime

    base_date = datetime.date(2026, 3, 1)
    for i in range(n):
        d = base_date + datetime.timedelta(days=i)
        lines.append(f"{d.strftime('%m/%d/%Y')},{1000000},{850000}")
    return "\n".join(lines)


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    """Mock HTTP response."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ─── Init tests ───


class TestCBOEFetcherInit:
    """CBOEFetcher 초기화 테스트."""

    def test_available_with_requests(self):
        """requests 설치 시 is_available=True."""
        fetcher = CBOEFetcher()
        assert fetcher.is_available is True

    def test_unavailable_without_requests(self):
        """requests 미설치 시 is_available=False."""
        with patch(
            'trading_bot.market_intelligence.cboe_fetcher._has_requests', False,
        ):
            fetcher = CBOEFetcher()
            assert fetcher.is_available is False

    def test_cached_df_initially_none(self):
        """초기 캐시 상태는 None."""
        fetcher = CBOEFetcher()
        assert fetcher._cached_df is None


# ─── CSV parsing tests ───


class TestCSVParsing:
    """CSV 다운로드 및 파싱 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_parse_valid_csv(self, mock_requests):
        """유효한 CSV를 성공적으로 파싱."""
        csv_text = _make_csv_text(n=30)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert len(df) == 30
        assert 'date' in df.columns
        assert 'pcr' in df.columns

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_parse_csv_pcr_values(self, mock_requests):
        """파싱된 PCR 값이 올바름."""
        csv_text = _make_csv_text(n=5, start_pcr=1.0)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert df['pcr'].iloc[0] == pytest.approx(1.0, abs=0.01)

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_parse_csv_without_pcr_column(self, mock_requests):
        """PCR 컬럼 없고 volume만 있는 CSV에서 PCR 계산."""
        csv_text = _make_csv_no_pcr_col(n=10)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert 'pcr' in df.columns
        assert df['pcr'].iloc[0] == pytest.approx(0.85, abs=0.01)

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_lookback_days_limits_rows(self, mock_requests):
        """lookback_days가 반환 행 수를 제한."""
        csv_text = _make_csv_text(n=50)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=10)

        assert df is not None
        assert len(df) == 10

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_sorted_by_date(self, mock_requests):
        """결과가 날짜순으로 정렬."""
        csv_text = _make_csv_text(n=20)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        dates = df['date'].tolist()
        assert dates == sorted(dates)


# ─── Network failure tests ───


class TestNetworkFailure:
    """네트워크 오류 시 동작 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_primary_failure_uses_fallback(self, mock_requests):
        """Primary URL 실패 시 fallback URL 시도."""
        csv_text = _make_csv_text(n=10)

        def side_effect(url, **kwargs):
            if url == _PRIMARY_URL:
                raise Exception("Connection timeout")
            return _mock_response(csv_text)

        mock_requests.get.side_effect = side_effect

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr()

        assert df is not None
        assert len(df) == 10
        assert mock_requests.get.call_count == 2

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_both_urls_fail_returns_none(self, mock_requests):
        """Primary + fallback 모두 실패 시 None 반환."""
        mock_requests.get.side_effect = Exception("Network error")

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr()

        assert df is None
        assert mock_requests.get.call_count == 2

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_http_error_returns_none(self, mock_requests):
        """HTTP 에러 시 None 반환."""
        mock_requests.get.return_value = _mock_response("", status_code=500)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr()

        assert df is None

    def test_fetch_without_requests(self):
        """requests 미설치 시 None 반환."""
        with patch(
            'trading_bot.market_intelligence.cboe_fetcher._has_requests', False,
        ):
            fetcher = CBOEFetcher()
            df = fetcher.fetch_equity_pcr()
            assert df is None


# ─── Caching tests ───


class TestCaching:
    """인스턴스 레벨 캐싱 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_second_call_uses_cache(self, mock_requests):
        """두 번째 호출은 HTTP 요청 없이 캐시 반환."""
        csv_text = _make_csv_text(n=30)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()

        # 첫 호출 -- HTTP 요청
        df1 = fetcher.fetch_equity_pcr()
        assert df1 is not None
        assert mock_requests.get.call_count == 1

        # 두 번째 호출 -- 캐시
        df2 = fetcher.fetch_equity_pcr()
        assert df2 is not None
        assert mock_requests.get.call_count == 1  # 추가 호출 없음

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_cache_returns_copy(self, mock_requests):
        """캐시 반환값은 원본의 복사본."""
        csv_text = _make_csv_text(n=30)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df1 = fetcher.fetch_equity_pcr()
        df2 = fetcher.fetch_equity_pcr()

        assert df1 is not df2  # 다른 객체

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_different_lookback_same_cache(self, mock_requests):
        """lookback_days가 달라도 동일 캐시 사용."""
        csv_text = _make_csv_text(n=50)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        df1 = fetcher.fetch_equity_pcr(lookback_days=10)
        df2 = fetcher.fetch_equity_pcr(lookback_days=30)

        assert len(df1) == 10
        assert len(df2) == 30
        assert mock_requests.get.call_count == 1


# ─── get_latest tests ───


class TestGetLatest:
    """get_latest() 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_get_latest_structure(self, mock_requests):
        """get_latest()가 올바른 키를 포함한 딕셔너리 반환."""
        csv_text = _make_csv_text(n=30, start_pcr=0.9)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert 'equity_pcr' in result
        assert 'pcr_5d_avg' in result
        assert 'pcr_20d_avg' in result
        assert 'date' in result

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_get_latest_pcr_value(self, mock_requests):
        """get_latest()의 PCR 값이 유효한 범위."""
        csv_text = _make_csv_text(n=30, start_pcr=0.9)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert result['equity_pcr'] > 0
        assert result['pcr_5d_avg'] > 0
        assert result['pcr_20d_avg'] > 0

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_get_latest_returns_none_on_failure(self, mock_requests):
        """데이터 수집 실패 시 None 반환."""
        mock_requests.get.side_effect = Exception("Network error")

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is None

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_get_latest_averages(self, mock_requests):
        """5d/20d 평균이 올바르게 계산."""
        csv_text = _make_csv_text(n=30, start_pcr=1.0)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        # 5d avg는 최근 5일 평균이므로 20d avg보다 클 수 있음 (상승 추세)
        assert isinstance(result['pcr_5d_avg'], float)
        assert isinstance(result['pcr_20d_avg'], float)

    @patch('trading_bot.market_intelligence.cboe_fetcher._requests')
    def test_get_latest_with_short_data(self, mock_requests):
        """데이터가 5일 미만일 때도 평균 계산 가능."""
        csv_text = _make_csv_text(n=3, start_pcr=0.8)
        mock_requests.get.return_value = _mock_response(csv_text)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert result['pcr_5d_avg'] > 0
        assert result['pcr_20d_avg'] > 0
