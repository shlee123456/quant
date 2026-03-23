"""
Tests for cboe_fetcher.py -- VIX 기반 Put/Call Ratio 프록시 수집기.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.market_intelligence.cboe_fetcher import (
    CBOEFetcher,
    _VIX_NEUTRAL,
)


# --- Helper ---


def _make_vix_df(n: int = 30, start_vix: float = 20.0) -> pd.DataFrame:
    """yfinance.download 반환값을 모방하는 VIX DataFrame 생성."""
    import datetime

    dates = pd.date_range(
        start=datetime.date(2026, 3, 1), periods=n, freq='B',
    )
    vix_values = [start_vix + i * 0.3 for i in range(n)]

    df = pd.DataFrame(
        {'Close': vix_values},
        index=dates,
    )
    df.index.name = 'Date'
    return df


def _make_empty_df() -> pd.DataFrame:
    """빈 DataFrame."""
    return pd.DataFrame()


# --- Init tests ---


class TestCBOEFetcherInit:
    """CBOEFetcher 초기화 테스트."""

    def test_available_with_yfinance(self):
        """yfinance 설치 시 is_available=True."""
        fetcher = CBOEFetcher()
        assert fetcher.is_available is True

    def test_unavailable_without_yfinance(self):
        """yfinance 미설치 시 is_available=False."""
        with patch(
            'trading_bot.market_intelligence.cboe_fetcher._has_yfinance', False,
        ):
            fetcher = CBOEFetcher()
            assert fetcher.is_available is False

    def test_cached_df_initially_none(self):
        """초기 캐시 상태는 None."""
        fetcher = CBOEFetcher()
        assert fetcher._cached_df is None


# --- VIX → PCR conversion tests ---


class TestVIXToPCR:
    """VIX → PCR 프록시 변환 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_vix_20_gives_pcr_1(self, mock_yf):
        """VIX 20 → PCR 1.0 (중립)."""
        mock_yf.download.return_value = _make_vix_df(n=5, start_vix=20.0)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert df['pcr'].iloc[0] == pytest.approx(1.0, abs=0.01)

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_vix_30_gives_pcr_1_5(self, mock_yf):
        """VIX 30 → PCR 1.5 (공포)."""
        mock_yf.download.return_value = _make_vix_df(n=5, start_vix=30.0)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert df['pcr'].iloc[0] == pytest.approx(1.5, abs=0.01)

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_vix_12_gives_pcr_0_6(self, mock_yf):
        """VIX 12 → PCR 0.6 (탐욕)."""
        mock_yf.download.return_value = _make_vix_df(n=5, start_vix=12.0)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert df['pcr'].iloc[0] == pytest.approx(0.6, abs=0.01)

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_pcr_formula(self, mock_yf):
        """PCR = VIX / 20.0 공식 검증."""
        mock_yf.download.return_value = _make_vix_df(n=10, start_vix=25.0)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        for _, row in df.iterrows():
            expected_pcr = row['vix'] / _VIX_NEUTRAL
            assert row['pcr'] == pytest.approx(expected_pcr, abs=1e-6)


# --- Data fetch tests ---


class TestDataFetch:
    """데이터 다운로드 및 파싱 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_fetch_returns_dataframe(self, mock_yf):
        """유효한 데이터를 성공적으로 파싱."""
        mock_yf.download.return_value = _make_vix_df(n=30)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        assert len(df) == 30
        assert 'date' in df.columns
        assert 'pcr' in df.columns
        assert 'vix' in df.columns

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_lookback_days_limits_rows(self, mock_yf):
        """lookback_days가 반환 행 수를 제한."""
        mock_yf.download.return_value = _make_vix_df(n=50)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=10)

        assert df is not None
        assert len(df) == 10

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_sorted_by_date(self, mock_yf):
        """결과가 날짜순으로 정렬."""
        mock_yf.download.return_value = _make_vix_df(n=20)

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr(lookback_days=60)

        assert df is not None
        dates = df['date'].tolist()
        assert dates == sorted(dates)


# --- Failure tests ---


class TestFailure:
    """오류 시 동작 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_download_exception_returns_none(self, mock_yf):
        """yfinance 예외 시 None 반환."""
        mock_yf.download.side_effect = Exception("Network error")

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr()

        assert df is None

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_empty_data_returns_none(self, mock_yf):
        """빈 데이터 시 None 반환."""
        mock_yf.download.return_value = _make_empty_df()

        fetcher = CBOEFetcher()
        df = fetcher.fetch_equity_pcr()

        assert df is None

    def test_fetch_without_yfinance(self):
        """yfinance 미설치 시 None 반환."""
        with patch(
            'trading_bot.market_intelligence.cboe_fetcher._has_yfinance', False,
        ):
            fetcher = CBOEFetcher()
            df = fetcher.fetch_equity_pcr()
            assert df is None


