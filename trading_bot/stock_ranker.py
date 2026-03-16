"""TOP 3 종목 랭킹 시스템.

5개 가중 팩터를 사용하여 종목을 점수화하고 순위를 매기는 결정론적 랭커.
Intelligence Layer 4의 per_stock composite_score를 주요 팩터로 활용한다.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StockRanker:
    """5개 가중 팩터 기반 종목 랭킹 시스템."""

    DEFAULT_WEIGHTS: Dict[str, float] = {
        'intelligence_composite': 0.40,
        'momentum_multi': 0.20,
        'technical_extremity': 0.15,
        'regime_clarity': 0.10,
        'daily_delta': 0.15,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def rank(
        self,
        stocks_data: Dict[str, Dict[str, Any]],
        intelligence_data: Optional[Dict[str, Any]],
        daily_changes: Optional[Dict[str, Any]],
        previous_top3: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """종목 점수를 계산하고 순위를 매긴다.

        Args:
            stocks_data: {symbol: {'price': {...}, 'indicators': {...}, 'regime': {...}}}
            intelligence_data: Intelligence 분석 결과 (layers.enhanced_technicals.details.per_stock)
            daily_changes: 전일 대비 변화 데이터
            previous_top3: 이전 TOP 3 종목 심볼 리스트

        Returns:
            점수 기준 내림차순 정렬된 종목 딕셔너리 리스트
        """
        ranked: List[Dict[str, Any]] = []

        for symbol, stock_data in stocks_data.items():
            price_data = stock_data.get('price', {})
            indicators = stock_data.get('indicators', {})
            regime_data = stock_data.get('regime', {})
            adx_data = indicators.get('adx', {})

            factor_results: Dict[str, Optional[float]] = {
                'intelligence_composite': self._score_intelligence(
                    symbol, intelligence_data, indicators
                ),
                'momentum_multi': self._score_momentum(price_data),
                'technical_extremity': self._score_extremity(indicators),
                'regime_clarity': self._score_regime(regime_data, adx_data),
                'daily_delta': self._score_daily_delta(symbol, daily_changes),
            }

            effective_weights = self._get_effective_weights(factor_results)

            if not effective_weights:
                logger.warning("종목 %s: 유효한 팩터 없음, 스킵", symbol)
                continue

            total_score = sum(
                factor_results[k] * effective_weights[k]
                for k in effective_weights
            )

            reasons = self._generate_reasons(
                indicators, price_data, regime_data, daily_changes, symbol
            )

            factor_scores = {
                k: round(v, 1)
                for k, v in factor_results.items()
                if v is not None
            }

            direction_info = self._determine_direction(indicators, regime_data)

            ranked.append({
                'symbol': symbol,
                'total_score': round(total_score, 1),
                'factor_scores': factor_scores,
                'reasons': reasons,
                'rank': 0,
                'direction': direction_info['direction'],
                'short_eligible': direction_info['short_eligible'],
                'short_signal_count': direction_info['short_signal_count'],
            })

        ranked.sort(key=lambda x: x['total_score'], reverse=True)
        ranked = self._apply_duplicate_penalty(ranked, previous_top3)

        for i, item in enumerate(ranked):
            item['rank'] = i + 1

        return ranked

    # ──────────────────────────────────────────────────────────────
    # Factor scoring
    # ──────────────────────────────────────────────────────────────

    def _score_intelligence(
        self,
        symbol: str,
        intelligence_data: Optional[Dict[str, Any]],
        indicators: Dict[str, Any],
    ) -> float:
        """팩터 1: Intelligence Composite (40%).

        Layer 4 per_stock composite_score의 절대값을 사용한다.
        데이터가 없으면 기본 지표에서 단순화된 점수를 계산한다.
        """
        per_stock = (intelligence_data or {}).get('layers', {}).get(
            'enhanced_technicals', {}
        ).get('details', {}).get('per_stock', {})
        score = per_stock.get(symbol, {}).get('composite_score')
        if score is not None:
            return abs(score)

        # Fallback: 기본 지표에서 단순 점수 계산
        rsi_val = indicators.get('rsi', {}).get('value', 50) or 50
        rsi_dist = abs(rsi_val - 50) / 50 * 100

        histogram = indicators.get('macd', {}).get('histogram', 0) or 0
        macd_mag = min(100, abs(histogram) * 20)

        pct_b = indicators.get('bollinger', {}).get('pct_b', 0.5) or 0.5
        bb_dist = abs(pct_b - 0.5) / 0.5 * 100

        return (rsi_dist + macd_mag + bb_dist) / 3.0

    @staticmethod
    def _score_momentum(price_data: Dict[str, Any]) -> float:
        """팩터 2: Multi-period Momentum (20%).

        1d/5d/20d 변동률 절대값의 가중 합산. 5% 변동 = 100점.
        """
        c1 = abs(price_data.get('change_1d', 0) or 0)
        c5 = abs(price_data.get('change_5d', 0) or 0)
        c20 = abs(price_data.get('change_20d', 0) or 0)
        raw = c1 * 0.5 + c5 * 0.3 + c20 * 0.2
        return min(100, raw / 5.0 * 100)

    @staticmethod
    def _score_extremity(indicators: Dict[str, Any]) -> float:
        """팩터 3: Technical Extremity (15%).

        RSI, Stochastic %K, Bollinger %B의 중심점 이격도.
        """
        rsi = indicators.get('rsi', {}).get('value', 50) or 50
        rsi_ext = abs(rsi - 50) / 50 * 100

        stoch_k = indicators.get('stochastic', {}).get('k', 50) or 50
        stoch_ext = abs(stoch_k - 50) / 50 * 100

        pct_b = indicators.get('bollinger', {}).get('pct_b', 0.5) or 0.5
        bb_ext = abs(pct_b - 0.5) / 0.5 * 100

        return rsi_ext * 0.4 + stoch_ext * 0.3 + bb_ext * 0.3

    @staticmethod
    def _score_regime(
        regime_data: Dict[str, Any], adx_data: Dict[str, Any]
    ) -> float:
        """팩터 4: Regime Clarity (10%).

        비-SIDEWAYS 상태, 신뢰도, ADX 강도를 종합한다.
        """
        state = regime_data.get('state', 'SIDEWAYS')
        conf = regime_data.get('confidence', 0) or 0
        adx = adx_data.get('value', 0) or 0

        state_score = 50 if state != 'SIDEWAYS' else 0
        conf_score = conf * 30
        adx_score = min(20, adx / 40 * 20)

        return state_score + conf_score + adx_score

    @staticmethod
    def _score_daily_delta(
        symbol: str, daily_changes: Optional[Dict[str, Any]]
    ) -> Optional[float]:
        """팩터 5: Daily Delta (15%).

        전일 대비 가격 변동률과 RSI 변화량. 데이터 없으면 None.
        """
        if not daily_changes or not daily_changes.get('has_previous'):
            return None

        sc = daily_changes.get('stocks', {}).get(symbol, {})
        if not sc:
            return None

        price_chg = abs(sc.get('price_change_pct', 0) or 0)
        rsi_chg = abs(sc.get('rsi_change', 0) or 0)

        return (
            min(100, price_chg / 3.0 * 100) * 0.6
            + min(100, rsi_chg / 10.0 * 100) * 0.4
        )

    # ──────────────────────────────────────────────────────────────
    # Weight redistribution
    # ──────────────────────────────────────────────────────────────

    def _get_effective_weights(
        self, factor_results: Dict[str, Optional[float]]
    ) -> Dict[str, float]:
        """None인 팩터의 가중치를 나머지에 재분배."""
        available = {
            k: v
            for k, v in self.weights.items()
            if factor_results.get(k) is not None
        }
        if not available:
            return {}

        total_available = sum(available.values())
        return {k: v / total_available for k, v in available.items()}

    # ──────────────────────────────────────────────────────────────
    # Direction determination (short eligibility)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _determine_direction(
        indicators: Dict[str, Any], regime_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """숏 시그널 개수를 세어 방향을 결정한다.

        숏 시그널 기준 (5개):
        1. RSI > 75
        2. 레짐이 BEARISH
        3. MACD 데드 크로스 + 최근 발생
        4. Stochastic %K > 80
        5. Bollinger %B > 0.95

        3개 이상이면 'short', 그렇지 않으면 'long'.
        """
        short_signals = 0

        # 1. RSI > 75
        rsi_val = indicators.get('rsi', {}).get('value')
        if rsi_val is not None and rsi_val > 75:
            short_signals += 1

        # 2. BEARISH 레짐
        state = regime_data.get('state', 'SIDEWAYS')
        if state == 'BEARISH':
            short_signals += 1

        # 3. MACD 데드 크로스 (최근)
        macd_data = indicators.get('macd', {})
        histogram = macd_data.get('histogram', 0) or 0
        cross_recent = macd_data.get('cross_recent', False)
        if histogram < 0 and cross_recent:
            short_signals += 1

        # 4. Stochastic %K > 80
        stoch_k = indicators.get('stochastic', {}).get('k')
        if stoch_k is not None and stoch_k > 80:
            short_signals += 1

        # 5. Bollinger %B > 0.95
        pct_b = indicators.get('bollinger', {}).get('pct_b')
        if pct_b is not None and pct_b > 0.95:
            short_signals += 1

        direction = 'short' if short_signals >= 3 else 'long'

        return {
            'direction': direction,
            'short_eligible': short_signals >= 3,
            'short_signal_count': short_signals,
        }

    # ──────────────────────────────────────────────────────────────
    # Duplicate penalty
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_duplicate_penalty(
        ranked: List[Dict[str, Any]],
        previous_top3: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """이전 TOP 3 종목에 30% 감점."""
        if not previous_top3:
            return ranked
        for item in ranked:
            if item['symbol'] in previous_top3:
                penalty = item['total_score'] * 0.30
                item['total_score'] -= penalty
                item['total_score'] = round(item['total_score'], 1)
                item['reasons'].append(f'전일 TOP3 중복 감점 (-{penalty:.0f})')
        ranked.sort(key=lambda x: x['total_score'], reverse=True)
        return ranked

    # ──────────────────────────────────────────────────────────────
    # Reason generation
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_reasons(
        indicators: Dict[str, Any],
        price_data: Dict[str, Any],
        regime_data: Dict[str, Any],
        daily_changes: Optional[Dict[str, Any]],
        symbol: str,
    ) -> List[str]:
        """사람이 읽을 수 있는 이유 문자열 생성."""
        reasons: List[str] = []

        rsi_val = indicators.get('rsi', {}).get('value')
        if rsi_val is not None:
            if rsi_val < 32:
                reasons.append(f'RSI {rsi_val:.1f} 과매도')
            elif rsi_val > 68:
                reasons.append(f'RSI {rsi_val:.1f} 과매수')

        change_1d = price_data.get('change_1d', 0) or 0
        if abs(change_1d) >= 3:
            reasons.append(f'1일 {change_1d:+.1f}% 급변')
        elif abs(change_1d) >= 1:
            reasons.append(f'1일 {change_1d:+.1f}% 변동')

        state = regime_data.get('state')
        if state and state != 'SIDEWAYS':
            reasons.append(f'레짐 {state}')

        macd_data = indicators.get('macd', {})
        if macd_data.get('cross_recent'):
            reasons.append('MACD 교차')

        if daily_changes and daily_changes.get('has_previous'):
            sc = daily_changes.get('stocks', {}).get(symbol, {})
            rsi_change = sc.get('rsi_change', 0) or 0
            if abs(rsi_change) >= 5:
                reasons.append(f'RSI 전일比 {rsi_change:+.1f}')

        return reasons
