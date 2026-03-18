"""
Tests for bok_fetcher.py — BOK 경제통계시스템 Open API 연동.
"""

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from trading_bot.market_intelligence.bok_fetcher import (
    BOKDataFetcher,
    BOK_SERIES,
    _BOK_API_BASE,
)


# ─── Helper ───


def _make_bok_response(
    rows: list,
    total_count: int = 0,
) -> dict:
    """테스트용 BOK API 응답 JSON 생성.

    Args:
        rows: StatisticSearch.row 리스트
        total_count: 전체 건수

    Returns:
        BOK API 형식 딕셔너리
    """
    if total_count == 0:
        total_count = len(rows)
    return {
        'StatisticSearch': {
            'list_total_count': total_count,
            'row': rows,
        }
    }


def _make_bok_error(code: str = 'ERROR', message: str = 'Test error') -> dict:
    """테스트용 BOK API 에러 응답 생성."""
    return {
        'RESULT': {
            'CODE': code,
            'MESSAGE': message,
        }
    }


def _make_monthly_rows(
    n: int = 12,
    start_year: int = 2025,
    start_month: int = 1,
    start_value: float = 100.0,
    trend: float = 0.5,
) -> list:
    """월별 데이터 행 리스트 생성.

    Args:
        n: 데이터 포인트 수
        start_year: 시작 연도
        start_month: 시작 월
        start_value: 시작 값
        trend: 월별 변화량

    Returns:
        BOK API row 형식 리스트
    """
    rows = []
    year = start_year
    month = start_month
    value = start_value

    for _ in range(n):
        time_str = f"{year}{month:02d}"
        rows.append({
            'TIME': time_str,
            'DATA_VALUE': str(round(value, 2)),
        })
        value += trend
        month += 1
        if month > 12:
            month = 1
            year += 1

    return rows


# ─── BOK_SERIES 상수 테스트 ───


class TestBOKSeries:
    """BOK_SERIES 상수 검증."""

    def test_required_keys(self):
        """필수 시리즈 키 존재."""
        expected_keys = {'base_rate', 'industrial_production', 'consumer_confidence', 'cpi'}
        assert expected_keys == set(BOK_SERIES.keys())

    def test_each_series_has_required_fields(self):
        """각 시리즈에 필수 필드가 있음."""
        required_fields = {'table_code', 'item_code', 'period_type', 'description'}
        for key, info in BOK_SERIES.items():
            assert required_fields.issubset(set(info.keys())), f"{key}에 필수 필드 누락"

    def test_base_rate_config(self):
        """기준금리 설정값 확인."""
        info = BOK_SERIES['base_rate']
        assert info['table_code'] == '722Y001'
        assert info['item_code'] == '0101000'
        assert info['period_type'] == 'M'

    def test_industrial_production_config(self):
        """광공업생산지수 설정값 확인."""
        info = BOK_SERIES['industrial_production']
        assert info['table_code'] == '901Y033'
        assert info['item_code'] == 'I11AA'

    def test_consumer_confidence_config(self):
        """소비자심리지수 설정값 확인."""
        info = BOK_SERIES['consumer_confidence']
        assert info['table_code'] == '511Y002'
        assert info['item_code'] == 'FME'

    def test_cpi_config(self):
        """소비자물가지수 설정값 확인."""
        info = BOK_SERIES['cpi']
        assert info['table_code'] == '901Y009'
        assert info['item_code'] == '0'

    def test_all_period_types_valid(self):
        """모든 period_type이 M, Q, A 중 하나."""
        valid_periods = {'M', 'Q', 'A'}
        for key, info in BOK_SERIES.items():
            assert info['period_type'] in valid_periods, f"{key}: 잘못된 period_type"


# ─── BOKDataFetcher 초기화 테스트 ───


class TestBOKDataFetcherInit:
    """BOKDataFetcher 초기화 테스트."""

    def test_disabled_without_key(self):
        """API 키 없으면 is_available=False."""
        with patch.dict('os.environ', {}, clear=True):
            fetcher = BOKDataFetcher(api_key=None)
        assert fetcher.is_available is False

    def test_enabled_with_explicit_key(self):
        """명시적 API 키로 활성화."""
        fetcher = BOKDataFetcher(api_key='test_key_123')
        assert fetcher.is_available is True

    def test_enabled_with_env_var(self):
        """환경변수 BOK_API_KEY로 활성화."""
        with patch.dict('os.environ', {'BOK_API_KEY': 'env_key_456'}):
            fetcher = BOKDataFetcher()
        assert fetcher.is_available is True

    def test_explicit_key_overrides_env(self):
        """명시적 키가 환경변수보다 우선."""
        with patch.dict('os.environ', {'BOK_API_KEY': 'env_key'}):
            fetcher = BOKDataFetcher(api_key='explicit_key')
        assert fetcher._api_key == 'explicit_key'

    def test_empty_string_key_is_disabled(self):
        """빈 문자열 키는 비활성."""
        with patch.dict('os.environ', {}, clear=True):
            fetcher = BOKDataFetcher(api_key='')
        assert fetcher.is_available is False


