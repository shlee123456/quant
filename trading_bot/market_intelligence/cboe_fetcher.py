"""CBOE Put/Call Ratio 데이터 수집 모듈.

CBOE 웹사이트에서 일별 Equity Put/Call Ratio CSV를 다운로드하여
옵션 시장 포지셔닝 데이터를 제공합니다.

Primary URL: https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv
Fallback URL: https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv
"""

import logging
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Optional

import pandas as pd

# requests optional import
try:
    import requests as _requests
    _has_requests = True
except ImportError:
    _requests = None  # type: ignore
    _has_requests = False

logger = logging.getLogger(__name__)

# CBOE CSV URLs
_PRIMARY_URL = (
    'https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv'
)
_FALLBACK_URL = (
    'https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv'
)


class CBOEFetcher:
    """CBOE Put/Call Ratio 데이터 수집기.

    CBOE에서 일별 Equity Put/Call Ratio CSV를 다운로드하고,
    최신 PCR 및 이동평균을 계산합니다.

    인스턴스 레벨 캐싱으로 동일 인스턴스 내 중복 다운로드를 방지합니다.
    """

    def __init__(self) -> None:
        self._cached_df: Optional[pd.DataFrame] = None
        self._available = _has_requests

        if not self._available:
            logger.info("requests 미설치 -- CBOE fetcher 비활성화")

    @property
    def is_available(self) -> bool:
        """requests가 설치되어 사용 가능한지 여부."""
        return self._available

    def fetch_equity_pcr(
        self, lookback_days: int = 60
    ) -> Optional[pd.DataFrame]:
        """CBOE Equity Put/Call Ratio CSV를 다운로드하고 파싱.

        Args:
            lookback_days: 최근 N일 데이터만 반환 (기본 60일)

        Returns:
            date, calls, puts, total, pcr 컬럼의 DataFrame 또는 실패 시 None
        """
        if not self._available:
            logger.warning("requests 미설치 -- CBOE CSV 다운로드 불가")
            return None

        # 캐시 반환
        if self._cached_df is not None:
            return self._cached_df.tail(lookback_days).copy()

        # Primary URL 시도
        df = self._download_and_parse(_PRIMARY_URL)

        # Fallback URL 시도
        if df is None:
            logger.warning("Primary CBOE URL 실패, fallback 시도")
            df = self._download_and_parse(_FALLBACK_URL)

        if df is None:
            logger.warning("CBOE Put/Call Ratio 데이터 수집 실패 (primary + fallback)")
            return None

        self._cached_df = df
        return df.tail(lookback_days).copy()

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """최신 PCR 데이터 요약 반환.

        Returns:
            {equity_pcr, pcr_5d_avg, pcr_20d_avg, date} 딕셔너리 또는 None
        """
        df = self.fetch_equity_pcr(lookback_days=60)
        if df is None or df.empty:
            return None

        latest = df.iloc[-1]
        pcr_series = df['pcr']

        pcr_5d = pcr_series.tail(5).mean() if len(pcr_series) >= 5 else pcr_series.mean()
        pcr_20d = pcr_series.tail(20).mean() if len(pcr_series) >= 20 else pcr_series.mean()

        return {
            'equity_pcr': round(float(latest['pcr']), 4),
            'pcr_5d_avg': round(float(pcr_5d), 4),
            'pcr_20d_avg': round(float(pcr_20d), 4),
            'date': str(latest['date']),
        }

    def _download_and_parse(self, url: str) -> Optional[pd.DataFrame]:
        """CSV를 다운로드하고 DataFrame으로 파싱.

        Args:
            url: CBOE CSV URL

        Returns:
            파싱된 DataFrame 또는 실패 시 None
        """
        try:
            response = _requests.get(url, timeout=15)
            response.raise_for_status()

            # CBOE CSV는 첫 2행이 면책조항/메타데이터, 3행부터 실제 헤더
            # 자동 감지: 'DATE' 문자열이 포함된 행을 헤더로 사용
            lines = response.text.splitlines()
            header_row = 0
            for i, line in enumerate(lines[:10]):
                if 'DATE' in line.upper() and 'CALL' in line.upper():
                    header_row = i
                    break

            df = pd.read_csv(
                StringIO(response.text),
                skiprows=header_row,
                skipinitialspace=True,
            )

            # 컬럼명 정규화 (공백/대소문자 통일)
            df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

            # 날짜 컬럼 파싱
            date_col = None
            for candidate in ('trade_date', 'date'):
                if candidate in df.columns:
                    date_col = candidate
                    break

            if date_col is None:
                logger.warning(f"CBOE CSV에 날짜 컬럼 없음: {list(df.columns)}")
                return None

            df['date'] = pd.to_datetime(df[date_col], errors='coerce')
            df = df.dropna(subset=['date'])

            # P/C Ratio 컬럼 찾기
            pcr_col = None
            for candidate in ('p/c_ratio', 'pc_ratio', 'pcr', 'put/call_ratio'):
                if candidate in df.columns:
                    pcr_col = candidate
                    break

            if pcr_col is not None:
                df['pcr'] = pd.to_numeric(df[pcr_col], errors='coerce')
            else:
                # puts/calls 컬럼에서 계산
                puts_col = next(
                    (c for c in df.columns if 'put' in c and 'vol' in c),
                    None,
                )
                calls_col = next(
                    (c for c in df.columns if 'call' in c and 'vol' in c),
                    None,
                )
                if puts_col and calls_col:
                    df['puts'] = pd.to_numeric(df[puts_col], errors='coerce')
                    df['calls'] = pd.to_numeric(df[calls_col], errors='coerce')
                    df['pcr'] = df['puts'] / df['calls'].replace(0, float('nan'))
                else:
                    logger.warning(f"CBOE CSV에서 PCR 계산 불가: {list(df.columns)}")
                    return None

            df = df.dropna(subset=['pcr'])
            df = df.sort_values('date').reset_index(drop=True)

            if df.empty:
                return None

            logger.info(f"CBOE PCR 데이터 로드: {len(df)}일 ({url.split('/')[-1]})")
            return df

        except Exception as e:
            logger.warning(f"CBOE CSV 다운로드/파싱 실패 ({url}): {e}")
            return None