# --- Caching tests ---


class TestCaching:
    """인스턴스 레벨 캐싱 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_second_call_uses_cache(self, mock_yf):
        """두 번째 호출은 다운로드 없이 캐시 반환."""
        mock_yf.download.return_value = _make_vix_df(n=30)

        fetcher = CBOEFetcher()

        df1 = fetcher.fetch_equity_pcr()
        assert df1 is not None
        assert mock_yf.download.call_count == 1

        df2 = fetcher.fetch_equity_pcr()
        assert df2 is not None
        assert mock_yf.download.call_count == 1  # 추가 호출 없음

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_cache_returns_copy(self, mock_yf):
        """캐시 반환값은 원본의 복사본."""
        mock_yf.download.return_value = _make_vix_df(n=30)

        fetcher = CBOEFetcher()
        df1 = fetcher.fetch_equity_pcr()
        df2 = fetcher.fetch_equity_pcr()

        assert df1 is not df2

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_different_lookback_same_cache(self, mock_yf):
        """lookback_days가 달라도 동일 캐시 사용."""
        mock_yf.download.return_value = _make_vix_df(n=50)

        fetcher = CBOEFetcher()
        df1 = fetcher.fetch_equity_pcr(lookback_days=10)
        df2 = fetcher.fetch_equity_pcr(lookback_days=30)

        assert len(df1) == 10
        assert len(df2) == 30
        assert mock_yf.download.call_count == 1


# --- get_latest tests ---


class TestGetLatest:
    """get_latest() 테스트."""

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_get_latest_structure(self, mock_yf):
        """get_latest()가 올바른 키를 포함한 딕셔너리 반환."""
        mock_yf.download.return_value = _make_vix_df(n=30, start_vix=20.0)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert 'equity_pcr' in result
        assert 'pcr_5d_avg' in result
        assert 'pcr_20d_avg' in result
        assert 'date' in result
        assert 'vix_value' in result
        assert 'source' in result
        assert result['source'] == 'vix_proxy'

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_get_latest_pcr_value(self, mock_yf):
        """get_latest()의 PCR 값이 유효한 범위."""
        mock_yf.download.return_value = _make_vix_df(n=30, start_vix=20.0)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert result['equity_pcr'] > 0
        assert result['pcr_5d_avg'] > 0
        assert result['pcr_20d_avg'] > 0
        assert result['vix_value'] > 0

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_get_latest_returns_none_on_failure(self, mock_yf):
        """데이터 수집 실패 시 None 반환."""
        mock_yf.download.side_effect = Exception("Network error")

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is None

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_get_latest_averages(self, mock_yf):
        """5d/20d 평균이 올바르게 계산."""
        mock_yf.download.return_value = _make_vix_df(n=30, start_vix=20.0)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert isinstance(result['pcr_5d_avg'], float)
        assert isinstance(result['pcr_20d_avg'], float)

    @patch('trading_bot.market_intelligence.cboe_fetcher.yf')
    def test_get_latest_with_short_data(self, mock_yf):
        """데이터가 5일 미만일 때도 평균 계산 가능."""
        mock_yf.download.return_value = _make_vix_df(n=3, start_vix=18.0)

        fetcher = CBOEFetcher()
        result = fetcher.get_latest()

        assert result is not None
        assert result['pcr_5d_avg'] > 0
        assert result['pcr_20d_avg'] > 0
