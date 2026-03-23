"""VIX 기반 Put/Call Ratio 프록시 모듈.

CBOE CSV URL이 2019년 이후 업데이트 중단되어,
yfinance ^VIX 데이터를 PCR 프록시로 사용합니다.

VIX와 PCR은 강한 상관관계 (둘 다 공포/헤지 활동 측정):
- VIX 20 ≈ PCR 1.0 (중립)
- VIX 30 ≈ PCR 1.5 (공포)
- VIX 12 ≈ PCR 0.6 (탐욕)

프록시 공식: pcr_proxy = vix_value / 20.0
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

# yfinance optional import
try:
    import yfinance as yf
    _has_yfinance = True
except ImportError:
    yf = None  # type: ignore
    _has_yfinance = False

logger = logging.getLogger(__name__)

# VIX → PCR 프록시 변환 상수
_VIX_NEUTRAL = 20.0  # VIX 20 = PCR 1.0


class CBOEFetcher:
    """VIX 기반 Put/Call Ratio 프록시 수집기.

    yfinance로 ^VIX 데이터를 다운로드하고,
    VIX → PCR 프록시 변환을 통해 옵션 시장 포지셔닝을 추정합니다.

    인스턴스 레벨 캐싱으로 동일 인스턴스 내 중복 다운로드를 방지합니다.
    """

    def __init__(self) -> None:
        self._cached_df: Optional[pd.DataFrame] = None
        self._available = _has_yfinance

        if not self._available:
            logger.info("yfinance 미설치 -- CBOE fetcher 비활성화")

    @property
    def is_available(self) -> bool:
        """yfinance가 설치되어 사용 가능한지 여부."""
        return self._available

    def fetch_equity_pcr(
        self, lookback_days: int = 60
    ) -> Optional[pd.DataFrame]:
        """VIX 기반 PCR 프록시 데이터를 다운로드하고 변환.

        Args:
            lookback_days: 최근 N일 데이터만 반환 (기본 60일)

        Returns:
            date, pcr, vix 컬럼의 DataFrame 또는 실패 시 None
        """
        if not self._available:
            logger.warning("yfinance 미설치 -- VIX 데이터 다운로드 불가")
            return None

        # 캐시 반환
        if self._cached_df is not None:
            return self._cached_df.tail(lookback_days).copy()

        df = self._fetch_vix()

        if df is None:
            logger.warning("VIX 데이터 수집 실패")
            return None

        self._cached_df = df
        return df.tail(lookback_days).copy()

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """최신 PCR 프록시 데이터 요약 반환.

        Returns:
            {equity_pcr, pcr_5d_avg, pcr_20d_avg, date, vix_value, source} 또는 None
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
            'vix_value': round(float(latest['vix']), 2),
            'source': 'vix_proxy',
        }

    def _fetch_vix(self) -> Optional[pd.DataFrame]:
        """yfinance로 ^VIX 데이터를 다운로드하고 PCR 프록시로 변환.

        Returns:
            date, vix, pcr 컬럼의 DataFrame 또는 실패 시 None
        """
        try:
            raw = yf.download('^VIX', period='3mo', progress=False)

            if raw is None or raw.empty:
                logger.warning("yfinance ^VIX 데이터 없음")
                return None

            # yfinance multi-level column 대응
            close_col = raw['Close']
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]

            df = pd.DataFrame({
                'date': close_col.index,
                'vix': close_col.values,
            })

            df['vix'] = pd.to_numeric(df['vix'], errors='coerce')
            df = df.dropna(subset=['vix'])

            if df.empty:
                return None

            # VIX → PCR 프록시 변환
            df['pcr'] = df['vix'] / _VIX_NEUTRAL

            df = df.sort_values('date').reset_index(drop=True)

            logger.info(f"VIX 기반 PCR 프록시 로드: {len(df)}일")
            return df

        except Exception as e:
            logger.warning(f"VIX 데이터 다운로드 실패: {e}")
            return None
