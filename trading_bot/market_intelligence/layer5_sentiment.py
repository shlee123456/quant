"""
Layer 5: Sentiment & Positioning - 심리 및 포지셔닝 분석.

다양한 심리/포지셔닝 지표를 결합하여 시장 참여자의 극단적 심리를 감지하고
역발상(contrarian) 시그널을 제공합니다.

Sub-metrics:
    - fear_greed (0.30): CNN Fear & Greed Index 기반 역발상 시그널
    - vix_sentiment (0.20): VIX 수준 기반 심리 판단
    - news_sentiment (0.20): 뉴스 헤드라인 키워드 감성 분석
    - smart_money (0.30): GLD/SPY 비율 모멘텀 기반 기관 리스크 선호도
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import momentum_score, pct_change, weighted_composite

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

SUB_WEIGHTS: Dict[str, float] = {
    'fear_greed': 0.30,
    'vix_sentiment': 0.20,
    'news_sentiment': 0.20,
    'smart_money': 0.30,
}

POSITIVE_WORDS = frozenset({
    'surge', 'rally', 'gain', 'soar', 'beat', 'upgrade', 'bullish',
    'record', 'growth', 'strong', 'outperform', 'breakout', 'buy',
    'positive', 'optimistic',
})

NEGATIVE_WORDS = frozenset({
    'crash', 'plunge', 'drop', 'fall', 'miss', 'downgrade', 'bearish',
    'recession', 'weak', 'underperform', 'decline', 'fear', 'risk',
    'sell', 'warning', 'concern',
})


class SentimentLayer(BaseIntelligenceLayer):
    """Layer 5: 심리 및 포지셔닝 분석.

    Fear & Greed Index, VIX, 뉴스 감성, 기관 리스크 선호도를
    결합하여 시장 심리의 극단성을 평가합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="sentiment")

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """심리/포지셔닝 분석 실행.

        Args:
            data: 분석 데이터 딕셔너리
                - 'fear_greed': Dict with 'value' key (0-100)
                - 'cache': MarketDataCache (VIX, HYG 데이터)
                - 'news': List[Dict] with 'title' key

        Returns:
            LayerResult with sentiment composite score
        """
        cache = data.get('cache')

        metrics: Dict[str, float] = {}
        details: Dict[str, Any] = {}

        # 1) Fear & Greed
        fg_score, fg_details = self._calc_fear_greed(data.get('fear_greed'))
        metrics['fear_greed'] = fg_score
        details['fear_greed'] = fg_details

        # 2) VIX Sentiment
        vs_score, vs_details = self._calc_vix_sentiment(cache)
        metrics['vix_sentiment'] = vs_score
        details['vix_sentiment'] = vs_details

        # 3) News Sentiment
        ns_score, ns_details = self._calc_news_sentiment(data.get('news'))
        metrics['news_sentiment'] = ns_score
        details['news_sentiment'] = ns_details

        # 4) Smart Money (HYG)
        sm_score, sm_details = self._calc_smart_money(cache)
        metrics['smart_money'] = sm_score
        details['smart_money'] = sm_details

        # 합성 점수
        composite = weighted_composite(metrics, SUB_WEIGHTS)
        signal = self.classify_score(composite)

        # 신뢰도: 유효 메트릭 비율
        valid_count = sum(
            1 for v in metrics.values() if not np.isnan(v)
        )
        confidence = valid_count / len(SUB_WEIGHTS)

        interpretation = self._build_interpretation(
            composite, details, metrics
        )

        return LayerResult(
            layer_name=self.name,
            score=round(composite, 1),
            signal=signal,
            confidence=round(confidence, 2),
            metrics={k: round(v, 1) for k, v in metrics.items()},
            interpretation=interpretation,
            details=details,
        )

    # ──────────────────────────────────────────────────────────────
    # Sub-metric implementations
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_fear_greed(
        fg_data: Optional[Dict[str, Any]],
    ) -> Tuple[float, Dict[str, Any]]:
        """Fear & Greed Index 일관된 역발상(contrarian) 점수.

        0-100 값을 완전한 역발상 시그널로 매핑:
        - 공포가 클수록 매수 시그널 (양수 점수)
        - 탐욕이 클수록 매도 시그널 (음수 점수)

        매핑:
        < 20: 극단적 공포 → +80 (강한 역발상 매수)
        20-35: 공포 → +40
        35-50: 약한 공포 → +10
        50-55: 중립 → 0
        55-65: 약한 탐욕 → -10
        65-80: 탐욕 → -40
        > 80: 극단적 탐욕 → -80 (강한 역발상 매도)

        Args:
            fg_data: Fear & Greed 데이터 {'value': int, ...}

        Returns:
            (score, details) 튜플
        """
        if fg_data is None:
            return 0.0, {'value': None, 'zone': 'unknown'}

        value = fg_data.get('value')
        if value is None:
            return 0.0, {'value': None, 'zone': 'unknown'}

        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0, {'value': None, 'zone': 'unknown'}

        # 일관된 역발상 매핑
        if value < 20:
            score = 80.0
            zone = 'extreme_fear'
        elif value < 35:
            score = 40.0
            zone = 'fear'
        elif value < 50:
            score = 10.0
            zone = 'mild_fear'
        elif value <= 55:
            score = 0.0
            zone = 'neutral'
        elif value <= 65:
            score = -10.0
            zone = 'mild_greed'
        elif value <= 80:
            score = -40.0
            zone = 'greed'
        else:
            score = -80.0
            zone = 'extreme_greed'

        return score, {
            'value': round(value, 1),
            'zone': zone,
        }

    def _calc_vix_sentiment(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """VIX 기반 심리 판단.

        VIX < 15: 극단적 안도감 (역발상 약간 부정적, -20)
        VIX 15-20: 정상 (+10)
        VIX 20-30: 공포 고조 (역발상 +30)
        VIX > 30: 패닉 (역발상 +50)
        5일 변화 방향도 고려.

        Args:
            cache: MarketDataCache

        Returns:
            (score, details) 튜플
        """
        vix_close = self._get_close(cache, '^VIX')
        source = '^VIX'

        if vix_close is None or len(vix_close) < 10:
            vix_close = self._get_close(cache, 'VIXY')
            source = 'VIXY'

        if vix_close is None or len(vix_close) < 10:
            return 0.0, {'error': 'VIX 데이터 없음'}

        current_vix = float(vix_close.iloc[-1])

        # VIX 수준 기반 역발상 점수
        if current_vix < 15:
            base_score = -20.0
            zone = 'extreme_complacency'
        elif current_vix <= 20:
            base_score = 10.0
            zone = 'normal'
        elif current_vix <= 30:
            base_score = 30.0
            zone = 'elevated_fear'
        else:
            base_score = 50.0
            zone = 'panic'

        # 5일 변화 방향
        change_5d = pct_change(vix_close, 5)
        direction_bonus = 0.0
        vix_direction = 'stable'

        if change_5d is not None:
            if change_5d > 0.05:  # VIX 5%+ 상승
                direction_bonus = 10.0  # 공포 증가 = 역발상 매수
                vix_direction = 'rising'
            elif change_5d < -0.05:  # VIX 5%+ 하락
                direction_bonus = -10.0  # 안도감 증가
                vix_direction = 'falling'

        score = max(-100.0, min(100.0, base_score + direction_bonus))

        return score, {
            'source': source,
            'current_vix': round(current_vix, 2),
            'zone': zone,
            'change_5d_pct': round((change_5d or 0.0) * 100, 2),
            'direction': vix_direction,
        }

    @staticmethod
    def _calc_news_sentiment(
        news_data: Optional[List[Dict[str, Any]]],
    ) -> Tuple[float, Dict[str, Any]]:
        """뉴스 헤드라인 키워드 기반 감성 분석.

        긍정/부정 키워드 빈도를 분석하여 뉴스 톤을 수치화.
        Net sentiment = (positive - negative) / total * 100

        Args:
            news_data: 뉴스 리스트 [{'title': str, ...}, ...]

        Returns:
            (score, details) 튜플
        """
        if not news_data:
            return 0.0, {
                'method': 'keyword',
                'positive_count': 0,
                'negative_count': 0,
                'total_headlines': 0,
                'tone': 'no_data',
            }

        # FinBERT attempt (opt-in)
        if os.getenv('FINBERT_ENABLED', 'false').lower() == 'true':
            try:
                from trading_bot.sentiment_analyzer import SentimentAnalyzer
                analyzer = SentimentAnalyzer.get_instance()
                return analyzer.analyze_headlines(news_data)
            except ImportError:
                logger.warning("transformers 미설치, 키워드 폴백")
            except Exception as e:
                logger.warning(f"FinBERT 실패, 키워드 폴백: {e}")

        positive_count = 0
        negative_count = 0
        total_headlines = 0

        for item in news_data:
            title = item.get('title', '')
            if not isinstance(title, str) or not title.strip():
                continue

            total_headlines += 1
            words = set(title.lower().split())

            positive_count += len(words & POSITIVE_WORDS)
            negative_count += len(words & NEGATIVE_WORDS)

        total_words = positive_count + negative_count
        if total_words == 0:
            return 0.0, {
                'method': 'keyword',
                'positive_count': 0,
                'negative_count': 0,
                'total_headlines': total_headlines,
                'tone': 'neutral',
            }

        # Net sentiment: -100 ~ +100
        net = (positive_count - negative_count) / total_words * 100

        # 톤 분류
        if net > 30:
            tone = 'positive'
        elif net < -30:
            tone = 'negative'
        else:
            tone = 'mixed'

        score = max(-100.0, min(100.0, net))

        return score, {
            'method': 'keyword',
            'positive_count': positive_count,
            'negative_count': negative_count,
            'total_headlines': total_headlines,
            'net_sentiment': round(net, 1),
            'tone': tone,
        }

    def _calc_smart_money(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """GLD/SPY 비율 모멘텀 기반 기관 리스크 선호도.

        GLD (Gold ETF) / SPY (S&P 500 ETF) 비율이 상승하면
        기관이 안전자산(금) 선호 = risk-off = 주식에 약세.
        비율 하락 = 기관이 주식 선호 = risk-on = 강세.

        스코어는 반전(negate)하여 GLD 강세 = 부정적으로 매핑합니다.

        Args:
            cache: MarketDataCache

        Returns:
            (score, details) 튜플
        """
        gld_close = self._get_close(cache, 'GLD')
        spy_close = self._get_close(cache, 'SPY')

        if (gld_close is None or spy_close is None
                or len(gld_close) < 25 or len(spy_close) < 25):
            return 0.0, {'error': 'GLD/SPY 데이터 없음'}

        # GLD/SPY 비율
        ratio = gld_close / spy_close
        ratio = ratio.dropna()

        if len(ratio) < 25:
            return 0.0, {'error': 'GLD/SPY 비율 데이터 부족'}

        # 5d/20d 모멘텀
        mom = momentum_score(ratio, periods=[5, 20])

        ret_5d = pct_change(ratio, 5)
        ret_20d = pct_change(ratio, 20)

        # GLD outperforming SPY = risk-off = bearish for equities → negate
        negated_mom = -mom

        # 방향 판단 (반전 후 기준)
        if negated_mom > 10:
            direction = 'risk_on'
        elif negated_mom < -10:
            direction = 'risk_off'
        else:
            direction = 'neutral'

        score = max(-100.0, min(100.0, negated_mom))

        return score, {
            'gld_spy_momentum': round(mom, 2),
            'gld_spy_ret_5d_pct': round((ret_5d or 0.0) * 100, 2),
            'gld_spy_ret_20d_pct': round((ret_20d or 0.0) * 100, 2),
            'direction': direction,
        }

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_close(
        cache: Any, symbol: str
    ) -> Optional[pd.Series]:
        """캐시에서 종가 시리즈를 안전하게 추출.

        Args:
            cache: MarketDataCache 인스턴스
            symbol: 티커 심볼

        Returns:
            Close 시리즈 또는 None
        """
        if cache is None:
            return None
        df = cache.get(symbol)
        if df is None or (hasattr(df, 'empty') and df.empty):
            return None
        for col in ['Close', 'close', 'Adj Close']:
            if col in df.columns:
                return df[col].dropna()
        return None

    def _build_interpretation(
        self,
        composite: float,
        details: Dict[str, Any],
        metrics: Dict[str, float],
    ) -> str:
        """한국어 해석 문자열 생성.

        Args:
            composite: 합성 점수
            details: 서브 메트릭 상세
            metrics: 서브 메트릭 점수

        Returns:
            한국어 해석 문자열
        """
        parts = []

        # Fear & Greed
        fg_info = details.get('fear_greed', {})
        fg_value = fg_info.get('value')
        fg_zone = fg_info.get('zone', 'unknown')

        zone_labels = {
            'extreme_fear': '극단적 공포, 역발상 매수 시그널',
            'fear': '공포, 역발상 매수',
            'mild_fear': '약한 공포',
            'neutral': '중립',
            'mild_greed': '약한 탐욕',
            'greed': '탐욕, 역발상 매도',
            'extreme_greed': '극단적 탐욕, 역발상 매도 시그널',
        }

        if fg_value is not None:
            label = zone_labels.get(fg_zone, fg_zone)
            parts.append(f"공포탐욕 {fg_value:.0f} ({label})")

        # VIX
        vs_info = details.get('vix_sentiment', {})
        vix_val = vs_info.get('current_vix')
        vix_dir = vs_info.get('direction', 'stable')

        if vix_val is not None:
            dir_label = {'rising': '상승 중', 'falling': '하락 중', 'stable': '안정'}
            parts.append(f"VIX {vix_val:.1f} {dir_label.get(vix_dir, '')}")

        # News tone
        ns_info = details.get('news_sentiment', {})
        tone = ns_info.get('tone', 'no_data')
        tone_labels = {
            'positive': '뉴스 긍정적',
            'negative': '뉴스 부정적',
            'mixed': '뉴스 혼조',
            'neutral': '뉴스 중립',
            'no_data': '뉴스 데이터 없음',
        }
        parts.append(tone_labels.get(tone, tone))

        # Smart Money
        sm_info = details.get('smart_money', {})
        sm_dir = sm_info.get('direction', 'neutral')
        sm_labels = {
            'risk_on': '기관 리스크 선호 증가',
            'risk_off': '기관 리스크 선호 감소',
            'neutral': '기관 중립',
        }
        parts.append(sm_labels.get(sm_dir, sm_dir))

        return ", ".join(parts)
