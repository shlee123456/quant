"""KR 투자자 수급 데이터 수집기.

pykrx를 사용하여 KOSPI 외국인/기관 순매수 데이터를 가져옵니다.
pykrx 미설치 시 비활성화됩니다.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# pykrx optional import (bok_fetcher.py 패턴)
try:
    from pykrx import stock as _pykrx_stock
    _has_pykrx = True
except ImportError:
    _pykrx_stock = None  # type: ignore
    _has_pykrx = False

logger = logging.getLogger(__name__)


class KRFlowFetcher:
    """KRX 투자자 수급 데이터 수집기.

    pykrx를 사용하여 KOSPI 시장의 외국인/기관 순매수 데이터와
    시장 전체 공매도 데이터를 수집합니다.
    pykrx 미설치 시 is_available=False로 비활성화됩니다.
    """

    def __init__(self):
        self._cached_flow: Optional[pd.DataFrame] = None
        self._cached_short: Optional[pd.DataFrame] = None

        if _has_pykrx:
            logger.info("KRFlowFetcher 활성화 (pykrx 사용 가능)")
        else:
            logger.info("pykrx 미설치 — KRFlowFetcher 비활성화")

    @property
    def is_available(self) -> bool:
        """pykrx가 설치되어 사용 가능한지 여부."""
        return _has_pykrx

    def fetch_market_flow(self, days: int = 20) -> Optional[pd.DataFrame]:
        """KOSPI 투자자별 순매수 데이터를 가져옵니다.

        Args:
            days: 조회할 영업일 수 (기본: 20)

        Returns:
            투자자별 순매수 DataFrame 또는 실패 시 None
        """
        if not _has_pykrx:
            logger.warning("pykrx 미설치 — 수급 데이터 수집 불가")
            return None

        if self._cached_flow is not None:
            return self._cached_flow

        # pykrx 날짜 형식: YYYYMMDD
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

        try:
            df = _pykrx_stock.get_market_trading_value_by_date(
                start_date, end_date, 'KOSPI'
            )

            if df is None or df.empty:
                logger.warning("KOSPI 수급 데이터 없음")
                return None

            self._cached_flow = df
            logger.debug(f"KOSPI 수급 데이터 로드: {len(df)}일")
            return df

        except Exception as e:
            logger.warning(f"KOSPI 수급 데이터 수집 실패: {e}")
            return None

    def get_latest_summary(self) -> Optional[Dict[str, Any]]:
        """최신 투자자 수급 요약을 반환합니다.

        Returns:
            Dict with keys: date, foreign_net_today, foreign_net_5d,
            institutional_net_today, institutional_net_5d,
            foreign_trend, institutional_trend, consensus
            또는 실패 시 None
        """
        df = self.fetch_market_flow()
        if df is None or len(df) < 2:
            return None

        try:
            # pykrx 컬럼: 기관합계, 기타법인, 개인, 외국인합계, 전체
            # 컬럼명은 pykrx 버전에 따라 다를 수 있음
            foreign_col = None
            inst_col = None

            for col in df.columns:
                if '외국인' in str(col):
                    foreign_col = col
                if '기관' in str(col):
                    inst_col = col

            if foreign_col is None or inst_col is None:
                logger.warning(
                    f"수급 데이터 컬럼 매칭 실패. 컬럼: {list(df.columns)}"
                )
                return None

            # 최신 데이터
            foreign_net_today = int(df[foreign_col].iloc[-1])
            inst_net_today = int(df[inst_col].iloc[-1])

            # 최근 5일 합산
            recent_5d = df.tail(5)
            foreign_net_5d = int(recent_5d[foreign_col].sum())
            inst_net_5d = int(recent_5d[inst_col].sum())

            # 트렌드 판단
            foreign_trend = 'buying' if foreign_net_5d > 0 else 'selling'
            inst_trend = 'buying' if inst_net_5d > 0 else 'selling'

            # 컨센서스
            if foreign_net_5d > 0 and inst_net_5d > 0:
                consensus = 'aligned_buying'
            elif foreign_net_5d < 0 and inst_net_5d < 0:
                consensus = 'aligned_selling'
            else:
                consensus = 'divergent'

            date_str = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])

            return {
                'date': date_str,
                'foreign_net_today': foreign_net_today,
                'foreign_net_5d': foreign_net_5d,
                'institutional_net_today': inst_net_today,
                'institutional_net_5d': inst_net_5d,
                'foreign_trend': foreign_trend,
                'institutional_trend': inst_trend,
                'consensus': consensus,
            }

        except Exception as e:
            logger.warning(f"수급 요약 생성 실패: {e}")
            return None

    def fetch_market_short_selling(self, days: int = 20) -> Optional[pd.DataFrame]:
        """시장 전체 공매도 데이터를 가져옵니다.

        pykrx.stock.get_shorting_volume_by_date(start, end) — 시장 전체, ticker 없음.

        Args:
            days: 조회할 영업일 수 (기본: 20)

        Returns:
            공매도 DataFrame 또는 실패 시 None
        """
        if not _has_pykrx:
            logger.warning("pykrx 미설치 — 공매도 데이터 수집 불가")
            return None

        if self._cached_short is not None:
            return self._cached_short

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

        try:
            df = _pykrx_stock.get_shorting_volume_by_date(start_date, end_date)

            if df is None or df.empty:
                logger.warning("공매도 데이터 없음")
                return None

            self._cached_short = df
            logger.debug(f"공매도 데이터 로드: {len(df)}일")
            return df

        except Exception as e:
            logger.warning(f"공매도 데이터 수집 실패: {e}")
            return None

    def get_short_selling_summary(self) -> Optional[Dict[str, Any]]:
        """최신 공매도 요약을 반환합니다.

        Returns:
            Dict with keys: short_ratio_today, short_ratio_5d_avg, trend
            또는 실패 시 None
        """
        df = self.fetch_market_short_selling()
        if df is None or len(df) < 2:
            return None

        try:
            # pykrx 공매도 컬럼: 공매도, 매수, 합계 등
            short_col = None
            total_col = None

            for col in df.columns:
                col_str = str(col)
                if '공매도' in col_str and short_col is None:
                    short_col = col
                if '합계' in col_str or '거래량' in col_str:
                    total_col = col

            # 컬럼을 찾지 못하면 첫 번째/마지막 컬럼으로 시도
            if short_col is None or total_col is None:
                cols = list(df.columns)
                if len(cols) >= 2:
                    short_col = cols[0]
                    total_col = cols[-1]
                else:
                    logger.warning(f"공매도 데이터 컬럼 매칭 실패: {list(df.columns)}")
                    return None

            # 공매도 비율 계산
            total_values = df[total_col].replace(0, np.nan)
            short_ratio = df[short_col] / total_values

            short_ratio_today = float(short_ratio.iloc[-1]) if not np.isnan(short_ratio.iloc[-1]) else 0.0
            short_ratio_5d = float(short_ratio.tail(5).mean()) if len(short_ratio) >= 5 else short_ratio_today

            # 트렌드: 오늘 > 5일 평균이면 increasing
            if short_ratio_today > short_ratio_5d * 1.02:
                trend = 'increasing'
            elif short_ratio_today < short_ratio_5d * 0.98:
                trend = 'decreasing'
            else:
                trend = 'stable'

            return {
                'short_ratio_today': round(short_ratio_today, 4),
                'short_ratio_5d_avg': round(short_ratio_5d, 4),
                'trend': trend,
            }

        except Exception as e:
            logger.warning(f"공매도 요약 생성 실패: {e}")
            return None
