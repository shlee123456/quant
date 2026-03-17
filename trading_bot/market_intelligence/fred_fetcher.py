"""FRED (Federal Reserve Economic Data) 통합 모듈.

FRED API에서 직접 경제 데이터를 가져와 ETF 프록시보다 정확한 매크로 지표를 제공.
API 키가 없거나 실패 시 기존 ETF 프록시로 자동 폴백.

환경변수: FRED_API_KEY (https://fred.stlouisfed.org에서 무료 발급)
"""
import logging
import os
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 핵심 FRED 시리즈 매핑
FRED_SERIES: Dict[str, str] = {
    'yield_spread': 'T10Y2Y',        # 10Y-2Y Treasury Spread (bp)
    'credit_spread': 'BAMLH0A0HYM2', # ICE BofA US High Yield OAS (bp)
    'manufacturing': 'IPMAN',          # Industrial Production: Manufacturing (100=기준, >100 확장)
    'fed_rate_2y': 'DGS2',           # 2-Year Treasury Yield (%)
    'unemployment': 'ICSA',           # Initial Jobless Claims
    'consumer_sentiment': 'UMCSENT',  # U of Michigan Consumer Sentiment
}


class FREDDataFetcher:
    """FRED API 클라이언트. API 키 없으면 비활성화."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv('FRED_API_KEY')
        self._fred = None
        self._available = False

        if self._api_key:
            try:
                from fredapi import Fred
                self._fred = Fred(api_key=self._api_key)
                self._available = True
                logger.info("FRED 데이터 소스 활성화")
            except ImportError:
                logger.info("fredapi 미설치 — FRED 비활성화 (pip install fredapi)")
            except Exception as e:
                logger.warning(f"FRED 초기화 실패: {e}")
        else:
            logger.info("FRED_API_KEY 미설정 — ETF 프록시 모드")

    @property
    def is_available(self) -> bool:
        return self._available

    def fetch_series(self, series_id: str, observation_start: str = None) -> Optional[pd.Series]:
        """단일 FRED 시리즈 조회.

        Args:
            series_id: FRED 시리즈 ID (예: 'T10Y2Y')
            observation_start: 시작일 (예: '2024-01-01'), None이면 2년 전부터

        Returns:
            pd.Series or None on failure
        """
        if not self._available:
            return None

        try:
            if observation_start is None:
                from datetime import datetime, timedelta
                observation_start = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

            data = self._fred.get_series(series_id, observation_start=observation_start)
            if data is not None and len(data) > 0:
                return data.dropna()
            return None
        except Exception as e:
            logger.warning(f"FRED 시리즈 {series_id} 조회 실패: {e}")
            return None

    def fetch_all(self) -> Dict[str, pd.Series]:
        """FRED_SERIES의 모든 시리즈를 조회.

        Returns:
            {시리즈키: pd.Series} 딕셔너리. 실패한 시리즈는 제외.
        """
        if not self._available:
            return {}

        results = {}
        for key, series_id in FRED_SERIES.items():
            data = self.fetch_series(series_id)
            if data is not None:
                results[key] = data
                logger.debug(f"FRED {key} ({series_id}): {len(data)}건 로드")
            else:
                logger.debug(f"FRED {key} ({series_id}): 로드 실패")

        return results
