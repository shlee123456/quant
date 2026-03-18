"""BOK (한국은행 경제통계시스템) 통합 모듈.

BOK Open API에서 직접 경제 데이터를 가져와 한국 매크로 지표를 제공합니다.
API 키가 없거나 실패 시 빈 결과를 반환합니다.

환경변수: BOK_API_KEY (https://ecos.bok.or.kr 에서 무료 발급)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

# requests optional import
try:
    import requests as _requests
    _has_requests = True
except ImportError:
    _requests = None  # type: ignore
    _has_requests = False

logger = logging.getLogger(__name__)

# BOK 경제통계시스템 핵심 시리즈 매핑
# {논리키: (통계표코드, 아이템코드, 주기, 설명)}
BOK_SERIES: Dict[str, Dict[str, str]] = {
    'base_rate': {
        'table_code': '722Y001',
        'item_code': '0101000',
        'period_type': 'M',
        'description': '한국은행 기준금리',
    },
    'industrial_production': {
        'table_code': '901Y033',
        'item_code': 'I11AA',
        'period_type': 'M',
        'description': '광공업생산지수',
    },
    'consumer_confidence': {
        'table_code': '511Y002',
        'item_code': 'FME',
        'period_type': 'M',
        'description': '소비자심리지수 (CCSI)',
    },
    'cpi': {
        'table_code': '901Y009',
        'item_code': '0',
        'period_type': 'M',
        'description': '소비자물가지수',
    },
}

# BOK API 기본 URL
_BOK_API_BASE = 'https://ecos.bok.or.kr/api/StatisticSearch'


class BOKDataFetcher:
    """BOK Open API 클라이언트. API 키 없으면 비활성화.

    Args:
        api_key: BOK API 키. None이면 환경변수 BOK_API_KEY에서 읽음.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv('BOK_API_KEY')
        self._available = bool(self._api_key)

        if self._available:
            logger.info("BOK 데이터 소스 활성화")
        else:
            logger.info("BOK_API_KEY 미설정 — BOK 비활성화")

    @property
    def is_available(self) -> bool:
        """API 키가 설정되어 사용 가능한지 여부."""
        return self._available

    def _build_url(
        self,
        table_code: str,
        period_type: str,
        start_date: str,
        end_date: str,
        item_code: str,
    ) -> str:
        """BOK API URL을 생성합니다.

        Args:
            table_code: 통계표 코드
            period_type: 주기 (M: 월, Q: 분기, A: 연)
            start_date: 시작일 (YYYYMM 또는 YYYY)
            end_date: 종료일 (YYYYMM 또는 YYYY)
            item_code: 아이템 코드

        Returns:
            완성된 API URL 문자열
        """
        return (
            f"{_BOK_API_BASE}/{self._api_key}/json/kr/1/100/"
            f"{table_code}/{period_type}/{start_date}/{end_date}/{item_code}"
        )

    def _parse_response(self, data: Dict[str, Any]) -> Optional[pd.Series]:
        """BOK API JSON 응답을 pd.Series로 변환합니다.

        Args:
            data: API 응답 JSON 딕셔너리

        Returns:
            날짜 인덱스의 pd.Series 또는 파싱 실패 시 None
        """
        stat_search = data.get('StatisticSearch')
        if stat_search is None:
            # 에러 응답인 경우
            result = data.get('RESULT', {})
            code = result.get('CODE', 'UNKNOWN')
            message = result.get('MESSAGE', 'Unknown error')
            logger.warning(f"BOK API 에러: {code} - {message}")
            return None

        rows: List[Dict[str, Any]] = stat_search.get('row', [])
        if not rows:
            return None

        dates: List[pd.Timestamp] = []
        values: List[float] = []

        for row in rows:
            time_str = row.get('TIME', '')
            data_value = row.get('DATA_VALUE', '')

            if not time_str or not data_value:
                continue

            try:
                value = float(data_value)
            except (ValueError, TypeError):
                continue

            # 날짜 파싱 (YYYYMM -> datetime)
            try:
                if len(time_str) == 6:
                    # 월별: YYYYMM
                    dt = pd.Timestamp(f"{time_str[:4]}-{time_str[4:6]}-01")
                elif len(time_str) == 4:
                    # 연별: YYYY
                    dt = pd.Timestamp(f"{time_str}-01-01")
                else:
                    continue
            except (ValueError, TypeError):
                continue

            dates.append(dt)
            values.append(value)

        if not dates:
            return None

        series = pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)
        series = series.sort_index()
        return series

    def fetch_series(
        self,
        key: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.Series]:
        """단일 BOK 시리즈를 조회합니다.

        Args:
            key: BOK_SERIES 키 (예: 'base_rate', 'cpi')
            start_date: 시작일 (YYYYMM 형식). None이면 2년 전부터.
            end_date: 종료일 (YYYYMM 형식). None이면 현재.

        Returns:
            pd.Series 또는 실패 시 None
        """
        if not self._available:
            return None

        series_info = BOK_SERIES.get(key)
        if series_info is None:
            logger.warning(f"BOK 시리즈 키 '{key}'가 BOK_SERIES에 없습니다")
            return None

        if end_date is None:
            end_date = datetime.now().strftime('%Y%m')
        if start_date is None:
            start_dt = datetime.now() - timedelta(days=730)
            start_date = start_dt.strftime('%Y%m')

        url = self._build_url(
            table_code=series_info['table_code'],
            period_type=series_info['period_type'],
            start_date=start_date,
            end_date=end_date,
            item_code=series_info['item_code'],
        )

        if not _has_requests:
            logger.warning("requests 미설치 — BOK API 호출 불가 (pip install requests)")
            return None

        try:
            response = _requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            result = self._parse_response(data)

            if result is not None and len(result) > 0:
                logger.debug(f"BOK {key}: {len(result)}건 로드")
                return result

            logger.debug(f"BOK {key}: 데이터 없음")
            return None

        except Exception as e:
            logger.warning(f"BOK 시리즈 {key} 조회 실패: {e}")
            return None

    def fetch_all(self) -> Dict[str, pd.Series]:
        """BOK_SERIES의 모든 시리즈를 조회합니다.

        Returns:
            {시리즈키: pd.Series} 딕셔너리. 실패한 시리즈는 제외.
        """
        if not self._available:
            return {}

        results: Dict[str, pd.Series] = {}
        for key in BOK_SERIES:
            data = self.fetch_series(key)
            if data is not None:
                results[key] = data
                logger.debug(
                    f"BOK {key} ({BOK_SERIES[key]['table_code']}): "
                    f"{len(data)}건 로드"
                )
            else:
                logger.debug(
                    f"BOK {key} ({BOK_SERIES[key]['table_code']}): 로드 실패"
                )

        return results