# ─── URL 빌드 테스트 ───


class TestBuildURL:
    """_build_url() 테스트."""

    def test_url_format(self):
        """URL 형식이 올바름."""
        fetcher = BOKDataFetcher(api_key='MY_KEY')
        url = fetcher._build_url(
            table_code='722Y001',
            period_type='M',
            start_date='202301',
            end_date='202512',
            item_code='0101000',
        )
        expected = (
            f"{_BOK_API_BASE}/MY_KEY/json/kr/1/100/"
            f"722Y001/M/202301/202512/0101000"
        )
        assert url == expected

    def test_url_contains_api_key(self):
        """URL에 API 키가 포함."""
        fetcher = BOKDataFetcher(api_key='SECRET_KEY')
        url = fetcher._build_url('T', 'M', '202301', '202512', 'I')
        assert 'SECRET_KEY' in url

    def test_url_contains_table_code(self):
        """URL에 통계표 코드가 포함."""
        fetcher = BOKDataFetcher(api_key='KEY')
        url = fetcher._build_url('901Y033', 'M', '202301', '202512', 'I11AA')
        assert '901Y033' in url


# ─── 응답 파싱 테스트 ───


class TestParseResponse:
    """_parse_response() 테스트."""

    def test_parse_valid_monthly_data(self):
        """유효한 월별 데이터 파싱."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = _make_monthly_rows(n=6, start_year=2025, start_month=1, start_value=3.5)
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert isinstance(result, pd.Series)
        assert len(result) == 6
        assert result.iloc[0] == 3.5

    def test_parse_yearly_data(self):
        """연별 데이터 (TIME: YYYY) 파싱."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = [
            {'TIME': '2023', 'DATA_VALUE': '100.0'},
            {'TIME': '2024', 'DATA_VALUE': '102.5'},
            {'TIME': '2025', 'DATA_VALUE': '105.0'},
        ]
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert len(result) == 3

    def test_parse_error_response(self):
        """에러 응답 시 None 반환."""
        fetcher = BOKDataFetcher(api_key='test')
        response = _make_bok_error('NO_DATA', '해당 데이터가 없습니다')

        result = fetcher._parse_response(response)
        assert result is None

    def test_parse_empty_rows(self):
        """빈 rows 배열 시 None 반환."""
        fetcher = BOKDataFetcher(api_key='test')
        response = _make_bok_response([])

        result = fetcher._parse_response(response)
        assert result is None

    def test_parse_missing_stat_search(self):
        """StatisticSearch 키가 없는 응답."""
        fetcher = BOKDataFetcher(api_key='test')
        response = {'RESULT': {'CODE': 'ERROR', 'MESSAGE': 'fail'}}

        result = fetcher._parse_response(response)
        assert result is None

    def test_parse_skips_invalid_values(self):
        """DATA_VALUE가 숫자가 아닌 행은 건너뜀."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = [
            {'TIME': '202501', 'DATA_VALUE': '3.5'},
            {'TIME': '202502', 'DATA_VALUE': 'N/A'},
            {'TIME': '202503', 'DATA_VALUE': '3.7'},
        ]
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert len(result) == 2

    def test_parse_skips_empty_time(self):
        """TIME이 빈 행은 건너뜀."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = [
            {'TIME': '', 'DATA_VALUE': '3.5'},
            {'TIME': '202501', 'DATA_VALUE': '3.5'},
        ]
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert len(result) == 1

    def test_parse_sorted_by_date(self):
        """결과가 날짜순으로 정렬."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = [
            {'TIME': '202503', 'DATA_VALUE': '3.7'},
            {'TIME': '202501', 'DATA_VALUE': '3.5'},
            {'TIME': '202502', 'DATA_VALUE': '3.6'},
        ]
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert list(result.values) == [3.5, 3.6, 3.7]

    def test_parse_returns_float_dtype(self):
        """반환 Series의 dtype이 float."""
        fetcher = BOKDataFetcher(api_key='test')
        rows = _make_monthly_rows(n=3)
        response = _make_bok_response(rows)

        result = fetcher._parse_response(response)
        assert result is not None
        assert result.dtype == float


# ─── fetch_series 테스트 ───


class TestFetchSeries:
    """fetch_series() 테스트."""

    def test_returns_none_when_unavailable(self):
        """비활성 상태에서 None 반환."""
        with patch.dict('os.environ', {}, clear=True):
            fetcher = BOKDataFetcher(api_key=None)
        assert fetcher.fetch_series('base_rate') is None

    def test_returns_none_for_unknown_key(self):
        """존재하지 않는 키는 None 반환."""
        fetcher = BOKDataFetcher(api_key='test')
        result = fetcher.fetch_series('nonexistent_key')
        assert result is None

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_series_success(self, mock_requests):
        """정상 API 호출 시 Series 반환."""
        rows = _make_monthly_rows(n=12, start_value=3.5)
        mock_response = MagicMock()
        mock_response.json.return_value = _make_bok_response(rows)
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        result = fetcher.fetch_series('base_rate', start_date='202501', end_date='202512')

        assert result is not None
        assert len(result) == 12
        mock_requests.get.assert_called_once()

        # URL에 올바른 통계표 코드 포함 확인
        call_url = mock_requests.get.call_args[0][0]
        assert '722Y001' in call_url
        assert '0101000' in call_url

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_series_api_error(self, mock_requests):
        """API 에러 시 None 반환."""
        mock_response = MagicMock()
        mock_response.json.return_value = _make_bok_error()
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        result = fetcher.fetch_series('base_rate')
        assert result is None

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_series_network_error(self, mock_requests):
        """네트워크 오류 시 None 반환."""
        mock_requests.get.side_effect = Exception("Connection refused")

        fetcher = BOKDataFetcher(api_key='test_key')
        result = fetcher.fetch_series('base_rate')
        assert result is None

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_series_default_dates(self, mock_requests):
        """start_date/end_date 미지정 시 기본값 사용."""
        rows = _make_monthly_rows(n=6)
        mock_response = MagicMock()
        mock_response.json.return_value = _make_bok_response(rows)
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        result = fetcher.fetch_series('cpi')

        assert result is not None
        mock_requests.get.assert_called_once()

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_series_http_error(self, mock_requests):
        """HTTP 에러 시 None 반환."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        result = fetcher.fetch_series('base_rate')
        assert result is None


