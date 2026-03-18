"""
Layer 1 (KR): 한국 매크로 레짐 - 경제 사이클 + 금리 + 유동성

한국 시장에 맞춘 ETF/지수 프록시로 거시 경제 환경을 수치화합니다:
- interest_rate (0.25): BOK 기준금리 + 국채 3Y ETF(114260.KS) 모멘텀
- credit_spread (0.20): 회사채 AA- ETF vs 국채 ETF 스프레드
- exchange_rate (0.15): USDKRW=X 모멘텀 (원화 약세=약세, 반전)
- industrial_production (0.20): BOK 광공업생산지수
- monetary_policy (0.20): 국채 3Y 수익률 모멘텀 (반전)
"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import momentum_score, pct_change, weighted_composite

logger = logging.getLogger(__name__)

# 서브 메트릭 가중치
KR_MACRO_WEIGHTS: Dict[str, float] = {
    'interest_rate': 0.25,
    'credit_spread': 0.20,
    'exchange_rate': 0.15,
    'industrial_production': 0.20,
    'monetary_policy': 0.20,
}

# 한국 시장 심볼
KR_BOND_3Y_ETF = '114260.KS'    # KODEX 국고채3년
KR_CORP_AA_ETF = '136340.KS'    # KBSTAR 중기우량회사채
KR_GOV_BOND_ETF = '114820.KS'   # KODEX 국고채10년
USDKRW_SYMBOL = 'USDKRW=X'     # 원/달러 환율


class KRMacroRegimeLayer(BaseIntelligenceLayer):
    """Layer 1 (KR): 한국 매크로 레짐 분석.

    한국 ETF 프록시와 BOK 데이터를 사용하여 경제 사이클 국면, 금리 방향,
    유동성 상태를 종합적으로 평가합니다.

    Args:
        weights: 서브 메트릭 가중치 딕셔너리 (기본: KR_MACRO_WEIGHTS)
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        super().__init__(name="kr_macro_regime")
        self.weights = weights or KR_MACRO_WEIGHTS.copy()

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """한국 매크로 레짐 분석 실행.

        Args:
            data: {'cache': MarketDataCache 또는 MockCache} 딕셔너리.
                  선택적으로 'bok_fetcher' 키로 BOKDataFetcher 전달 가능.

        Returns:
            LayerResult with macro regime composite score
        """
        cache = data.get('cache')
        bok_fetcher = data.get('bok_fetcher')

        # 각 서브 메트릭 계산
        sub_scores: Dict[str, float] = {}
        sub_details: Dict[str, Any] = {}

        # 1. 금리 방향
        score, detail = self._score_interest_rate(cache, bok_fetcher)
        sub_scores['interest_rate'] = score
        sub_details['interest_rate'] = detail

        # 2. 신용 스프레드
        score, detail = self._score_credit_spread(cache)
        sub_scores['credit_spread'] = score
        sub_details['credit_spread'] = detail

        # 3. 환율
        score, detail = self._score_exchange_rate(cache)
        sub_scores['exchange_rate'] = score
        sub_details['exchange_rate'] = detail

        # 4. 산업생산
        score, detail = self._score_industrial_production(bok_fetcher)
        sub_scores['industrial_production'] = score
        sub_details['industrial_production'] = detail

        # 5. 통화정책 기대
        score, detail = self._score_monetary_policy(cache)
        sub_scores['monetary_policy'] = score
        sub_details['monetary_policy'] = detail

        # 합성 점수 계산
        composite = weighted_composite(sub_scores, self.weights)

        # 신뢰도: 유효한 메트릭 수에 비례
        valid_count = sum(1 for v in sub_scores.values() if not np.isnan(v))
        confidence = valid_count / len(self.weights)

        # 데이터 신선도 계산
        avg_freshness = self._calc_freshness(cache)
        confidence = confidence * avg_freshness

        # 사이클 국면 감지
        cycle_phase = self._detect_cycle_phase(sub_scores)

        # 시그널 분류
        signal = self.classify_score(composite)

        # 한국어 해석
        interpretation = self._interpret(composite)

        return LayerResult(
            layer_name=self.name,
            score=composite,
            signal=signal,
            confidence=confidence,
            metrics=sub_scores,
            interpretation=interpretation,
            details={
                'sub_details': sub_details,
                'cycle_phase': cycle_phase,
                'weights': self.weights,
            },
            avg_freshness=round(avg_freshness, 2),
            data_symbols_used=valid_count,
            data_symbols_expected=len(self.weights),
        )

    # ─── Sub-metric scoring ───

    def _score_interest_rate(self, cache: Any, bok_fetcher: Any) -> tuple:
        """금리 방향을 평가.

        우선순위:
        1. BOK 기준금리 데이터
        2. 국채 3Y ETF(114260.KS) 모멘텀 (폴백)

        금리 하락 기대 (ETF 가격 상승) → bullish.

        Returns:
            (score, details_dict)
        """
        # 최우선: BOK 기준금리
        if bok_fetcher is not None:
            try:
                bok_rate = bok_fetcher.get_base_rate()
                if bok_rate is not None and len(bok_rate) >= 2:
                    return self._score_interest_rate_bok(bok_rate)
            except Exception as e:
                logger.debug(f"BOK 기준금리 조회 실패: {e}")

        # 폴백: 국채 3Y ETF 모멘텀
        bond_3y = self._get_close(cache, KR_BOND_3Y_ETF)

        if bond_3y is None or len(bond_3y) < 25:
            return float('nan'), {'error': 'insufficient data'}

        mom = momentum_score(bond_3y, periods=[5, 10, 20])

        # 채권 가격 상승 = 금리 하락 = bullish
        # 채권 ETF는 변동성이 작으므로 스코어 증폭
        score = float(max(-100.0, min(100.0, mom * 3.0)))

        ret_5d = pct_change(bond_3y, 5)
        ret_20d = pct_change(bond_3y, 20)

        return score, {
            'source': 'KR_BOND_3Y_ETF',
            'momentum': round(mom, 2),
            'ret_5d': round(ret_5d or 0.0, 4),
            'ret_20d': round(ret_20d or 0.0, 4),
        }

    def _score_interest_rate_bok(self, base_rate: pd.Series) -> tuple:
        """BOK 기준금리 기반 금리 방향 점수.

        기준금리 하락 = dovish = bullish
        기준금리 상승 = hawkish = bearish
        """
        current = float(base_rate.iloc[-1])
        prev = float(base_rate.iloc[-2]) if len(base_rate) > 1 else current

        # 금리 하락 = positive
        if current < prev:
            score = 50.0
        elif current > prev:
            score = -50.0
        else:
            score = 0.0

        # 금리 수준 보너스: 높은 금리 = 인하 여지 = 약간 positive
        if current > 4.0:
            score += 10.0
        elif current < 1.5:
            score -= 10.0

        score = float(max(-100.0, min(100.0, score)))

        return score, {
            'source': 'BOK_BASE_RATE',
            'current_rate': round(current, 2),
            'previous_rate': round(prev, 2),
            'direction': 'cutting' if current < prev else (
                'hiking' if current > prev else 'hold'
            ),
        }

    def _score_credit_spread(self, cache: Any) -> tuple:
        """한국 신용 스프레드를 평가.

        회사채 AA- ETF vs 국채 ETF 스프레드.
        회사채 ETF outperforming = risk-on (bullish)

        Returns:
            (score, details_dict)
        """
        corp = self._get_close(cache, KR_CORP_AA_ETF)
        gov = self._get_close(cache, KR_GOV_BOND_ETF)

        if corp is None or gov is None or len(corp) < 25 or len(gov) < 25:
            return float('nan'), {'error': 'insufficient data'}

        # 수익률 계산
        corp_ret_5d = pct_change(corp, 5)
        gov_ret_5d = pct_change(gov, 5)
        corp_ret_20d = pct_change(corp, 20)
        gov_ret_20d = pct_change(gov, 20)

        if corp_ret_5d is None or gov_ret_5d is None:
            return float('nan'), {'error': 'insufficient return data'}

        # 스프레드 수익률 (Corp - Gov)
        spread_5d = corp_ret_5d - gov_ret_5d
        spread_20d = (corp_ret_20d or 0.0) - (gov_ret_20d or 0.0)

        # 회사채 outperforming = risk-on (bullish)
        raw_score = (spread_5d * 2500) + (spread_20d * 1500)
        score = float(max(-100.0, min(100.0, raw_score)))

        return score, {
            'corp_ret_5d': round(corp_ret_5d, 4),
            'gov_ret_5d': round(gov_ret_5d, 4),
            'spread_5d': round(spread_5d, 4),
            'corp_ret_20d': round(corp_ret_20d or 0.0, 4),
            'gov_ret_20d': round(gov_ret_20d or 0.0, 4),
            'spread_20d': round(spread_20d, 4),
        }

    def _score_exchange_rate(self, cache: Any) -> tuple:
        """원/달러 환율 모멘텀을 평가.

        원화 약세 (USDKRW 상승) → 주식 약세이므로 반전.

        Returns:
            (score, details_dict)
        """
        usdkrw = self._get_close(cache, USDKRW_SYMBOL)

        if usdkrw is None or len(usdkrw) < 25:
            return float('nan'), {'error': 'insufficient data'}

        mom = momentum_score(usdkrw, periods=[5, 20])

        # 원화 약세 (USDKRW 상승) = 주식 약세이므로 반전
        score = -mom

        ret_5d = pct_change(usdkrw, 5)
        ret_20d = pct_change(usdkrw, 20)

        return score, {
            'momentum_raw': round(mom, 2),
            'ret_5d': round(ret_5d or 0.0, 4),
            'ret_20d': round(ret_20d or 0.0, 4),
            'current_rate': round(float(usdkrw.iloc[-1]), 2),
        }

    def _score_industrial_production(self, bok_fetcher: Any) -> tuple:
        """산업생산지수를 평가.

        BOK 광공업생산지수. 100 기준 (2020=100).

        Returns:
            (score, details_dict)
        """
        if bok_fetcher is None:
            return float('nan'), {'error': 'no bok_fetcher'}

        try:
            ip_series = bok_fetcher.get_industrial_production()
        except Exception as e:
            logger.debug(f"BOK 광공업생산지수 조회 실패: {e}")
            return float('nan'), {'error': f'bok_fetch_failed: {e}'}

        if ip_series is None or len(ip_series) < 2:
            return float('nan'), {'error': 'insufficient data'}

        current = float(ip_series.iloc[-1])
        prev = float(ip_series.iloc[-2]) if len(ip_series) > 1 else current

        # 100 기준: 100이면 0점, 105이면 +50, 95이면 -50
        score = (current - 100.0) * 10.0

        # 방향성 보너스
        if current > prev:
            score += 10.0
        elif current < prev:
            score -= 10.0

        score = float(max(-100.0, min(100.0, score)))

        return score, {
            'source': 'BOK_IP',
            'current_ip': round(current, 1),
            'previous_ip': round(prev, 1),
            'direction': 'improving' if current > prev else 'declining',
        }

    def _score_monetary_policy(self, cache: Any) -> tuple:
        """통화정책 기대를 평가.

        국채 3Y ETF 가격 모멘텀으로 금리 기대 측정.
        채권 가격 상승 = 금리 인하 기대 = dovish = bullish

        Returns:
            (score, details_dict)
        """
        bond_3y = self._get_close(cache, KR_BOND_3Y_ETF)

        if bond_3y is None or len(bond_3y) < 25:
            return float('nan'), {'error': 'insufficient data'}

        mom = momentum_score(bond_3y, periods=[5, 10, 20])

        # 채권 가격 상승 = dovish = bullish
        # 변동성 작으므로 증폭
        score = float(max(-100.0, min(100.0, mom * 2.5)))

        ret_5d = pct_change(bond_3y, 5)
        ret_20d = pct_change(bond_3y, 20)

        return score, {
            'bond_3y_momentum': round(mom, 2),
            'ret_5d': round(ret_5d or 0.0, 4),
            'ret_20d': round(ret_20d or 0.0, 4),
        }

    # ─── Cycle phase detection ───

    def _detect_cycle_phase(self, scores: Dict[str, float]) -> str:
        """서브 메트릭으로 경기 사이클 국면을 판단.

        Returns:
            "expansion", "late_expansion", "contraction", "early_recovery"
        """
        ir = scores.get('interest_rate', 0.0)
        cs = scores.get('credit_spread', 0.0)
        ip = scores.get('industrial_production', 0.0)

        # NaN을 0으로 치환
        if np.isnan(ir):
            ir = 0.0
        if np.isnan(cs):
            cs = 0.0
        if np.isnan(ip):
            ip = 0.0

        bullish_count = sum(1 for s in [ir, cs, ip] if s > 10)
        bearish_count = sum(1 for s in [ir, cs, ip] if s < -10)

        if bullish_count >= 2 and ip > 10:
            return "expansion"
        elif bullish_count >= 2 and ip <= 10:
            return "late_expansion"
        elif bearish_count >= 2:
            return "contraction"
        elif ir > 10 and cs > 0 and ip < 0:
            return "early_recovery"
        elif bullish_count == 1:
            return "late_expansion"
        else:
            return "contraction"

    # ─── Helpers ───

    def _calc_freshness(self, cache: Any) -> float:
        """데이터 신선도 계산."""
        if cache is None:
            return 1.0

        if hasattr(cache, 'avg_freshness_for_symbols'):
            etf_syms = [KR_BOND_3Y_ETF, KR_CORP_AA_ETF, KR_GOV_BOND_ETF, USDKRW_SYMBOL]
            return cache.avg_freshness_for_symbols(etf_syms)

        return 1.0

    def _interpret(self, composite: float) -> str:
        """합성 점수를 한국어 해석으로 변환."""
        if composite > 50:
            return "한국 매크로 환경 강한 확장 국면"
        elif composite > 20:
            return "한국 매크로 환경 완만한 확장"
        elif composite > -20:
            return "한국 매크로 환경 중립/전환기"
        elif composite > -50:
            return "한국 매크로 환경 둔화 조짐"
        else:
            return "한국 매크로 환경 침체 우려"
