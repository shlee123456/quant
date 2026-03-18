"""
한국 시장 데이터 캐시 — yfinance 기반 KRX 데이터 다운로더.

미국 시장용 MarketDataCache를 상속하여 한국 시장 심볼과
KOSPI MA200 장기 추세 판정을 제공합니다.
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from .data_fetcher import MarketDataCache

logger = logging.getLogger(__name__)


KR_LAYER_SYMBOLS: Dict[str, List[str]] = {
    'indices': ['^KS11', '^KQ11'],
    'vix': [],  # ^VKOSPI는 Yahoo Finance 미지원 — VKOSPI 의존 레이어는 graceful degradation
    'breadth_stocks': [
        '005930.KS', '000660.KS', '005380.KS', '207940.KS', '373220.KS',
        '000270.KS', '005490.KS', '068270.KS', '105560.KS', '006400.KS',
        '012330.KS', '035420.KS', '028260.KS', '055550.KS', '051910.KS',
        '035720.KS', '086790.KS', '096770.KS', '032830.KS', '015760.KS',
        '017670.KS', '000810.KS', '316140.KS', '066570.KS', '011200.KS',
    ],
    'sectors': [
        '091160.KS', '091170.KS', '117700.KS', '140710.KS',
        '266360.KS', '315270.KS', '305720.KS', '098560.KS',
    ],
    'bond_proxies': ['148070.KS', '114260.KS'],
    'sentiment_proxies': ['GLD'],
    'fx': ['USDKRW=X'],
}


def _get_kr_all_symbols() -> List[str]:
    """KR_LAYER_SYMBOLS의 모든 심볼을 중복 없이 합산."""
    seen: set = set()
    result: List[str] = []
    for symbols in KR_LAYER_SYMBOLS.values():
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                result.append(sym)
    return result


class KRMarketDataCache(MarketDataCache):
    """한국 시장 데이터 캐시.

    MarketDataCache를 상속하여 한국 시장 심볼 세트를 사용합니다.
    단일 yf.download() 호출로 KRX 종목의 OHLCV 데이터를 가져오고,
    KOSPI MA200 장기 추세 판정을 제공합니다.

    Args:
        period: yfinance 조회 기간 (기본 '1y', MA200 계산에 200거래일 필요)
        interval: yfinance 조회 간격 (기본 '1d')
        bok_fetcher: BOKDataFetcher 인스턴스 (선택, 한국은행 경제 데이터 연동)
    """

    def __init__(
        self,
        period: str = '1y',
        interval: str = '1d',
        bok_fetcher: Optional[Any] = None,
    ):
        # 부모 클래스 초기화 (fred_fetcher 대신 None)
        super().__init__(period=period, interval=interval, fred_fetcher=None)
        self._bok_fetcher = bok_fetcher
        self._bok_data: Dict[str, pd.Series] = {}

    def _get_all_symbols(self) -> List[str]:
        """한국 시장 심볼 세트를 반환 (오버라이드).

        Returns:
            KR_LAYER_SYMBOLS의 모든 심볼 리스트 (중복 제거)
        """
        return _get_kr_all_symbols()

    def fetch(self, stock_symbols: Optional[List[str]] = None) -> bool:
        """yfinance에서 한국 시장 데이터를 다운로드.

        부모 클래스의 fetch()를 오버라이드하여 한국 시장 심볼을 사용합니다.

        Args:
            stock_symbols: 추가로 다운로드할 심볼 리스트 (None이면 기본 심볼만)

        Returns:
            True: 성공적으로 데이터를 가져옴, False: 실패
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance가 설치되지 않았습니다. pip install yfinance")
            return False

        all_symbols = self._get_all_symbols()
        if stock_symbols:
            for sym in stock_symbols:
                if sym not in all_symbols:
                    all_symbols.append(sym)

        logger.info(
            f"KRMarketDataCache: {len(all_symbols)}개 심볼 다운로드 시작 "
            f"(period={self.period}, interval={self.interval})"
        )

        try:
            raw = yf.download(
                tickers=all_symbols,
                period=self.period,
                interval=self.interval,
                group_by='ticker',
                progress=False,
                threads=True,
            )

            if raw is None or raw.empty:
                logger.error("yf.download()이 빈 결과를 반환했습니다")
                return False

            self._parse_download_result(raw, all_symbols)

            # 배치 다운로드에서 누락된 심볼 개별 재시도
            missing = [s for s in all_symbols if s not in self._data]
            if missing:
                logger.info(f"KRMarketDataCache: {len(missing)}개 심볼 개별 재시도")
                for sym in missing:
                    try:
                        single = yf.download(
                            tickers=sym,
                            period=self.period,
                            interval=self.interval,
                            progress=False,
                        )
                        if single is not None and not single.empty:
                            if 'Close' in single.columns:
                                single = single.dropna(subset=['Close'])
                            if not single.empty:
                                self._data[sym] = single
                    except Exception:
                        pass
                retry_ok = len(missing) - len([s for s in missing if s not in self._data])
                if retry_ok > 0:
                    logger.info(f"KRMarketDataCache: 재시도로 {retry_ok}개 추가 복구")

            self._fetched = True
            logger.info(f"KRMarketDataCache: {len(self._data)}개 심볼 캐시 완료")

            # BOK 데이터 로드 (선택적)
            if self._bok_fetcher and self._bok_fetcher.is_available:
                try:
                    self._bok_data = self._bok_fetcher.fetch_all()
                    logger.info(f"BOK 데이터 로드: {len(self._bok_data)}개 시리즈")
                except Exception as e:
                    logger.warning(f"BOK 데이터 로드 실패: {e}")

            return True

        except Exception as e:
            logger.error(f"KRMarketDataCache 다운로드 실패: {e}")
            return False

    def get_bok(self, key: str) -> Optional[pd.Series]:
        """BOK 시리즈를 키로 조회. 없으면 None.

        Args:
            key: BOK 시리즈 키 (예: 'base_rate', 'cpi')

        Returns:
            pd.Series 또는 None
        """
        return self._bok_data.get(key)

    def kospi_ma200_status(self) -> Dict[str, Any]:
        """KOSPI 200일 이동평균 기준 장기 추세 판정.

        ^KS11 (KOSPI 지수)의 종가를 기준으로 200일 이동평균과 비교합니다.

        Returns:
            {
                'above_ma200': bool,
                'current_price': float,
                'ma200': float,
                'distance_pct': float,
                'regime': str,
            }
            데이터 부족(< 200일) 시 빈 딕셔너리.
        """
        kospi_df = self._data.get('^KS11')
        if kospi_df is None or kospi_df.empty:
            return {}

        close = None
        for col in ('Close', 'close', 'Adj Close'):
            if col in kospi_df.columns:
                close = kospi_df[col].dropna()
                break
        if close is None or len(close) < 200:
            return {}

        current_price = float(close.iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        above = current_price > ma200
        distance_pct = round((current_price - ma200) / ma200 * 100, 2)

        return {
            'above_ma200': above,
            'current_price': round(current_price, 2),
            'ma200': round(ma200, 2),
            'distance_pct': distance_pct,
            'regime': 'long_term_bullish' if above else 'long_term_bearish',
        }
