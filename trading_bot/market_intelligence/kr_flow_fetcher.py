"""KR 투자자 수급 데이터 수집기.

KIS API (한국투자증권)를 사용하여 KOSPI 주요 종목의
외국인/기관 순매수 데이터를 수집하고 시장 전체 수급을 추정합니다.
KIS API 미사용 시 비활성화됩니다.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _get_field(row, key: str, default=None):
    """KisDynamicDict (속성 접근) 또는 dict (키 접근)에서 필드를 읽습니다."""
    # dict-like 접근 시도
    if isinstance(row, dict):
        return row.get(key, default)
    # KisDynamicDict는 속성 접근만 지원
    return getattr(row, key, default)

# 시장 대표 종목 (시가총액 상위, KOSPI 수급 프록시)
_PROXY_STOCKS: List[str] = [
    '005930',  # 삼성전자
    '000660',  # SK하이닉스
    '005380',  # 현대차
    '035420',  # NAVER
    '051910',  # LG화학
]

# KIS API 투자자별 매매동향 설정
_TR_ID = 'FHKST01010900'
_ENDPOINT = '/uapi/domestic-stock/v1/quotations/inquire-investor'


def _create_kis_client():
    """환경변수에서 KIS 클라이언트를 생성합니다.

    Returns:
        PyKis 인스턴스 또는 None
    """
    appkey = os.getenv('KIS_APPKEY')
    appsecret = os.getenv('KIS_APPSECRET')
    account = os.getenv('KIS_ACCOUNT')
    user_id = os.getenv('KIS_ID', account)

    if not all([appkey, appsecret, account]):
        return None

    try:
        from pykis import PyKis
        return PyKis(
            id=user_id,
            appkey=appkey,
            secretkey=appsecret,
            virtual_id=user_id,
            virtual_appkey=appkey,
            virtual_secretkey=appsecret,
            account=account,
        )
    except Exception as e:
        logger.warning(f"KIS 클라이언트 생성 실패: {e}")
        return None


class KRFlowFetcher:
    """KRX 투자자 수급 데이터 수집기.

    KIS API를 사용하여 KOSPI 주요 종목의 외국인/기관 순매수 데이터를
    수집하고, 시장 전체 수급 방향을 추정합니다.
    KIS API 미사용 시 is_available=False로 비활성화됩니다.

    Args:
        kis_client: PyKis 인스턴스 (None이면 환경변수에서 자동 생성)
    """

    def __init__(self, kis_client=None):
        self._cached_flow: Optional[pd.DataFrame] = None
        self._kis = kis_client

        if self._kis is None:
            self._kis = _create_kis_client()

        if self._kis is not None:
            logger.info("KRFlowFetcher 활성화 (KIS API 사용)")
        else:
            logger.info("KIS API 미설정 — KRFlowFetcher 비활성화")

    @property
    def is_available(self) -> bool:
        """KIS API가 설정되어 사용 가능한지 여부."""
        return self._kis is not None

    def _fetch_stock_investor(
        self, symbol: str, start_date: str, end_date: str,
    ) -> Optional[List[Dict[str, str]]]:
        """단일 종목의 투자자별 매매동향을 KIS API로 조회합니다.

        Args:
            symbol: 종목코드 (예: '005930')
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            KIS API 응답 리스트 또는 실패 시 None
        """
        try:
            result = self._kis.fetch(
                _ENDPOINT,
                method='GET',
                params={
                    'FID_COND_MRKT_DIV_CODE': 'J',
                    'FID_INPUT_ISCD': symbol,
                    'FID_INPUT_DATE_1': start_date,
                    'FID_INPUT_DATE_2': end_date,
                    'FID_PERIOD_DIV_CODE': 'D',
                },
                headers={'tr_id': _TR_ID},
                domain='real',
            )
            return result.output
        except Exception as e:
            logger.warning(f"KIS 투자자 동향 조회 실패 ({symbol}): {e}")
            return None

    def fetch_market_flow(self, days: int = 20) -> Optional[pd.DataFrame]:
        """KOSPI 주요 종목의 투자자별 순매수 데이터를 집계합니다.

        KIS API로 대표 종목들의 외국인/기관 순매수 금액(백만원)을 조회하고,
        날짜별로 합산하여 시장 전체 수급을 추정합니다.

        Args:
            days: 조회할 영업일 수 (기본: 20)

        Returns:
            투자자별 순매수 금액 DataFrame (컬럼: 외국인합계, 기관합계)
            또는 실패 시 None
        """
        if not self.is_available:
            logger.warning("KIS API 미설정 — 수급 데이터 수집 불가")
            return None

        if self._cached_flow is not None:
            return self._cached_flow

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

        try:
            # 날짜별 합산 딕셔너리: {date: {foreign: 0, inst: 0}}
            aggregated: Dict[str, Dict[str, int]] = {}

            for i, symbol in enumerate(_PROXY_STOCKS):
                if i > 0:
                    time.sleep(0.1)  # Rate limiting (15 calls/sec)

                rows = self._fetch_stock_investor(symbol, start_date, end_date)
                if not rows:
                    continue

                for row in rows:
                    date = _get_field(row, 'stck_bsop_date')
                    if not date:
                        continue
                    frgn = int(_get_field(row, 'frgn_ntby_tr_pbmn', '0'))
                    orgn = int(_get_field(row, 'orgn_ntby_tr_pbmn', '0'))

                    if date not in aggregated:
                        aggregated[date] = {'외국인합계': 0, '기관합계': 0}
                    aggregated[date]['외국인합계'] += frgn
                    aggregated[date]['기관합계'] += orgn

            if not aggregated:
                logger.warning("KOSPI 수급 데이터 없음 (KIS API)")
                return None

            df = pd.DataFrame.from_dict(aggregated, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # 백만원 → 원 단위 변환
            df = df * 1_000_000

            self._cached_flow = df
            logger.debug(f"KOSPI 수급 데이터 로드 (KIS API): {len(df)}일")
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
            foreign_col = '외국인합계'
            inst_col = '기관합계'

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

            date_str = (
                str(df.index[-1].date())
                if hasattr(df.index[-1], 'date')
                else str(df.index[-1])
            )

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

        KIS API에는 시장 전체 공매도 엔드포인트가 없으므로 None을 반환합니다.
        호출자(KRMarketStructureLayer)는 None을 graceful하게 처리합니다.

        Args:
            days: 조회할 영업일 수 (미사용)

        Returns:
            항상 None
        """
        logger.debug("KIS API에 시장 전체 공매도 엔드포인트 없음 — None 반환")
        return None

    def get_short_selling_summary(self) -> Optional[Dict[str, Any]]:
        """최신 공매도 요약을 반환합니다.

        KIS API에는 시장 전체 공매도 데이터가 없으므로 항상 None입니다.

        Returns:
            항상 None
        """
        return None
