"""
Daily Market Data Analyzer

KIS 브로커로 시가총액 Top 10 종목의 OHLCV 데이터를 수집하고,
기술 지표(RSI, MACD, Bollinger Bands, Stochastic, ADX)를 계산하여
구조화된 JSON으로 저장하는 모듈.

Usage:
    from trading_bot.market_analyzer import MarketAnalyzer
    from trading_bot.brokers import KoreaInvestmentBroker

    broker = KoreaInvestmentBroker(...)
    analyzer = MarketAnalyzer()
    results = analyzer.analyze(symbols=['AAPL', 'MSFT', ...], broker=broker)
    analyzer.save_json(results, output_dir='data/market_analysis')
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from .regime_detector import RegimeDetector

try:
    from .news_collector import NewsCollector
    _has_news_collector = True
except ImportError:
    NewsCollector = None
    _has_news_collector = False

try:
    from .fear_greed_collector import FearGreedCollector
    _has_fear_greed = True
except ImportError:
    FearGreedCollector = None
    _has_fear_greed = False

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """시가총액 Top 10 종목의 일일 기술적 분석을 수행하는 클래스"""

    # 주요 종목 거래소 매핑
    NYSE_SYMBOLS = {
        'LLY', 'WMT', 'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK',
        'V', 'MA', 'AXP', 'JNJ', 'UNH', 'ABBV', 'MRK', 'TMO', 'ABT',
        'XOM', 'CVX', 'COP', 'SLB', 'EOG',
        'PG', 'KO', 'PM', 'MO',
        'DIS', 'HD', 'LOW', 'MCD', 'NKE', 'TGT',
        'CRM', 'ORCL',
        'BA', 'CAT', 'GE', 'UPS', 'FDX', 'MMM',
    }

    def __init__(self, ohlcv_limit: int = 200, api_delay: float = 0.5):
        """
        Args:
            ohlcv_limit: OHLCV 조회 봉 수 (기본 200)
            api_delay: API 호출 간 대기 시간(초)
        """
        self.ohlcv_limit = ohlcv_limit
        self.api_delay = api_delay
        self.regime_detector = RegimeDetector()

    def analyze(self, symbols: List[str], broker: Any, collect_news: bool = True,
                collect_fear_greed: bool = True) -> Dict:
        """
        전체 분석 실행: 데이터 수집 + 지표 계산 + 레짐 감지 + 뉴스 수집 + F&G 지수

        Args:
            symbols: 분석 대상 종목 리스트
            broker: KoreaInvestmentBroker 인스턴스
            collect_news: 뉴스 수집 여부 (기본 True)
            collect_fear_greed: 공포/탐욕 지수 수집 여부 (기본 True)

        Returns:
            구조화된 분석 결과 딕셔너리
        """
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"시장 분석 시작: {today}, {len(symbols)}개 종목")

        stocks_results = {}

        for symbol in symbols:
            try:
                df = self._fetch_data(symbol, broker)
                if df is None or len(df) < 30:
                    logger.warning(f"{symbol}: 데이터 부족 (조회 실패 또는 30봉 미만)")
                    continue

                indicators = self._calculate_indicators(df)
                regime = self._detect_regime(df)
                patterns = self._detect_patterns(df['close'].values)

                # 가격 정보
                last_close = float(df['close'].iloc[-1])
                change_5d = self._pct_change(df['close'], 5)
                change_20d = self._pct_change(df['close'], 20)

                # 시그널 진단: 현재 RSI 기반 최적 범위 제안
                rsi_val = indicators['rsi']['value']
                signal_diagnosis = self._diagnose_signals(rsi_val, indicators)

                stocks_results[symbol] = {
                    'price': {
                        'last': last_close,
                        'change_5d': change_5d,
                        'change_20d': change_20d,
                    },
                    'indicators': indicators,
                    'regime': regime,
                    'patterns': patterns,
                    'signal_diagnosis': signal_diagnosis,
                }

                logger.info(f"  {symbol}: ${last_close:.2f}, RSI={rsi_val:.1f}, 레짐={regime['state']}")

            except Exception as e:
                logger.error(f"  {symbol} 분석 실패: {e}", exc_info=True)
                continue

        if not stocks_results:
            logger.error("분석 가능한 종목이 없습니다")
            return {'date': today, 'market_summary': {}, 'stocks': {}}

        summary = self._generate_summary(stocks_results)

        result = {
            'date': today,
            'market_summary': summary,
            'stocks': stocks_results,
        }

        # 뉴스 수집 (옵션)
        if collect_news and _has_news_collector:
            try:
                news_collector = NewsCollector()
                news_data = news_collector.collect(symbols)
                result['news'] = news_data
                logger.info(f"뉴스 수집 완료: 시장 {len(news_data.get('market_news', []))}건, "
                            f"종목 {sum(len(v) for v in news_data.get('stock_news', {}).values())}건")
            except Exception as e:
                logger.warning(f"뉴스 수집 실패 (기술적 분석은 정상 진행): {e}")
        elif collect_news and not _has_news_collector:
            logger.info("NewsCollector 미설치 - 뉴스 수집 건너뜀 (feedparser 설치 필요)")

        # Fear & Greed Index 수집 (옵션)
        if collect_fear_greed and _has_fear_greed:
            try:
                fg_collector = FearGreedCollector()
                fg_data = fg_collector.collect(limit=30)
                if fg_data is not None:
                    # 차트 생성
                    chart_path = fg_collector.generate_chart(fg_data)
                    if chart_path:
                        fg_data['chart_path'] = chart_path
                    result['fear_greed_index'] = fg_data
                    logger.info(
                        f"Fear & Greed Index 수집 완료: "
                        f"{fg_data['current']['value']} ({fg_data['current']['classification']})"
                    )
            except Exception as e:
                logger.warning(f"Fear & Greed Index 수집 실패 (기술적 분석은 정상 진행): {e}")
        elif collect_fear_greed and not _has_fear_greed:
            logger.info("FearGreedCollector 미설치 - F&G 지수 수집 건너뜀")

        return result

    def _fetch_data(self, symbol: str, broker: Any) -> Optional[pd.DataFrame]:
        """KIS 브로커로 OHLCV 일봉 조회 (거래소 폴백 포함)

        KIS API에서 일부 NYSE 종목이 NASDAQ으로 등록된 경우가 있어,
        첫 번째 거래소 실패 시 다른 거래소로 재시도합니다.
        """
        primary = 'NYSE' if symbol.upper() in self.NYSE_SYMBOLS else 'NASDAQ'
        fallbacks = ['NASDAQ', 'NYSE', 'AMEX']
        markets_to_try = [primary] + [m for m in fallbacks if m != primary]

        for market in markets_to_try:
            try:
                df = broker.fetch_ohlcv(
                    symbol=symbol,
                    timeframe='1d',
                    limit=self.ohlcv_limit,
                    overseas=True,
                    market=market,
                )
                time.sleep(self.api_delay)

                if df is not None and not df.empty:
                    if market != primary:
                        logger.info(f"{symbol}: {primary} 실패 → {market}에서 조회 성공")
                    return df

            except Exception as e:
                logger.debug(f"{symbol} ({market}) 조회 실패: {e}")
                time.sleep(self.api_delay)
                continue

        logger.warning(f"{symbol}: 모든 거래소(NYSE/NASDAQ/AMEX)에서 조회 실패")
        return None

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """RSI, MACD, Bollinger Bands, Stochastic, ADX 계산"""
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)

        # --- RSI ---
        rsi = self._calc_rsi(close, period=14)
        rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        rsi_signal, rsi_zone = self._classify_rsi(rsi_val)

        # --- MACD ---
        macd_line, signal_line, histogram = self._calc_macd(close)
        macd_hist_val = float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else 0.0
        macd_signal = 'bullish' if macd_hist_val > 0 else 'bearish'
        # 최근 크로스 감지 (최근 3봉 이내)
        cross_recent = self._detect_macd_cross(macd_line, signal_line, lookback=3)

        # --- Bollinger Bands ---
        bb_upper, bb_middle, bb_lower = self._calc_bollinger(close, period=20, std_dev=2.0)
        pct_b = self._calc_pct_b(close.iloc[-1], bb_upper.iloc[-1], bb_lower.iloc[-1])
        bb_signal = self._classify_bollinger(pct_b)

        # --- Stochastic ---
        stoch_k, stoch_d = self._calc_stochastic(high, low, close, k_period=14, d_period=3)
        k_val = float(stoch_k.iloc[-1]) if not pd.isna(stoch_k.iloc[-1]) else 50.0
        d_val = float(stoch_d.iloc[-1]) if not pd.isna(stoch_d.iloc[-1]) else 50.0
        stoch_signal = self._classify_stochastic(k_val, d_val)

        # --- ADX ---
        adx = self._calc_adx(df, period=14)
        adx_val = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
        adx_trend = self._classify_adx(adx_val)

        return {
            'rsi': {'value': round(rsi_val, 1), 'signal': rsi_signal, 'zone': rsi_zone},
            'macd': {
                'histogram': round(macd_hist_val, 3),
                'signal': macd_signal,
                'cross_recent': cross_recent,
            },
            'bollinger': {'pct_b': round(pct_b, 3), 'signal': bb_signal},
            'stochastic': {'k': round(k_val, 1), 'd': round(d_val, 1), 'signal': stoch_signal},
            'adx': {'value': round(adx_val, 1), 'trend': adx_trend},
        }

    def _detect_regime(self, df: pd.DataFrame) -> Dict:
        """RegimeDetector를 사용한 시장 레짐 감지"""
        try:
            result = self.regime_detector.detect(df)
            return {
                'state': result.regime.value,
                'confidence': round(result.confidence, 2),
            }
        except Exception as e:
            logger.warning(f"레짐 감지 실패: {e}")
            return {'state': 'UNKNOWN', 'confidence': 0.0}

    def _detect_patterns(self, close_prices: np.ndarray) -> Dict:
        """저점 패턴 감지 (이중/삼중 바닥) 및 지지선 추정"""
        result = {'double_bottom': False, 'support_levels': []}

        if len(close_prices) < 30:
            return result

        # 최근 60봉 (또는 전체) 에서 로컬 최저점 찾기
        window = min(60, len(close_prices))
        recent = close_prices[-window:]

        local_mins = []
        for i in range(2, len(recent) - 2):
            if recent[i] <= recent[i - 1] and recent[i] <= recent[i - 2] \
               and recent[i] <= recent[i + 1] and recent[i] <= recent[i + 2]:
                local_mins.append(float(recent[i]))

        # 이중 바닥: 최근 두 저점이 비슷한 수준 (2% 이내)
        if len(local_mins) >= 2:
            last_two = local_mins[-2:]
            diff_pct = abs(last_two[0] - last_two[1]) / max(last_two) * 100
            if diff_pct < 2.0:
                result['double_bottom'] = True

        # 지지선: 로컬 최저점 클러스터링 (단순 방식)
        if local_mins:
            sorted_mins = sorted(local_mins)
            result['support_levels'] = [round(s, 2) for s in sorted_mins[:3]]

        return result

    def _diagnose_signals(self, rsi_val: float, indicators: Dict) -> Dict:
        """현재 지표 기반으로 전략 파라미터 적합성 진단"""
        # RSI 35/65 기본 범위에서 시그널 발생 여부
        rsi_35_65_buy = rsi_val < 35
        rsi_35_65_sell = rsi_val > 65

        # 현재 RSI 값 기반 최적 범위 제안
        # RSI가 40~60 범위에 많이 있다면 좁은 범위 권장
        optimal_oversold = max(25, round(rsi_val - 8)) if rsi_val < 50 else 35
        optimal_overbought = min(75, round(rsi_val + 8)) if rsi_val > 50 else 65

        return {
            'rsi_35_65': {
                'buy_triggered': rsi_35_65_buy,
                'sell_triggered': rsi_35_65_sell,
            },
            'optimal_rsi_range': {
                'oversold': optimal_oversold,
                'overbought': optimal_overbought,
            },
        }

    def _generate_summary(self, stocks_results: Dict) -> Dict:
        """전체 시장 요약 통계 생성"""
        total = len(stocks_results)
        bullish = 0
        bearish = 0
        sideways = 0
        rsi_values = []
        notable_events = []

        for symbol, data in stocks_results.items():
            regime = data['regime']['state']
            if regime == 'BULLISH':
                bullish += 1
            elif regime == 'BEARISH':
                bearish += 1
            else:
                sideways += 1

            rsi_val = data['indicators']['rsi']['value']
            rsi_values.append(rsi_val)

            # 주목할 이벤트 감지
            if rsi_val < 25:
                notable_events.append(f"{symbol} RSI {rsi_val:.0f} 극단적 과매도")
            elif rsi_val > 75:
                notable_events.append(f"{symbol} RSI {rsi_val:.0f} 극단적 과매수")

            change_20d = data['price'].get('change_20d', 0)
            if change_20d is not None and change_20d < -10:
                notable_events.append(f"{symbol} 20일 {change_20d:.1f}% 급락")
            elif change_20d is not None and change_20d > 10:
                notable_events.append(f"{symbol} 20일 +{change_20d:.1f}% 급등")

            adx_val = data['indicators']['adx']['value']
            if adx_val > 40:
                notable_events.append(f"{symbol} ADX {adx_val:.0f} 강한 추세")

        avg_rsi = round(float(np.mean(rsi_values)), 1) if rsi_values else 50.0

        # 시장 심리 판단
        if avg_rsi < 35:
            sentiment = "강한 약세"
        elif avg_rsi < 45:
            sentiment = "약세"
        elif avg_rsi < 55:
            sentiment = "중립"
        elif avg_rsi < 65:
            sentiment = "강세"
        else:
            sentiment = "강한 강세"

        return {
            'total_stocks': total,
            'bullish_count': bullish,
            'bearish_count': bearish,
            'sideways_count': sideways,
            'avg_rsi': avg_rsi,
            'market_sentiment': sentiment,
            'notable_events': notable_events[:10],  # 최대 10개
        }

    def save_json(self, results: Dict, output_dir: str = 'data/market_analysis') -> str:
        """분석 결과를 JSON 파일로 저장

        Args:
            results: analyze() 반환값
            output_dir: 저장 디렉토리

        Returns:
            저장된 파일 경로
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        date_str = results.get('date', datetime.now().strftime('%Y-%m-%d'))
        file_path = output_path / f"{date_str}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"분석 결과 저장: {file_path}")
        return str(file_path)

    # ─── 지표 계산 헬퍼 ───

    @staticmethod
    def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        avg_gains = gains.ewm(span=period, min_periods=period, adjust=False).mean()
        avg_losses = losses.ewm(span=period, min_periods=period, adjust=False).mean()
        rs = avg_gains / avg_losses.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        fast_ema = close.ewm(span=fast, adjust=False).mean()
        slow_ema = close.ewm(span=slow, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def _calc_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0):
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return upper, middle, lower

    @staticmethod
    def _calc_pct_b(price: float, upper: float, lower: float) -> float:
        if pd.isna(upper) or pd.isna(lower) or upper == lower:
            return 0.5
        return (price - lower) / (upper - lower)

    @staticmethod
    def _calc_stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                         k_period: int = 14, d_period: int = 3):
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        denom = (highest_high - lowest_low).replace(0, np.nan)
        stoch_k = 100 * (close - lowest_low) / denom
        stoch_d = stoch_k.rolling(window=d_period).mean()
        return stoch_k, stoch_d

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """RegimeDetector의 ADX 계산을 재사용"""
        return self.regime_detector._calculate_adx(df, period)

    @staticmethod
    def _pct_change(series: pd.Series, periods: int) -> Optional[float]:
        if len(series) <= periods:
            return None
        prev = float(series.iloc[-periods - 1])
        curr = float(series.iloc[-1])
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100, 1)

    @staticmethod
    def _detect_macd_cross(macd: pd.Series, signal: pd.Series, lookback: int = 3) -> bool:
        if len(macd) < lookback + 1:
            return False
        for i in range(-lookback, 0):
            prev_diff = macd.iloc[i - 1] - signal.iloc[i - 1]
            curr_diff = macd.iloc[i] - signal.iloc[i]
            if not pd.isna(prev_diff) and not pd.isna(curr_diff):
                if (prev_diff <= 0 and curr_diff > 0) or (prev_diff >= 0 and curr_diff < 0):
                    return True
        return False

    # ─── 분류 헬퍼 ───

    @staticmethod
    def _classify_rsi(val: float) -> tuple:
        if val < 25:
            return 'oversold', '0-25'
        elif val < 35:
            return 'near_oversold', '25-35'
        elif val < 45:
            return 'weak', '35-45'
        elif val < 55:
            return 'neutral', '45-55'
        elif val < 65:
            return 'strong', '55-65'
        elif val < 75:
            return 'near_overbought', '65-75'
        else:
            return 'overbought', '75-100'

    @staticmethod
    def _classify_bollinger(pct_b: float) -> str:
        if pct_b < 0.0:
            return 'below_lower'
        elif pct_b < 0.2:
            return 'near_lower'
        elif pct_b < 0.8:
            return 'neutral'
        elif pct_b < 1.0:
            return 'near_upper'
        else:
            return 'above_upper'

    @staticmethod
    def _classify_stochastic(k: float, d: float) -> str:
        if k < 20 and d < 20:
            return 'oversold_zone'
        elif k > 80 and d > 80:
            return 'overbought_zone'
        elif k < 20:
            return 'near_oversold'
        elif k > 80:
            return 'near_overbought'
        else:
            return 'neutral'

    @staticmethod
    def _classify_adx(val: float) -> str:
        if val < 15:
            return 'no_trend'
        elif val < 25:
            return 'weak_trend'
        elif val < 40:
            return 'moderate_trend'
        else:
            return 'strong_trend'
