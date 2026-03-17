"""
Centralized yfinance data downloader for Market Intelligence layers.

모든 레이어가 공유하는 시장 데이터 캐시를 제공합니다.
단일 yf.download() 호출로 모든 심볼의 데이터를 효율적으로 가져옵니다.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# yfinance optional import
try:
    import yfinance as yf
    _has_yfinance = True
except ImportError:
    yf = None
    _has_yfinance = False


LAYER_SYMBOLS: Dict[str, List[str]] = {
    'yield_curve': ['^TNX', '^FVX', 'TLT', 'SHY', 'IEF'],
    'credit_spread': ['HYG', 'LQD', 'IEI'],
    'dollar': ['UUP'],
    'manufacturing': ['XLI'],
    'vix': ['^VIX', '^VIX3M'],
    'vix_etf': ['VIXY', 'VIXM'],
    'breadth_stocks': [
        'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'TSLA', 'BRK-B',
        'JPM', 'JNJ', 'V', 'UNH', 'PG', 'HD', 'MA', 'DIS', 'NFLX', 'ADBE',
        'CRM', 'INTC', 'CSCO', 'PFE', 'XOM', 'WMT', 'KO',
    ],
    'factors': ['MTUM', 'VLUE', 'QUAL', 'SIZE', 'USMV'],
    'sectors': [
        'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLU', 'XLY', 'XLC',
        'XLB', 'XLRE',
    ],
    'indices': ['SPY', 'QQQ', 'DIA', 'IWM'],
    'sentiment_proxies': ['GLD'],
}


def _get_all_symbols() -> List[str]:
    """모든 레이어 심볼을 중복 없이 합산."""
    seen = set()
    result = []
    for symbols in LAYER_SYMBOLS.values():
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                result.append(sym)
    return result


class MarketDataCache:
    """시장 데이터 캐시.

    단일 yf.download() 호출로 모든 심볼의 OHLCV 데이터를 가져오고,
    레이어별로 필요한 데이터를 get()/get_many()로 조회합니다.

    Args:
        period: yfinance 조회 기간 (기본 '6mo')
        interval: yfinance 조회 간격 (기본 '1d')
    """

    def __init__(self, period: str = '6mo', interval: str = '1d', fred_fetcher=None):
        self.period = period
        self.interval = interval
        self._data: Dict[str, pd.DataFrame] = {}
        self._fred_data: Dict[str, pd.Series] = {}
        self._fred_fetcher = fred_fetcher
        self._fetched = False

    def fetch(self, stock_symbols: Optional[List[str]] = None) -> bool:
        """yfinance에서 데이터를 다운로드.

        Args:
            stock_symbols: 추가로 다운로드할 심볼 리스트 (None이면 기본 심볼만)

        Returns:
            True: 성공적으로 데이터를 가져옴, False: 실패
        """
        if not _has_yfinance:
            logger.warning("yfinance가 설치되지 않았습니다. pip install yfinance")
            return False

        all_symbols = _get_all_symbols()
        if stock_symbols:
            for sym in stock_symbols:
                if sym not in all_symbols:
                    all_symbols.append(sym)

        logger.info(f"MarketDataCache: {len(all_symbols)}개 심볼 다운로드 시작 "
                    f"(period={self.period}, interval={self.interval})")

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
            self._fetched = True
            logger.info(f"MarketDataCache: {len(self._data)}개 심볼 캐시 완료")

            # FRED 데이터 로드 (선택적)
            if self._fred_fetcher and self._fred_fetcher.is_available:
                try:
                    self._fred_data = self._fred_fetcher.fetch_all()
                    logger.info(f"FRED 데이터 로드: {len(self._fred_data)}개 시리즈")
                except Exception as e:
                    logger.warning(f"FRED 데이터 로드 실패 (ETF 프록시 사용): {e}")

            return True

        except Exception as e:
            logger.error(f"MarketDataCache 다운로드 실패: {e}")
            return False

    def _parse_download_result(
        self,
        raw: pd.DataFrame,
        symbols: List[str],
    ) -> None:
        """yf.download() 결과를 심볼별 DataFrame으로 파싱.

        yfinance는 단일 심볼이면 단일 레벨 컬럼,
        복수 심볼이면 MultiIndex (ticker, price) 컬럼을 반환합니다.
        """
        self._data = {}

        if len(symbols) == 1:
            # 단일 심볼: 컬럼이 바로 Open, High, Low, Close, Volume
            sym = symbols[0]
            df = raw.copy()
            if not df.empty and 'Close' in df.columns:
                df = df.dropna(subset=['Close'])
                if not df.empty:
                    self._data[sym] = df
            return

        # 복수 심볼: MultiIndex columns
        if isinstance(raw.columns, pd.MultiIndex):
            for sym in symbols:
                try:
                    if sym in raw.columns.get_level_values(0):
                        df = raw[sym].copy()
                        # NaN-only 행 제거
                        if 'Close' in df.columns:
                            df = df.dropna(subset=['Close'])
                        if not df.empty:
                            self._data[sym] = df
                except (KeyError, TypeError):
                    continue
        else:
            # 단일 심볼이 반환된 경우 (요청은 복수지만 1개만 성공)
            if 'Close' in raw.columns:
                # 어떤 심볼인지 판단하기 어려우므로 첫 번째 심볼로 할당
                for sym in symbols:
                    df = raw.copy()
                    df = df.dropna(subset=['Close'])
                    if not df.empty:
                        self._data[sym] = df
                    break

    def get(self, symbol: str) -> Optional[pd.DataFrame]:
        """단일 심볼의 OHLCV 데이터를 반환.

        Args:
            symbol: 티커 심볼

        Returns:
            DataFrame (Open, High, Low, Close, Volume) 또는 None
        """
        return self._data.get(symbol)

    def get_many(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """여러 심볼의 데이터를 한 번에 반환.

        Args:
            symbols: 티커 심볼 리스트

        Returns:
            {심볼: DataFrame} 딕셔너리 (데이터 없는 심볼은 제외)
        """
        result = {}
        for sym in symbols:
            df = self._data.get(sym)
            if df is not None:
                result[sym] = df
        return result

    def get_fred(self, key: str) -> Optional[pd.Series]:
        """FRED 시리즈를 키로 조회. 없으면 None."""
        return self._fred_data.get(key)

    def freshness_multiplier(self, symbol: str) -> float:
        """데이터 신선도 멀티플라이어.

        당일 데이터=1.0, 하루 경과마다 -0.1, 최소 0.3.

        Args:
            symbol: 심볼명

        Returns:
            0.0 (데이터 없음) ~ 1.0 (당일 데이터)
        """
        df = self._data.get(symbol)
        if df is None or df.empty:
            return 0.0

        latest = df.index[-1]
        now = pd.Timestamp.now(tz='UTC')

        if latest.tzinfo is None:
            latest = latest.tz_localize('UTC')

        days_stale = max(0, (now - latest).days)
        return max(0.3, 1.0 - 0.1 * days_stale)

    @property
    def available_symbols(self) -> List[str]:
        """캐시에 저장된 심볼 목록."""
        return list(self._data.keys())

    @property
    def is_fetched(self) -> bool:
        """데이터가 이미 로드되었는지 여부."""
        return self._fetched
