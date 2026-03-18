"""
Layer 5 (KR): Sentiment - 한국 시장 심리 분석.

한국 시장에 특화된 심리/포지셔닝 지표를 결합하여
시장 참여자의 극단적 심리를 감지하고 역발상(contrarian) 시그널을 제공합니다.

CNN Fear & Greed Index가 없으므로 가중치를 재분배합니다.

Sub-metrics:
    - vkospi_sentiment (0.30): VKOSPI 역발상 스코어링
    - news_sentiment (0.35): 한글 뉴스 키워드 감성 분석
    - smart_money (0.20): GLD/KOSPI 비율 모멘텀
    - usdkrw_sentiment (0.15): 원달러 환율 방향 (원화 강세=리스크온)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import momentum_score, pct_change, weighted_composite

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

KR_SUB_WEIGHTS: Dict[str, float] = {
    'vkospi_sentiment': 0.30,
    'news_sentiment': 0.35,
    'smart_money': 0.20,
    'usdkrw_sentiment': 0.15,
}

KR_BULLISH_KEYWORDS = frozenset({
    '상승', '급등', '호재', '반등', '신고가', '매수', '강세', '호황',
})

KR_BEARISH_KEYWORDS = frozenset({
    '하락', '급락', '악재', '폭락', '매도', '약세', '불황', '위기',
})


class KRSentimentLayer(BaseIntelligenceLayer):
    """Layer 5 (KR): 한국 시장 심리 분석.

    VKOSPI, 한글 뉴스 감성, GLD/KOSPI 비율 모멘텀, 원달러 환율을
    결합하여 한국 시장 심리의 극단성을 평가합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="kr_sentiment")

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """한국 시장 심리 분석 실행.

        Args:
            data: 분석 데이터 딕셔너리
                - 'cache': MarketDataCache (^VKOSPI, GLD, ^KS11, USDKRW=X)
                - 'news': List[Dict] with 'title' key (한글 뉴스)

        Returns:
            LayerResult with KR sentiment composite score
        """
        cache = data.get('cache')

        metrics: Dict[str, float] = {}
        details: Dict[str, Any] = {}

        # 1) VKOSPI Sentiment
        vk_score, vk_details = self._calc_vkospi_sentiment(cache)
        metrics['vkospi_sentiment'] = vk_score
        details['vkospi_sentiment'] = vk_details

        # 2) News Sentiment (한글)
        ns_score, ns_details = self._calc_news_sentiment(data.get('news'))
        metrics['news_sentiment'] = ns_score
        details['news_sentiment'] = ns_details

        # 3) Smart Money (GLD/KOSPI)
        sm_score, sm_details = self._calc_smart_money(cache)
        metrics['smart_money'] = sm_score
        details['smart_money'] = sm_details

        # 4) USDKRW Sentiment
        fx_score, fx_details = self._calc_usdkrw_sentiment(cache)
        metrics['usdkrw_sentiment'] = fx_score
        details['usdkrw_sentiment'] = fx_details

        # 합성 점수
        composite = weighted_composite(metrics, KR_SUB_WEIGHTS)
        signal = self.classify_score(composite)

        # 신뢰도: 유효 메트릭 비율
        valid_count = sum(
            1 for v in metrics.values() if not np.isnan(v)
        )
        confidence = valid_count / len(KR_SUB_WEIGHTS)

        # 데이터 신선도 계산
        cache_syms = ['^VKOSPI', '^KS11', 'GLD', 'USDKRW=X']
        if cache is not None and hasattr(cache, 'avg_freshness_for_symbols'):
            cache_freshness = cache.avg_freshness_for_symbols(cache_syms)
        else:
            cache_freshness = 1.0

        avg_freshness = cache_freshness
        confidence = confidence * avg_freshness

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
            avg_freshness=round(avg_freshness, 2),
            data_symbols_used=valid_count,
            data_symbols_expected=len(KR_SUB_WEIGHTS),
        )

    # ──────────────────────────────────────────────────────────────
    # Sub-metric implementations
    # ──────────────────────────────────────────────────────────────

    def _calc_vkospi_sentiment(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """VKOSPI 기반 심리 판단 (역발상).

        VKOSPI < 15: 극단적 안도감 (역발상 약간 부정적, -20)
        VKOSPI 15-20: 정상 (+10)
        VKOSPI 20-30: 공포 고조 (역발상 +30)
        VKOSPI > 30: 패닉 (역발상 +50)
        5일 변화 방향도 고려.

        Args:
            cache: MarketDataCache

        Returns:
            (score, details) 튜플
        """
        vkospi_close = self._get_close(cache, '^VKOSPI')

        if vkospi_close is None or len(vkospi_close) < 10:
            return 0.0, {'error': 'VKOSPI 데이터 없음'}

        current_vkospi = float(vkospi_close.iloc[-1])

        # VKOSPI 수준 기반 역발상 점수
        if current_vkospi < 15:
            base_score = -20.0
            zone = 'extreme_complacency'
        elif current_vkospi <= 20:
            base_score = 10.0
            zone = 'normal'
        elif current_vkospi <= 30:
            base_score = 30.0
            zone = 'elevated_fear'
        else:
            base_score = 50.0
            zone = 'panic'

        # 5일 변화 방향
        change_5d = pct_change(vkospi_close, 5)
        direction_bonus = 0.0
        vkospi_direction = 'stable'

        if change_5d is not None:
            if change_5d > 0.05:
                direction_bonus = 10.0
                vkospi_direction = 'rising'
            elif change_5d < -0.05:
                direction_bonus = -10.0
                vkospi_direction = 'falling'

        score = max(-100.0, min(100.0, base_score + direction_bonus))

        return score, {
            'current_vkospi': round(current_vkospi, 2),
            'zone': zone,
            'change_5d_pct': round((change_5d or 0.0) * 100, 2),
            'direction': vkospi_direction,
        }

    @staticmethod
    def _calc_news_sentiment(
        news_data: Optional[List[Dict[str, Any]]],
    ) -> Tuple[float, Dict[str, Any]]:
        """한글 뉴스 헤드라인 키워드 기반 감성 분석.

        한글 긍정/부정 키워드 빈도를 분석하여 뉴스 톤을 수치화.
        Net sentiment = (bullish - bearish) / total * 100

        Args:
            news_data: 뉴스 리스트 [{'title': str, ...}, ...]

        Returns:
            (score, details) 튜플
        """
        if not news_data:
            return 0.0, {
                'method': 'kr_keyword',
                'bullish_count': 0,
                'bearish_count': 0,
                'total_headlines': 0,
                'tone': 'no_data',
            }

        bullish_count = 0
        bearish_count = 0
        total_headlines = 0

        for item in news_data:
            title = item.get('title', '')
            if not isinstance(title, str) or not title.strip():
                continue

            total_headlines += 1

            # 한글 키워드는 단어 분리 없이 부분 문자열 매칭
            for keyword in KR_BULLISH_KEYWORDS:
                if keyword in title:
                    bullish_count += 1

            for keyword in KR_BEARISH_KEYWORDS:
                if keyword in title:
                    bearish_count += 1

        total_keywords = bullish_count + bearish_count
        if total_keywords == 0:
            return 0.0, {
                'method': 'kr_keyword',
                'bullish_count': 0,
                'bearish_count': 0,
                'total_headlines': total_headlines,
                'tone': 'neutral',
            }

        # Net sentiment: -100 ~ +100
        net = (bullish_count - bearish_count) / total_keywords * 100

        # 톤 분류
        if net > 30:
            tone = 'positive'
        elif net < -30:
            tone = 'negative'
        else:
            tone = 'mixed'

        score = max(-100.0, min(100.0, net))

        return score, {
            'method': 'kr_keyword',
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'total_headlines': total_headlines,
            'net_sentiment': round(net, 1),
            'tone': tone,
        }

    def _calc_smart_money(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """GLD/KOSPI 비율 모멘텀 기반 기관 리스크 선호도.

        GLD / KOSPI 비율 상승 = 안전자산 선호 = risk-off = 주식 약세.
        비율 하락 = KOSPI 선호 = risk-on = 강세.

        스코어는 반전(negate)하여 GLD 강세 = 부정적으로 매핑합니다.

        Args:
            cache: MarketDataCache

        Returns:
            (score, details) 튜플
        """
        gld_close = self._get_close(cache, 'GLD')
        kospi_close = self._get_close(cache, '^KS11')

        if (gld_close is None or kospi_close is None
                or len(gld_close) < 25 or len(kospi_close) < 25):
            return 0.0, {'error': 'GLD/KOSPI 데이터 없음'}

        # GLD/KOSPI 비율
        ratio = gld_close / kospi_close
        ratio = ratio.dropna()

        if len(ratio) < 25:
            return 0.0, {'error': 'GLD/KOSPI 비율 데이터 부족'}

        # 5d/20d 모멘텀
        mom = momentum_score(ratio, periods=[5, 20])

        ret_5d = pct_change(ratio, 5)
        ret_20d = pct_change(ratio, 20)

        # GLD outperforming KOSPI = risk-off → negate
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
            'gld_kospi_momentum': round(mom, 2),
            'gld_kospi_ret_5d_pct': round((ret_5d or 0.0) * 100, 2),
            'gld_kospi_ret_20d_pct': round((ret_20d or 0.0) * 100, 2),
            'direction': direction,
        }

    def _calc_usdkrw_sentiment(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """원달러 환율 방향 기반 심리 판단.

        원화 강세 (USDKRW 하락) = 리스크온 = 한국 주식 긍정적 (+)
        원화 약세 (USDKRW 상승) = 리스크오프 = 한국 주식 부정적 (-)

        5일/20일 환율 변화율을 기반으로 스코어링합니다.

        Args:
            cache: MarketDataCache

        Returns:
            (score, details) 튜플
        """
        usdkrw_close = self._get_close(cache, 'USDKRW=X')

        if usdkrw_close is None or len(usdkrw_close) < 25:
            return 0.0, {'error': 'USDKRW 데이터 없음'}

        current_rate = float(usdkrw_close.iloc[-1])

        # 환율 모멘텀 (5d/20d)
        mom = momentum_score(usdkrw_close, periods=[5, 20])

        ret_5d = pct_change(usdkrw_close, 5)
        ret_20d = pct_change(usdkrw_close, 20)

        # USDKRW 상승 = 원화 약세 = 한국 주식 부정적 → negate
        negated_mom = -mom

        # 방향 판단
        if negated_mom > 10:
            direction = 'krw_strong'
        elif negated_mom < -10:
            direction = 'krw_weak'
        else:
            direction = 'stable'

        score = max(-100.0, min(100.0, negated_mom))

        return score, {
            'current_rate': round(current_rate, 2),
            'usdkrw_momentum': round(mom, 2),
            'usdkrw_ret_5d_pct': round((ret_5d or 0.0) * 100, 2),
            'usdkrw_ret_20d_pct': round((ret_20d or 0.0) * 100, 2),
            'direction': direction,
        }

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────
    # _get_close() is inherited from BaseIntelligenceLayer

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
        parts: List[str] = []

        # VKOSPI
        vk_info = details.get('vkospi_sentiment', {})
        vk_val = vk_info.get('current_vkospi')
        vk_dir = vk_info.get('direction', 'stable')

        if vk_val is not None:
            dir_label = {'rising': '상승 중', 'falling': '하락 중', 'stable': '안정'}
            parts.append(f"VKOSPI {vk_val:.1f} {dir_label.get(vk_dir, '')}")

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

        # USDKRW
        fx_info = details.get('usdkrw_sentiment', {})
        fx_dir = fx_info.get('direction', 'stable')
        fx_rate = fx_info.get('current_rate')
        fx_labels = {
            'krw_strong': '원화 강세 (리스크온)',
            'krw_weak': '원화 약세 (리스크오프)',
            'stable': '환율 안정',
        }
        fx_text = fx_labels.get(fx_dir, fx_dir)
        if fx_rate is not None:
            fx_text = f"원달러 {fx_rate:.0f} {fx_text}"
        parts.append(fx_text)

        return ", ".join(parts)
