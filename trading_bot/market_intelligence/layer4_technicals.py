"""
Layer 4: Enhanced Individual Stock Technicals - 개별 종목 기술적 분석.

기존 5개 지표(RSI, MACD, Bollinger, Stochastic, ADX)에 추가로
OBV, MFI, ATR, MA Cross, Volume Analysis를 계산하여
개별 종목의 기술적 건강성을 종합 평가합니다.

Indicator weights:
    - rsi (0.12), macd (0.12), bollinger (0.10)
    - stochastic (0.10), adx (0.08)
    - obv (0.10), mfi (0.10), atr (0.08)
    - ma_cross (0.10), volume (0.10)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import calc_rsi, weighted_composite

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

INDICATOR_WEIGHTS: Dict[str, float] = {
    'rsi': 0.12,
    'macd': 0.12,
    'bollinger': 0.10,
    'stochastic': 0.10,
    'adx': 0.08,
    'obv': 0.10,
    'mfi': 0.10,
    'atr': 0.08,
    'ma_cross': 0.10,
    'volume': 0.10,
}


class TechnicalsLayer(BaseIntelligenceLayer):
    """Layer 4: 종합 기술적 분석 레이어.

    기존 MarketAnalyzer의 5개 지표를 통과시키고,
    OBV, MFI, ATR, MA Cross, Volume Analysis 5개를 추가 계산합니다.
    종목별 합성 기술적 점수를 산출합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="technicals")

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """종합 기술적 분석 실행.

        Args:
            data: 분석 데이터 딕셔너리
                - 'stocks': {symbol: {'price': {...}, 'indicators': {...}}} 기존 분석 결과
                - 'cache': MarketDataCache (yfinance 데이터)
                - 'stock_symbols': List[str] 분석 대상 심볼 목록

        Returns:
            LayerResult with per-stock technical scores
        """
        stocks = data.get('stocks', {})
        cache = data.get('cache')
        stock_symbols = data.get('stock_symbols', [])

        if not stock_symbols and stocks:
            stock_symbols = list(stocks.keys())

        if not stock_symbols:
            return self._empty_result("분석 대상 종목 없음")

        # 종목별 기술적 점수 계산
        per_stock: Dict[str, Dict[str, Any]] = {}
        composite_scores: List[float] = []

        for symbol in stock_symbols:
            stock_data = stocks.get(symbol, {})
            df = self._get_ohlcv(cache, symbol) if cache else None

            stock_result = self._analyze_stock(symbol, stock_data, df)
            per_stock[symbol] = stock_result

            if stock_result.get('composite_score') is not None:
                composite_scores.append(stock_result['composite_score'])

        if not composite_scores:
            return self._empty_result("기술적 점수 계산 불가")

        # 레이어 전체 점수: 종목 평균
        avg_score = float(np.mean(composite_scores))
        signal = self.classify_score(avg_score)

        # 상위/하위 종목 정렬
        sorted_stocks = sorted(
            [(s, d.get('composite_score', 0.0)) for s, d in per_stock.items()
             if d.get('composite_score') is not None],
            key=lambda x: x[1],
            reverse=True,
        )
        top_stocks = [s for s, _ in sorted_stocks[:3]]
        bottom_stocks = [s for s, _ in sorted_stocks[-3:]]

        confidence = min(1.0, len(composite_scores) / max(len(stock_symbols), 1))

        interpretation = self._build_interpretation(
            avg_score, top_stocks, bottom_stocks
        )

        return LayerResult(
            layer_name=self.name,
            score=round(avg_score, 1),
            signal=signal,
            confidence=round(confidence, 2),
            metrics={
                'avg_composite': round(avg_score, 1),
                'num_stocks_analyzed': len(composite_scores),
            },
            interpretation=interpretation,
            details={
                'per_stock': per_stock,
                'top_stocks': top_stocks,
                'bottom_stocks': bottom_stocks,
            },
        )

    # ──────────────────────────────────────────────────────────────
    # Per-stock analysis
    # ──────────────────────────────────────────────────────────────

    def _analyze_stock(
        self,
        symbol: str,
        stock_data: Dict[str, Any],
        df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """개별 종목의 10개 지표를 계산하고 합성 점수 산출.

        Args:
            symbol: 티커 심볼
            stock_data: MarketAnalyzer 기존 분석 결과
            df: OHLCV DataFrame (yfinance)

        Returns:
            종목별 결과 딕셔너리
        """
        indicators = stock_data.get('indicators', {})
        scores: Dict[str, float] = {}

        # ── 기존 5개 지표 점수 (pass-through) ──
        scores['rsi'] = self._score_rsi(indicators.get('rsi', {}))
        scores['macd'] = self._score_macd(indicators.get('macd', {}))
        scores['bollinger'] = self._score_bollinger(indicators.get('bollinger', {}))
        scores['stochastic'] = self._score_stochastic(indicators.get('stochastic', {}))
        scores['adx'] = self._score_adx(indicators.get('adx', {}))

        # ── 새 5개 지표 계산 (OHLCV 데이터 필요) ──
        if df is not None and not df.empty and len(df) >= 30:
            close = self._extract_col(df, 'Close')
            high = self._extract_col(df, 'High')
            low = self._extract_col(df, 'Low')
            volume = self._extract_col(df, 'Volume')

            if close is not None and high is not None and low is not None:
                scores['obv'] = self._score_obv(close, volume)
                scores['mfi'] = self._score_mfi(high, low, close, volume)
                scores['atr'] = self._score_atr(high, low, close)
                scores['ma_cross'] = self._score_ma_cross(close)
                scores['volume'] = self._score_volume(close, volume)
            else:
                for ind in ['obv', 'mfi', 'atr', 'ma_cross', 'volume']:
                    scores[ind] = 0.0
        else:
            for ind in ['obv', 'mfi', 'atr', 'ma_cross', 'volume']:
                scores[ind] = 0.0

        # NaN 처리
        clean_scores = {
            k: v if not np.isnan(v) else 0.0 for k, v in scores.items()
        }

        composite = weighted_composite(clean_scores, INDICATOR_WEIGHTS)

        return {
            'symbol': symbol,
            'indicator_scores': {k: round(v, 1) for k, v in clean_scores.items()},
            'composite_score': round(composite, 1),
            'signal': self.classify_score(composite),
        }

    # ──────────────────────────────────────────────────────────────
    # Existing indicator scoring (from MarketAnalyzer data)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _score_rsi(rsi_data: Dict[str, Any]) -> float:
        """RSI 점수 매핑.

        < 30 -> +50 to +100 (oversold = buy opportunity)
        > 70 -> -50 to -100 (overbought)
        30-70 -> proportional mapping
        """
        value = rsi_data.get('value')
        if value is None:
            return 0.0

        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0

        if value < 20:
            return 100.0
        elif value < 30:
            # 20-30 -> +50 to +100
            return 50.0 + (30.0 - value) / 10.0 * 50.0
        elif value < 45:
            # 30-45 -> 0 to +50
            return (45.0 - value) / 15.0 * 50.0
        elif value <= 55:
            return 0.0
        elif value <= 70:
            # 55-70 -> 0 to -50
            return -(value - 55.0) / 15.0 * 50.0
        elif value <= 80:
            # 70-80 -> -50 to -100
            return -50.0 - (value - 70.0) / 10.0 * 50.0
        else:
            return -100.0

    @staticmethod
    def _score_macd(macd_data: Dict[str, Any]) -> float:
        """MACD 히스토그램 기반 점수.

        histogram > 0 -> positive, < 0 -> negative.
        """
        histogram = macd_data.get('histogram')
        if histogram is None:
            return 0.0

        try:
            histogram = float(histogram)
        except (TypeError, ValueError):
            return 0.0

        # 히스토그램을 점수로 변환 (일반적으로 -5 ~ +5 범위)
        score = histogram * 20.0
        return max(-100.0, min(100.0, score))

    @staticmethod
    def _score_bollinger(bb_data: Dict[str, Any]) -> float:
        """Bollinger %B 기반 점수.

        < 0.2 -> positive (near lower band = buy)
        > 0.8 -> negative (near upper band = sell)
        """
        pct_b = bb_data.get('pct_b')
        if pct_b is None:
            return 0.0

        try:
            pct_b = float(pct_b)
        except (TypeError, ValueError):
            return 0.0

        # 0 ~ 1 -> +100 ~ -100
        if pct_b < 0.0:
            return 100.0
        elif pct_b > 1.0:
            return -100.0

        return (0.5 - pct_b) * 200.0

    @staticmethod
    def _score_stochastic(stoch_data: Dict[str, Any]) -> float:
        """Stochastic 점수 (RSI와 유사한 존 스코어링).

        < 20 -> +50 to +100 (oversold)
        > 80 -> -50 to -100 (overbought)
        """
        k_val = stoch_data.get('k')
        if k_val is None:
            return 0.0

        try:
            k_val = float(k_val)
        except (TypeError, ValueError):
            return 0.0

        if k_val < 10:
            return 100.0
        elif k_val < 20:
            return 50.0 + (20.0 - k_val) / 10.0 * 50.0
        elif k_val < 40:
            return (40.0 - k_val) / 20.0 * 50.0
        elif k_val <= 60:
            return 0.0
        elif k_val <= 80:
            return -(k_val - 60.0) / 20.0 * 50.0
        elif k_val <= 90:
            return -50.0 - (k_val - 80.0) / 10.0 * 50.0
        else:
            return -100.0

    @staticmethod
    def _score_adx(adx_data: Dict[str, Any]) -> float:
        """ADX 점수.

        ADX > 25 = stronger trend. 트렌드 방향에 따라 부호 결정.
        """
        value = adx_data.get('value')
        trend = adx_data.get('trend', '')

        if value is None:
            return 0.0

        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0

        # ADX 강도 (0 ~ 100)
        strength = min(value / 50.0, 1.0) * 50.0

        # 트렌드 방향에 따라 부호 결정
        if isinstance(trend, str):
            if 'bull' in trend.lower() or 'up' in trend.lower():
                return strength
            elif 'bear' in trend.lower() or 'down' in trend.lower():
                return -strength
            elif 'strong' in trend.lower():
                return strength * 0.5  # 방향 모를 때 약간 긍정적
        return 0.0

    # ──────────────────────────────────────────────────────────────
    # New indicator calculations (from OHLCV data)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _score_obv(
        close: pd.Series, volume: Optional[pd.Series]
    ) -> float:
        """OBV (On-Balance Volume) 점수.

        OBV = cumsum(volume * sign(close.diff()))
        OBV > 20MA -> +50, < 20MA -> -50
        Price-OBV divergence = stronger signal.

        Args:
            close: 종가 시리즈
            volume: 거래량 시리즈

        Returns:
            -100 ~ +100 점수
        """
        if volume is None or len(close) < 25 or len(volume) < 25:
            return 0.0

        # OBV 계산
        direction = np.sign(close.diff()).fillna(0)
        obv = (volume * direction).cumsum()

        if len(obv) < 21:
            return 0.0

        obv_ma20 = obv.rolling(20).mean()

        current_obv = float(obv.iloc[-1])
        current_ma20 = float(obv_ma20.iloc[-1])

        if np.isnan(current_obv) or np.isnan(current_ma20):
            return 0.0

        # OBV vs 20MA
        if current_ma20 == 0:
            base_score = 0.0
        else:
            deviation = (current_obv - current_ma20) / abs(current_ma20)
            base_score = max(-50.0, min(50.0, deviation * 100.0))

        # Price-OBV 다이버전스 체크
        price_change_5d = 0.0
        if len(close) > 5:
            prev_price = float(close.iloc[-6])
            if prev_price != 0:
                price_change_5d = (float(close.iloc[-1]) - prev_price) / prev_price

        obv_change_5d = 0.0
        if len(obv) > 5:
            prev_obv = float(obv.iloc[-6])
            if prev_obv != 0:
                obv_change_5d = (float(obv.iloc[-1]) - prev_obv) / abs(prev_obv)

        # 다이버전스 보너스
        divergence_bonus = 0.0
        if price_change_5d > 0.01 and obv_change_5d < -0.01:
            # 가격 상승 + OBV 하락 = bearish divergence
            divergence_bonus = -30.0
        elif price_change_5d < -0.01 and obv_change_5d > 0.01:
            # 가격 하락 + OBV 상승 = bullish divergence
            divergence_bonus = 30.0

        return max(-100.0, min(100.0, base_score + divergence_bonus))

    @staticmethod
    def _score_mfi(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: Optional[pd.Series],
        period: int = 14,
    ) -> float:
        """MFI (Money Flow Index) 점수.

        MFI = 100 - 100/(1 + money_ratio)
        < 20 = oversold (bullish), > 80 = overbought (bearish)

        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            volume: 거래량 시리즈
            period: MFI 기간

        Returns:
            -100 ~ +100 점수
        """
        if volume is None or len(close) < period + 5:
            return 0.0

        typical_price = (high + low + close) / 3.0
        raw_money_flow = typical_price * volume

        tp_diff = typical_price.diff()

        positive_flow = raw_money_flow.where(tp_diff > 0, 0.0)
        negative_flow = raw_money_flow.where(tp_diff < 0, 0.0)

        positive_sum = positive_flow.rolling(period).sum()
        negative_sum = negative_flow.rolling(period).sum()

        # money ratio
        money_ratio = positive_sum / negative_sum.replace(0, np.nan)
        mfi = 100 - (100 / (1 + money_ratio))

        current_mfi = mfi.iloc[-1]
        if np.isnan(current_mfi):
            return 0.0

        current_mfi = float(current_mfi)

        # RSI와 같은 존 스코어링
        if current_mfi < 10:
            return 100.0
        elif current_mfi < 20:
            return 50.0 + (20.0 - current_mfi) / 10.0 * 50.0
        elif current_mfi < 40:
            return (40.0 - current_mfi) / 20.0 * 50.0
        elif current_mfi <= 60:
            return 0.0
        elif current_mfi <= 80:
            return -(current_mfi - 60.0) / 20.0 * 50.0
        elif current_mfi <= 90:
            return -50.0 - (current_mfi - 80.0) / 10.0 * 50.0
        else:
            return -100.0

    @staticmethod
    def _score_atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> float:
        """ATR (Average True Range) 점수.

        ATR as % of price > 3% = high volatility (slight negative / risk).
        20d expansion/contraction 추가 분석.

        Args:
            high: 고가 시리즈
            low: 저가 시리즈
            close: 종가 시리즈
            period: ATR 기간

        Returns:
            -100 ~ +100 점수
        """
        if len(close) < period + 5:
            return 0.0

        # True Range 계산
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        current_atr = float(atr.iloc[-1])
        current_price = float(close.iloc[-1])

        if np.isnan(current_atr) or np.isnan(current_price) or current_price == 0:
            return 0.0

        atr_pct = current_atr / current_price * 100

        # 20일 ATR 확장/수축
        if len(atr.dropna()) >= 21:
            atr_20d_ago = float(atr.dropna().iloc[-21])
            if atr_20d_ago > 0:
                atr_change = (current_atr - atr_20d_ago) / atr_20d_ago
            else:
                atr_change = 0.0
        else:
            atr_change = 0.0

        # 높은 변동성 = 리스크 (약간 부정적)
        # ATR% < 1% = 매우 낮은 변동성 -> +20
        # ATR% 1-2% = 정상 -> 0
        # ATR% 2-3% = 다소 높음 -> -20
        # ATR% > 3% = 높음 -> -40 ~ -60
        if atr_pct < 1.0:
            base_score = 20.0
        elif atr_pct < 2.0:
            base_score = 0.0
        elif atr_pct < 3.0:
            base_score = -20.0 * (atr_pct - 2.0)
        else:
            base_score = -20.0 - min(40.0, (atr_pct - 3.0) * 20.0)

        # 변동성 확장 = 부정적, 수축 = 긍정적
        expansion_penalty = 0.0
        if atr_change > 0.2:  # 20%+ 확장
            expansion_penalty = -min(30.0, atr_change * 50.0)
        elif atr_change < -0.2:  # 20%+ 수축
            expansion_penalty = min(20.0, abs(atr_change) * 30.0)

        return max(-100.0, min(100.0, base_score + expansion_penalty))

    @staticmethod
    def _score_ma_cross(close: pd.Series) -> float:
        """50MA/200MA 크로스 점수.

        Above both MAs = +80, Golden Cross = +100.
        Death Cross = -100, Below both = -80.

        Args:
            close: 종가 시리즈

        Returns:
            -100 ~ +100 점수
        """
        if len(close) < 201:
            # 200MA 계산 불가 -> 50MA만 사용
            if len(close) < 51:
                return 0.0
            ma50 = close.rolling(50).mean()
            current_price = float(close.iloc[-1])
            current_ma50 = float(ma50.iloc[-1])
            if np.isnan(current_ma50):
                return 0.0
            return 40.0 if current_price > current_ma50 else -40.0

        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        current_price = float(close.iloc[-1])
        current_ma50 = float(ma50.iloc[-1])
        current_ma200 = float(ma200.iloc[-1])

        if np.isnan(current_ma50) or np.isnan(current_ma200):
            return 0.0

        above_50 = current_price > current_ma50
        above_200 = current_price > current_ma200
        ma50_above_200 = current_ma50 > current_ma200

        # Golden Cross / Death Cross 감지 (최근 5일 이내)
        recent_ma50 = ma50.iloc[-6:-1].dropna()
        recent_ma200 = ma200.iloc[-6:-1].dropna()

        golden_cross = False
        death_cross = False

        if len(recent_ma50) >= 1 and len(recent_ma200) >= 1:
            prev_ma50_above = float(recent_ma50.iloc[0]) > float(recent_ma200.iloc[0])
            if ma50_above_200 and not prev_ma50_above:
                golden_cross = True
            elif not ma50_above_200 and prev_ma50_above:
                death_cross = True

        if golden_cross:
            return 100.0
        elif death_cross:
            return -100.0
        elif above_50 and above_200:
            return 80.0
        elif above_50 and not above_200:
            return 20.0
        elif not above_50 and above_200:
            return -20.0
        else:
            return -80.0

    @staticmethod
    def _score_volume(
        close: pd.Series, volume: Optional[pd.Series]
    ) -> float:
        """거래량 분석 점수.

        5d/20d 거래량 비율 + 가격-거래량 다이버전스 분석.

        Args:
            close: 종가 시리즈
            volume: 거래량 시리즈

        Returns:
            -100 ~ +100 점수
        """
        if volume is None or len(close) < 25 or len(volume) < 25:
            return 0.0

        vol_5d = volume.tail(5).mean()
        vol_20d = volume.tail(20).mean()

        if np.isnan(vol_5d) or np.isnan(vol_20d) or vol_20d == 0:
            return 0.0

        vol_ratio = float(vol_5d / vol_20d)

        # 가격 추세 판단 (5일)
        if len(close) > 5:
            price_start = float(close.iloc[-6])
            price_end = float(close.iloc[-1])
            if price_start != 0:
                price_trend = (price_end - price_start) / price_start
            else:
                price_trend = 0.0
        else:
            price_trend = 0.0

        score = 0.0

        # 거래량 확대 + 가격 상승 = 확인 (bullish)
        if vol_ratio > 1.2 and price_trend > 0.01:
            score = min(50.0, (vol_ratio - 1.0) * 50.0 + price_trend * 500.0)

        # 거래량 확대 + 가격 하락 = 확인 (bearish)
        elif vol_ratio > 1.2 and price_trend < -0.01:
            score = max(-50.0, -(vol_ratio - 1.0) * 50.0 + price_trend * 500.0)

        # 거래량 축소 + 가격 상승 = bearish divergence
        elif vol_ratio < 0.8 and price_trend > 0.01:
            score = -min(50.0, (1.0 - vol_ratio) * 80.0)

        # 거래량 축소 + 가격 하락 = bullish divergence (selling exhaustion)
        elif vol_ratio < 0.8 and price_trend < -0.01:
            score = min(50.0, (1.0 - vol_ratio) * 80.0)

        return max(-100.0, min(100.0, score))

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_ohlcv(cache: Any, symbol: str) -> Optional[pd.DataFrame]:
        """캐시에서 OHLCV DataFrame 조회.

        Args:
            cache: MarketDataCache 인스턴스
            symbol: 티커 심볼

        Returns:
            OHLCV DataFrame 또는 None
        """
        if cache is None:
            return None
        return cache.get(symbol)

    @staticmethod
    def _extract_col(
        df: pd.DataFrame, col_name: str
    ) -> Optional[pd.Series]:
        """DataFrame에서 컬럼 추출 (대소문자 무관).

        Args:
            df: DataFrame
            col_name: 컬럼 이름 (대소문자 무관)

        Returns:
            시리즈 또는 None
        """
        for c in [col_name, col_name.lower(), col_name.upper()]:
            if c in df.columns:
                return df[c]
        return None

    def _empty_result(self, reason: str) -> LayerResult:
        """데이터 부족 시 기본 결과 반환.

        Args:
            reason: 결과가 비어있는 이유

        Returns:
            중립 LayerResult
        """
        return LayerResult(
            layer_name=self.name,
            score=0.0,
            signal="neutral",
            confidence=0.0,
            metrics={},
            interpretation=f"기술적 분석 불가: {reason}",
            details={'error': reason},
        )

    def _build_interpretation(
        self,
        avg_score: float,
        top_stocks: List[str],
        bottom_stocks: List[str],
    ) -> str:
        """한국어 해석 문자열 생성.

        Args:
            avg_score: 평균 합성 점수
            top_stocks: 상위 종목 리스트
            bottom_stocks: 하위 종목 리스트

        Returns:
            한국어 해석 문자열
        """
        parts = [f"기술적 종합 점수 {avg_score:.1f}"]

        if top_stocks:
            parts.append(f"매수 유망 종목: {', '.join(top_stocks[:3])}")
        if bottom_stocks:
            parts.append(f"주의 종목: {', '.join(bottom_stocks[:3])}")

        return ", ".join(parts)
