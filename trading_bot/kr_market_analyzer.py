"""
한국 시장 일일 데이터 분석기 (KR Market Analyzer)

KIS 브로커로 KRX 시가총액 상위 종목의 OHLCV 데이터를 수집하고,
기술 지표(RSI, MACD, Bollinger Bands, Stochastic, ADX)를 계산하여
구조화된 JSON으로 저장하는 모듈.

MarketAnalyzer(US)와 동일한 패턴이며, 국내주식(overseas=False)에 특화.

Usage:
    from trading_bot.kr_market_analyzer import KRMarketAnalyzer
    from trading_bot.brokers import KoreaInvestmentBroker

    broker = KoreaInvestmentBroker(...)
    analyzer = KRMarketAnalyzer()
    results = analyzer.analyze(symbols=['005930', '000660'], broker=broker)
    analyzer.save_json(results, output_dir='data/market_analysis')
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .regime_detector import RegimeDetector
from .kr_news_collector import KRNewsCollector
from .kr_event_calendar import KREventCalendarCollector

try:
    import yfinance as yf
    _has_yfinance = True
except ImportError:
    yf = None
    _has_yfinance = False

logger = logging.getLogger(__name__)


# KRX 시가총액 상위 종목
KRX_TOP_SYMBOLS: List[str] = [
    '005930', '000660', '005380', '035420', '035720',
    '006400', '373220', '005490', '105560', '207940',
    '000270', '068270', '012330', '055550', '051910', '096770',
]

# 한국 시장 종목 한글명 매핑
KR_STOCK_NAMES: Dict[str, str] = {
    '005930': '삼성전자',
    '000660': 'SK하이닉스',
    '005380': '현대차',
    '035420': 'NAVER',
    '035720': '카카오',
    '006400': '삼성SDI',
    '373220': 'LG에너지솔루션',
    '005490': 'POSCO홀딩스',
    '105560': 'KB금융',
    '207940': '삼성바이오로직스',
    '000270': '기아',
    '068270': '셀트리온',
    '012330': '현대모비스',
    '055550': '신한지주',
    '051910': 'LG화학',
    '096770': 'SK이노베이션',
}


class KRMarketAnalyzer:
    """KRX 시가총액 상위 종목의 일일 기술적 분석을 수행하는 클래스"""

    # 매크로 분석: KOSPI, KOSDAQ 지수 + KODEX 섹터 ETF (yfinance 티커)
    MACRO_INDICES: List[str] = ['^KS11', '^KQ11']  # KOSPI, KOSDAQ
    MACRO_SECTORS: Dict[str, str] = {
        '069500.KS': 'KODEX200',           # KOSPI200
        '229200.KS': 'KODEX코스닥150',     # 코스닥150
        '091160.KS': 'KODEX반도체',         # 반도체
        '091170.KS': 'KODEX은행',           # 은행
        '117700.KS': 'KODEX건설',           # 건설
        '266360.KS': 'KODEX자동차',         # 자동차
        '117460.KS': 'KODEX에너지화학',     # 에너지/화학
        '091180.KS': 'KODEX자동차',         # 철강
        '102780.KS': 'KODEX삼성그룹',       # 삼성그룹
        '244580.KS': 'KODEX바이오',         # 바이오
    }
    MACRO_RISK: List[str] = [
        '148070.KS',  # KOSEF 국고채10년
        '132030.KS',  # KODEX골드선물
    ]

    # 섹터 분류 (로테이션 분석용)
    OFFENSIVE_SECTORS: List[str] = [
        '091160.KS', '266360.KS', '244580.KS', '102780.KS',
    ]
    DEFENSIVE_SECTORS: List[str] = [
        '091170.KS', '117700.KS', '117460.KS',
    ]

    # 실패 종목 재시도 설정
    RETRY_MAX_ROUNDS: int = 2
    RETRY_DELAY_SECONDS: int = 30

    def __init__(self, ohlcv_limit: int = 200, api_delay: float = 0.5) -> None:
        """
        Args:
            ohlcv_limit: OHLCV 조회 봉 수 (기본 200)
            api_delay: API 호출 간 대기 시간(초)
        """
        self.ohlcv_limit = ohlcv_limit
        self.api_delay = api_delay
        self.regime_detector = RegimeDetector()

    def analyze(
        self,
        symbols: List[str],
        broker: Any,
        collect_news: bool = True,
        collect_events: bool = True,
    ) -> Dict:
        """
        전체 분석 실행: 데이터 수집 + 지표 계산 + 레짐 감지 + 뉴스 + 이벤트

        Args:
            symbols: 분석 대상 종목 리스트 (6자리 종목코드)
            broker: KoreaInvestmentBroker 인스턴스
            collect_news: 뉴스 수집 여부
            collect_events: 이벤트 캘린더 수집 여부

        Returns:
            구조화된 분석 결과 딕셔너리
        """
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"한국 시장 분석 시작: {today}, {len(symbols)}개 종목")

        stocks_results: Dict[str, Dict] = {}

        # 1차 시도
        for symbol in symbols:
            try:
                result = self._analyze_single_symbol(symbol, broker)
                if result is not None:
                    stocks_results[symbol] = result
            except Exception as e:
                logger.error(f"  {symbol} 분석 실패: {e}", exc_info=True)

        # 실패 종목 재시도
        failed_symbols = [s for s in symbols if s not in stocks_results]
        for retry_round in range(1, self.RETRY_MAX_ROUNDS + 1):
            if not failed_symbols:
                break

            logger.info(
                f"실패 종목 재시도 ({retry_round}/{self.RETRY_MAX_ROUNDS}): "
                f"{', '.join(failed_symbols)} — {self.RETRY_DELAY_SECONDS}초 대기"
            )
            time.sleep(self.RETRY_DELAY_SECONDS)

            still_failed: List[str] = []
            for symbol in failed_symbols:
                try:
                    result = self._analyze_single_symbol(symbol, broker)
                    if result is not None:
                        stocks_results[symbol] = result
                        logger.info(f"  {symbol}: 재시도 {retry_round}회차 성공")
                    else:
                        still_failed.append(symbol)
                except Exception as e:
                    logger.error(f"  {symbol} 재시도 실패: {e}")
                    still_failed.append(symbol)

            failed_symbols = still_failed

        if failed_symbols:
            logger.warning(
                f"최종 실패 종목 ({len(failed_symbols)}개): {', '.join(failed_symbols)}"
            )

        if not stocks_results:
            logger.error("분석 가능한 종목이 없습니다")
            return {'date': today, 'market': 'kr', 'market_summary': {}, 'stocks': {}}

        summary = self._generate_summary(stocks_results)

        result_data: Dict = {
            'date': today,
            'market': 'kr',
            'market_summary': summary,
            'stocks': stocks_results,
        }

        # 뉴스 수집
        if collect_news:
            try:
                news_collector = KRNewsCollector()
                news_data = news_collector.collect(symbols)
                result_data['news'] = news_data
                logger.info(
                    f"한국 뉴스 수집 완료: 시장 {len(news_data.get('market_news', []))}건, "
                    f"종목 {sum(len(v) for v in news_data.get('stock_news', {}).values())}건"
                )
            except ImportError:
                logger.info("KRNewsCollector 미설치 - 뉴스 수집 건너뜀 (feedparser 설치 필요)")
            except Exception as e:
                logger.warning(f"한국 뉴스 수집 실패 (기술적 분석은 정상 진행): {e}")

        # 이벤트 캘린더 수집
        if collect_events:
            try:
                event_collector = KREventCalendarCollector()
                events = event_collector.collect()
                if events:
                    result_data['events'] = events
                    logger.info(
                        f"한국 이벤트 캘린더: "
                        f"금통위 다음={events.get('bok_rate', {}).get('next_date')}"
                    )
            except Exception as e:
                logger.warning(f"한국 이벤트 캘린더 수집 실패: {e}")

        return result_data

    def _analyze_single_symbol(self, symbol: str, broker: Any) -> Optional[Dict]:
        """단일 종목 데이터 수집 및 분석

        Args:
            symbol: 종목 코드 (6자리)
            broker: KoreaInvestmentBroker 인스턴스

        Returns:
            분석 결과 딕셔너리 또는 None
        """
        df = self._fetch_data(symbol, broker)
        if df is None or len(df) < 30:
            logger.warning(f"{symbol}: 데이터 부족 (조회 실패 또는 30봉 미만)")
            return None

        indicators = self._calculate_indicators(df)
        regime = self._detect_regime(df)
        patterns = self._detect_patterns(df['close'].values)

        # 가격 정보
        last_close = float(df['close'].iloc[-1])
        change_1d = self._pct_change(df['close'], 1)
        change_5d = self._pct_change(df['close'], 5)
        change_20d = self._pct_change(df['close'], 20)

        # 시그널 진단
        rsi_val = indicators['rsi']['value']
        signal_diagnosis = self._diagnose_signals(rsi_val, indicators)

        stock_name = KR_STOCK_NAMES.get(symbol, symbol)
        logger.info(
            f"  {symbol}({stock_name}): {last_close:,.0f}원, "
            f"RSI={rsi_val:.1f}, 레짐={regime['state']}"
        )

        # 펀더멘탈 수집 시도 (ticker 정보)
        fundamentals = self._fetch_fundamentals(symbol, broker)

        result: Dict = {
            'name': stock_name,
            'price': {
                'last': last_close,
                'change_1d': change_1d,
                'change_5d': change_5d,
                'change_20d': change_20d,
            },
            'indicators': indicators,
            'regime': regime,
            'patterns': patterns,
            'signal_diagnosis': signal_diagnosis,
        }

        if fundamentals:
            result['fundamentals'] = fundamentals

        return result

    def _fetch_data(self, symbol: str, broker: Any) -> Optional[pd.DataFrame]:
        """KIS 브로커로 국내주식 OHLCV 일봉 조회 (overseas=False)"""
        try:
            df = broker.fetch_ohlcv(
                symbol=symbol,
                timeframe='1d',
                limit=self.ohlcv_limit,
                overseas=False,
            )
            time.sleep(self.api_delay)

            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.debug(f"{symbol} 조회 실패: {e}")

        logger.warning(f"{symbol}: 조회 실패")
        return None

    def _fetch_fundamentals(self, symbol: str, broker: Any) -> Optional[Dict]:
        """KIS 브로커로 종목 기본 정보 조회 (PER/PBR/EPS 등)"""
        try:
            ticker = broker.fetch_ticker(symbol, overseas=False)
            time.sleep(self.api_delay)

            if ticker is None:
                return None

            fundamentals: Dict[str, Any] = {}
            for key in ('per', 'pbr', 'eps', 'bps', 'sector', 'industry'):
                val = ticker.get(key)
                if val is not None:
                    fundamentals[key] = val

            return fundamentals if fundamentals else None
        except Exception as e:
            logger.debug(f"{symbol} 펀더멘탈 조회 실패: {e}")
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
        result: Dict = {'double_bottom': False, 'support_levels': []}

        if len(close_prices) < 30:
            return result

        window = min(60, len(close_prices))
        recent = close_prices[-window:]

        local_mins: List[float] = []
        for i in range(2, len(recent) - 2):
            if (recent[i] <= recent[i - 1] and recent[i] <= recent[i - 2]
                    and recent[i] <= recent[i + 1] and recent[i] <= recent[i + 2]):
                local_mins.append(float(recent[i]))

        # 이중 바닥: 최근 두 저점이 비슷한 수준 (2% 이내)
        if len(local_mins) >= 2:
            last_two = local_mins[-2:]
            diff_pct = abs(last_two[0] - last_two[1]) / max(last_two) * 100
            if diff_pct < 2.0:
                result['double_bottom'] = True

        if local_mins:
            sorted_mins = sorted(local_mins)
            result['support_levels'] = [round(s, 0) for s in sorted_mins[:3]]

        return result

    def _diagnose_signals(self, rsi_val: float, indicators: Dict) -> Dict:
        """현재 지표 기반으로 전략 파라미터 적합성 진단"""
        rsi_35_65_buy = rsi_val < 35
        rsi_35_65_sell = rsi_val > 65

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
        rsi_values: List[float] = []
        notable_events: List[str] = []

        for symbol, data in stocks_results.items():
            stock_name = data.get('name', symbol)
            regime = data['regime']['state']
            if regime == 'BULLISH':
                bullish += 1
            elif regime == 'BEARISH':
                bearish += 1
            else:
                sideways += 1

            rsi_val = data['indicators']['rsi']['value']
            rsi_values.append(rsi_val)

            if rsi_val < 25:
                notable_events.append(f"{stock_name}({symbol}) RSI {rsi_val:.0f} 극단적 과매도")
            elif rsi_val > 75:
                notable_events.append(f"{stock_name}({symbol}) RSI {rsi_val:.0f} 극단적 과매수")

            change_20d = data['price'].get('change_20d', 0)
            if change_20d is not None and change_20d < -10:
                notable_events.append(f"{stock_name}({symbol}) 20일 {change_20d:.1f}% 급락")
            elif change_20d is not None and change_20d > 10:
                notable_events.append(f"{stock_name}({symbol}) 20일 +{change_20d:.1f}% 급등")

            adx_val = data['indicators']['adx']['value']
            if adx_val > 40:
                notable_events.append(f"{stock_name}({symbol}) ADX {adx_val:.0f} 강한 추세")

        avg_rsi = round(float(np.mean(rsi_values)), 1) if rsi_values else 50.0

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
            'notable_events': notable_events[:10],
        }

    def save_json(self, results: Dict, output_dir: str = 'data/market_analysis') -> str:
        """분석 결과를 JSON 파일로 저장 ({date}_kr.json)

        Args:
            results: analyze() 반환값
            output_dir: 저장 디렉토리

        Returns:
            저장된 파일 경로
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        date_str = results.get('date', datetime.now().strftime('%Y-%m-%d'))
        file_path = output_path / f"{date_str}_kr.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"한국 시장 분석 결과 저장: {file_path}")
        return str(file_path)

    # ─── 매크로 시장 분석 ───

    def analyze_macro(self) -> Optional[Dict]:
        """
        yfinance를 사용하여 한국 매크로 시장 환경 분석
        (KOSPI/KOSDAQ 지수, KODEX 섹터 ETF, 리스크 자산)

        Returns:
            매크로 분석 결과 딕셔너리 또는 None
        """
        if not _has_yfinance:
            logger.info("yfinance 미설치 - 매크로 분석 건너뜀 (pip install yfinance)")
            return None

        logger.info("한국 매크로 시장 분석 시작")

        macro_data = self._fetch_macro_data()
        if not macro_data:
            logger.warning("한국 매크로 데이터 다운로드 실패")
            return None

        # 1. 지수 분석
        indices: Dict[str, Dict] = {}
        for symbol in self.MACRO_INDICES:
            if symbol in macro_data:
                analysis = self._analyze_macro_symbol(macro_data[symbol])
                if analysis is not None:
                    indices[symbol] = analysis

        # 2. 섹터 ETF 분석 + 순위
        sectors = self._calc_sector_rankings(macro_data)

        # 3. 로테이션 감지
        rotation = self._detect_rotation(sectors)

        # 4. 시장 폭(breadth) 분석
        breadth = self._calc_breadth(indices, sectors)

        # 5. 리스크 환경 평가
        risk_env = self._assess_risk_env(macro_data)

        # 6. 종합 요약
        overall = self._generate_macro_summary(indices, sectors, rotation, breadth, risk_env)

        result: Dict = {
            'collected_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'indices': indices,
            'sectors': sectors,
            'rotation': rotation,
            'breadth': breadth,
            'risk_environment': risk_env,
            'overall': overall,
        }

        logger.info(f"한국 매크로 분석 완료: {overall[:80]}...")
        return result

    def _fetch_macro_data(self) -> Dict[str, pd.DataFrame]:
        """yf.download()로 한국 매크로 심볼 데이터를 한 번에 다운로드"""
        all_symbols = (
            self.MACRO_INDICES
            + list(self.MACRO_SECTORS.keys())
            + self.MACRO_RISK
        )

        try:
            raw = yf.download(
                all_symbols,
                period='1y',
                interval='1d',
                progress=False,
                group_by='ticker',
            )
        except Exception as e:
            logger.warning(f"yfinance 다운로드 실패: {e}")
            return {}

        if raw is None or raw.empty:
            logger.warning("yfinance 다운로드 결과가 비어 있습니다")
            return {}

        result: Dict[str, pd.DataFrame] = {}

        for symbol in all_symbols:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if symbol not in raw.columns.get_level_values(0):
                        logger.debug(f"{symbol}: 다운로드 데이터 없음")
                        continue
                    df = raw[symbol].copy()
                else:
                    df = raw.copy()

                df = df.dropna(subset=['Close'])
                if df.empty or len(df) < 30:
                    logger.debug(f"{symbol}: 데이터 부족 ({len(df)}봉)")
                    continue

                result[symbol] = df
            except Exception as e:
                logger.debug(f"{symbol} 데이터 처리 실패: {e}")
                continue

        logger.info(f"한국 매크로 데이터 다운로드 완료: {len(result)}/{len(all_symbols)}개 심볼")
        return result

    def _analyze_macro_symbol(self, df: pd.DataFrame) -> Optional[Dict]:
        """개별 매크로 심볼에 대한 기술적 분석"""
        if df is None or len(df) < 30:
            return None

        try:
            close = df['Close'].astype(float)
            volume = df['Volume'].astype(float)

            last = float(close.iloc[-1])
            chg_1d = self._pct_change(close, 1)
            chg_5d = self._pct_change(close, 5)
            chg_20d = self._pct_change(close, 20)

            rsi = self._calc_rsi(close, period=14)
            rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

            vol_5d_avg = float(volume.iloc[-5:].mean()) if len(volume) >= 5 else float(volume.mean())
            vol_20d_avg = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
            vol_ratio = round(vol_5d_avg / vol_20d_avg, 2) if vol_20d_avg > 0 else 1.0

            return {
                'last': round(last, 2),
                'chg_1d': chg_1d,
                'chg_5d': chg_5d,
                'chg_20d': chg_20d,
                'rsi': round(rsi_val, 1),
                'vol_ratio': vol_ratio,
            }
        except Exception as e:
            logger.debug(f"매크로 심볼 분석 실패: {e}")
            return None

    def _calc_sector_rankings(self, macro_data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """섹터 ETF의 5일/20일 수익률 기준 순위"""
        sectors: Dict[str, Dict] = {}

        for symbol, name in self.MACRO_SECTORS.items():
            if symbol not in macro_data:
                continue
            analysis = self._analyze_macro_symbol(macro_data[symbol])
            if analysis is None:
                continue
            analysis['name'] = name
            sectors[symbol] = analysis

        if not sectors:
            return {}

        sorted_by_5d = sorted(
            sectors.keys(),
            key=lambda s: sectors[s].get('chg_5d') or 0.0,
            reverse=True,
        )
        for rank, symbol in enumerate(sorted_by_5d, 1):
            sectors[symbol]['rank_5d'] = rank

        sorted_by_20d = sorted(
            sectors.keys(),
            key=lambda s: sectors[s].get('chg_20d') or 0.0,
            reverse=True,
        )
        for rank, symbol in enumerate(sorted_by_20d, 1):
            sectors[symbol]['rank_20d'] = rank

        return sectors

    def _detect_rotation(self, sectors: Dict[str, Dict]) -> Dict:
        """공격적 섹터 vs 방어적 섹터 평균 5일 수익률 비교"""
        offensive_returns: List[float] = []
        for s in self.OFFENSIVE_SECTORS:
            if s in sectors and sectors[s].get('chg_5d') is not None:
                offensive_returns.append(sectors[s]['chg_5d'])

        defensive_returns: List[float] = []
        for s in self.DEFENSIVE_SECTORS:
            if s in sectors and sectors[s].get('chg_5d') is not None:
                defensive_returns.append(sectors[s]['chg_5d'])

        offensive_avg = round(float(np.mean(offensive_returns)), 2) if offensive_returns else 0.0
        defensive_avg = round(float(np.mean(defensive_returns)), 2) if defensive_returns else 0.0
        diff = round(offensive_avg - defensive_avg, 2)

        if diff > 1.0:
            signal = "공격적 로테이션 (리스크온)"
        elif diff < -1.0:
            signal = "방어적 로테이션 (리스크오프)"
        else:
            signal = "뚜렷한 로테이션 없음 (중립)"

        return {
            'offensive_avg_5d': offensive_avg,
            'defensive_avg_5d': defensive_avg,
            'diff': diff,
            'signal': signal,
        }

    def _calc_breadth(self, indices: Dict[str, Dict], sectors: Dict[str, Dict]) -> Dict:
        """시장 폭 분석: KOSPI vs KOSDAQ, 섹터 긍정/부정 비율"""
        kospi_5d = indices.get('^KS11', {}).get('chg_5d') or 0.0
        kosdaq_5d = indices.get('^KQ11', {}).get('chg_5d') or 0.0

        kospi_vs_kosdaq = round(kospi_5d - kosdaq_5d, 1)

        positive_count = sum(
            1 for s in sectors.values()
            if s.get('chg_5d') is not None and s['chg_5d'] > 0
        )
        negative_count = sum(
            1 for s in sectors.values()
            if s.get('chg_5d') is not None and s['chg_5d'] <= 0
        )

        parts: List[str] = []
        if kosdaq_5d > kospi_5d + 0.5:
            parts.append("코스닥 상대 강세로 중소형주 선호")
        elif kospi_5d > kosdaq_5d + 0.5:
            parts.append("코스피 대형주 쏠림으로 시장 폭 협소")
        else:
            parts.append("코스피/코스닥 균형")

        if positive_count >= 7:
            parts.append("대다수 섹터 상승으로 광범위한 강세")
        elif negative_count >= 7:
            parts.append("대다수 섹터 하락으로 광범위한 약세")
        else:
            parts.append(f"섹터 혼조 (상승 {positive_count}개, 하락 {negative_count}개)")

        interpretation = ". ".join(parts)

        return {
            'kospi_vs_kosdaq_5d': kospi_vs_kosdaq,
            'sectors_positive_5d': positive_count,
            'sectors_negative_5d': negative_count,
            'interpretation': interpretation,
        }

    def _assess_risk_env(self, macro_data: Dict[str, pd.DataFrame]) -> Dict:
        """국고채10년(148070), 금(132030) 5일 수익률로 리스크 환경 판단"""
        bond_chg: Optional[float] = None
        gold_chg: Optional[float] = None

        if '148070.KS' in macro_data:
            analysis = self._analyze_macro_symbol(macro_data['148070.KS'])
            if analysis is not None:
                bond_chg = analysis.get('chg_5d')

        if '132030.KS' in macro_data:
            analysis = self._analyze_macro_symbol(macro_data['132030.KS'])
            if analysis is not None:
                gold_chg = analysis.get('chg_5d')

        bond_val = bond_chg if bond_chg is not None else 0.0
        gold_val = gold_chg if gold_chg is not None else 0.0

        bond_dir = 'up' if bond_val > 0.5 else ('down' if bond_val < -0.5 else 'neutral')
        gold_dir = 'up' if gold_val > 0.5 else ('down' if gold_val < -0.5 else 'neutral')

        if bond_dir == 'up' and gold_dir == 'up':
            assessment = "리스크오프 (안전자산 선호)"
        elif bond_dir == 'down' and gold_dir == 'down':
            assessment = "리스크온 (위험자산 선호)"
        else:
            assessment = "혼조 (방향성 불확실)"

        return {
            'bond_chg_5d': bond_val,
            'gold_chg_5d': gold_val,
            'assessment': assessment,
        }

    def _generate_macro_summary(
        self,
        indices: Dict[str, Dict],
        sectors: Dict[str, Dict],
        rotation: Dict,
        breadth: Dict,
        risk_env: Dict,
    ) -> str:
        """매크로 분석 결과를 종합하여 한줄 요약 문자열 생성"""
        parts: List[str] = []

        if sectors:
            sorted_sectors = sorted(
                sectors.items(),
                key=lambda x: x[1].get('chg_5d') or 0.0,
                reverse=True,
            )
            best = sorted_sectors[0]
            worst = sorted_sectors[-1]
            best_name = best[1].get('name', best[0])
            worst_name = worst[1].get('name', worst[0])
            best_chg = best[1].get('chg_5d') or 0.0
            worst_chg = worst[1].get('chg_5d') or 0.0

            if worst_chg < -1.0:
                parts.append(f"{worst_name} 약세({worst_chg:+.1f}%) 속 {best_name}({best_chg:+.1f}%) 강세")
            elif best_chg > 1.0:
                if len(sorted_sectors) >= 2:
                    second = sorted_sectors[1]
                    second_name = second[1].get('name', second[0])
                    second_chg = second[1].get('chg_5d') or 0.0
                    parts.append(
                        f"{best_name}({best_chg:+.1f}%)/{second_name}({second_chg:+.1f}%) 강세"
                    )
                else:
                    parts.append(f"{best_name}({best_chg:+.1f}%) 강세")
            else:
                parts.append(
                    f"섹터 전반 보합권 ({best_name} {best_chg:+.1f}% ~ {worst_name} {worst_chg:+.1f}%)"
                )

        rotation_signal = rotation.get('signal', '')
        if '공격적' in rotation_signal:
            parts.append("공격적 로테이션 진행 중")
        elif '방어적' in rotation_signal:
            parts.append("방어적 로테이션 진행 중")

        kospi_data = indices.get('^KS11', {})
        kosdaq_data = indices.get('^KQ11', {})
        kospi_5d = kospi_data.get('chg_5d') or 0.0
        kosdaq_5d = kosdaq_data.get('chg_5d') or 0.0
        if kosdaq_5d > kospi_5d + 0.5:
            parts.append("코스닥 상대 강세로 중소형주 선호")
        elif kospi_5d > kosdaq_5d + 0.5:
            parts.append("대형주 쏠림으로 시장 폭 협소")

        assessment = risk_env.get('assessment', '')
        if '리스크오프' in assessment:
            parts.append("안전자산 선호 흐름")
        elif '리스크온' in assessment:
            parts.append("위험자산 선호 흐름")

        return ". ".join(parts) + "." if parts else "매크로 데이터 부족으로 요약 불가."

    # ─── 전일 대비 변화 분석 ───

    @staticmethod
    def _load_previous_day_json(today: str, data_dir: str = "data/market_analysis") -> Optional[Dict]:
        """전날(또는 가장 최근) 한국 분석 JSON 로드."""
        import glob

        pattern = os.path.join(data_dir, "*_kr.json")
        files = sorted(glob.glob(pattern))

        previous_files = [f for f in files if not f.endswith(f"{today}_kr.json")]
        if not previous_files:
            return None

        latest_file = previous_files[-1]
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"이전 한국 분석 로드: {latest_file}")
            return data
        except Exception as e:
            logger.warning(f"이전 한국 분석 로드 실패: {e}")
            return None

    @staticmethod
    def _calculate_daily_changes(current_data: Dict, previous_data: Dict) -> Dict:
        """전일 대비 주요 변화 계산."""
        changes: Dict = {
            'has_previous': True,
            'previous_date': previous_data.get('date', 'unknown'),
            'stocks': {},
        }

        curr_stocks = current_data.get('stocks', {})
        prev_stocks = previous_data.get('stocks', {})
        for symbol in curr_stocks:
            if symbol in prev_stocks:
                curr_price = curr_stocks[symbol].get('price', {}).get('last')
                prev_price = prev_stocks[symbol].get('price', {}).get('last')
                curr_rsi = curr_stocks[symbol].get('indicators', {}).get('rsi', {}).get('value')
                prev_rsi = prev_stocks[symbol].get('indicators', {}).get('rsi', {}).get('value')

                stock_change: Dict = {}
                if curr_price and prev_price and prev_price > 0:
                    stock_change['price_change_pct'] = round((curr_price - prev_price) / prev_price * 100, 2)
                if curr_rsi is not None and prev_rsi is not None:
                    stock_change['rsi_change'] = round(curr_rsi - prev_rsi, 1)

                if stock_change:
                    changes['stocks'][symbol] = stock_change

        return changes

    # ─── 지표 계산 헬퍼 (MarketAnalyzer와 동일) ───

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