# ─── fetch_all 테스트 ───


class TestFetchAll:
    """fetch_all() 테스트."""

    def test_returns_empty_when_unavailable(self):
        """비활성 상태에서 빈 dict 반환."""
        with patch.dict('os.environ', {}, clear=True):
            fetcher = BOKDataFetcher(api_key=None)
        assert fetcher.fetch_all() == {}

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_all_success(self, mock_requests):
        """모든 시리즈 성공적으로 로드."""
        rows = _make_monthly_rows(n=6, start_value=100.0)
        mock_response = MagicMock()
        mock_response.json.return_value = _make_bok_response(rows)
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        results = fetcher.fetch_all()

        assert len(results) == len(BOK_SERIES)
        for key in BOK_SERIES:
            assert key in results
            assert isinstance(results[key], pd.Series)
            assert len(results[key]) == 6

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_all_partial_failure(self, mock_requests):
        """일부 시리즈 실패 시 성공한 것만 반환."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            if call_count[0] % 2 == 0:
                # 짝수 호출은 에러
                mock_resp.json.return_value = _make_bok_error()
            else:
                # 홀수 호출은 성공
                rows = _make_monthly_rows(n=6)
                mock_resp.json.return_value = _make_bok_response(rows)
            return mock_resp

        mock_requests.get.side_effect = side_effect

        fetcher = BOKDataFetcher(api_key='test_key')
        results = fetcher.fetch_all()

        # 일부만 성공
        assert 0 < len(results) < len(BOK_SERIES)

    @patch('trading_bot.market_intelligence.bok_fetcher._requests')
    def test_fetch_all_total_failure(self, mock_requests):
        """모든 시리즈 실패 시 빈 dict."""
        mock_response = MagicMock()
        mock_response.json.return_value = _make_bok_error()
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        fetcher = BOKDataFetcher(api_key='test_key')
        results = fetcher.fetch_all()
        assert results == {}


# ─── requests 미설치 테스트 ───


class TestWithoutRequests:
    """requests 미설치 시 동작."""

    def test_fetch_series_without_requests(self):
        """requests 미설치 시 None 반환."""
        fetcher = BOKDataFetcher(api_key='test_key')

        with patch(
            'trading_bot.market_intelligence.bok_fetcher._has_requests',
            False,
        ):
            result = fetcher.fetch_series('base_rate')
            assert result is None
