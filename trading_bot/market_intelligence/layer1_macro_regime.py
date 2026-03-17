"""
Layer 1: Macro Regime - 경제 사이클 + 금리 + 유동성

ETF 프록시를 사용하여 거시 경제 환경을 수치화합니다:
- yield_curve (0.25): TLT/SHY 비율로 수익률 곡선 기울기 대리
- credit_spread (0.20): HYG vs LQD 스프레드로 신용 위험 측정
- dollar (0.15): UUP 모멘텀으로 달러 강도 측정
- manufacturing (0.20): XLI 모멘텀 + IWM/SPY 비율로 제조업 경기 측정
- fed_expectations (0.20): SHY 가격 변동으로 금리 기대 측정
"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import momentum_score, pct_change, percentile_rank, weighted_composite

logger = logging.getLogger(__name__)

# 서브 메트릭 가중치
MACRO_WEIGHTS: Dict[str, float] = {
    'yield_curve': 0.25,
    'credit_spread': 0.20,
    'dollar': 0.15,
    'manufacturing': 0.20,
    'fed_expectations': 0.20,
}


class MacroRegimeLayer(BaseIntelligenceLayer):
    """Layer 1: 매크로 레짐 분석.

    ETF 프록시를 사용하여 경제 사이클 국면, 금리 방향, 유동성 상태를
    종합적으로 평가합니다.

    Args:
        weights: 서브 메트릭 가중치 딕셔너리 (기본: MACRO_WEIGHTS)
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        super().__init__(name="macro_regime")
        self.weights = weights or MACRO_WEIGHTS.copy()

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """매크로 레짐 분석 실행.

        Args:
            data: {'cache': MarketDataCache 또는 MockCache} 딕셔너리

        Returns:
            LayerResult with macro regime composite score
        """
        cache = data.get('cache')

        # 각 서브 메트릭 계산
        sub_scores: Dict[str, float] = {}
        sub_details: Dict[str, Any] = {}

        # 1. Yield Curve (TLT/SHY ratio)
        score, detail = self._score_yield_curve(cache)
        sub_scores['yield_curve'] = score
        sub_details['yield_curve'] = detail

        # 2. Credit Spread (HYG vs LQD)
        score, detail = self._score_credit_spread(cache)
        sub_scores['credit_spread'] = score
        sub_details['credit_spread'] = detail

        # 3. Dollar (UUP momentum)
        score, detail = self._score_dollar(cache)
        sub_scores['dollar'] = score
        sub_details['dollar'] = detail

        # 4. Manufacturing (XLI momentum + IWM/SPY)
        score, detail = self._score_manufacturing(cache)
        sub_scores['manufacturing'] = score
        sub_details['manufacturing'] = detail

        # 5. Fed Expectations (SHY price)
        score, detail = self._score_fed_expectations(cache)
        sub_scores['fed_expectations'] = score
        sub_details['fed_expectations'] = detail

        # 합성 점수 계산
        composite = weighted_composite(sub_scores, self.weights)

        # 신뢰도: 유효한 메트릭 수에 비례
        valid_count = sum(1 for v in sub_scores.values() if not np.isnan(v))
        confidence = valid_count / len(self.weights)

        # 사이클 국면 감지
        cycle_phase = self._detect_cycle_phase(sub_scores, sub_details)

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
        )

    # ─── Sub-metric scoring ───

    def _score_yield_curve(self, cache: Any) -> tuple:
        """TLT/SHY 비율로 수익률 곡선 기울기를 평가.

        TLT (장기채 ETF) / SHY (단기채 ETF) 비율이 상승하면
        수익률 곡선이 가파르게(steepening) → 경기 확장 시그널.

        Returns:
            (score, details_dict)
        """
        tlt = self._get_close(cache, 'TLT')
        shy = self._get_close(cache, 'SHY')

        if tlt is None or shy is None or len(tlt) < 25 or len(shy) < 25:
            return float('nan'), {'error': 'insufficient data'}

        # TLT/SHY 비율 시리즈
        ratio = tlt / shy
        ratio = ratio.dropna()

        if len(ratio) < 25:
            return float('nan'), {'error': 'insufficient ratio data'}

        current_ratio = float(ratio.iloc[-1])
        ma20 = float(ratio.rolling(20).mean().iloc[-1])

        # 20일 트렌드: 현재 비율이 20MA 대비 얼마나 위/아래인지
        if ma20 != 0:
            trend_pct = (current_ratio - ma20) / ma20
        else:
            trend_pct = 0.0

        # 5일 변화율
        ret_5d = pct_change(ratio, 5)
        if ret_5d is None:
            ret_5d = 0.0

        # 스코어: 트렌드 + 단기 모멘텀
        # steepening (ratio 상승) = bullish
        # 트렌드 pct: 보통 -3% ~ +3% 범위
        raw_score = (trend_pct * 2000) + (ret_5d * 1000)
        score = float(max(-100.0, min(100.0, raw_score)))

        return score, {
            'current_ratio': round(current_ratio, 4),
            'ma20_ratio': round(ma20, 4),
            'trend_pct': round(trend_pct, 4),
            'ret_5d': round(ret_5d, 4),
        }

    def _score_credit_spread(self, cache: Any) -> tuple:
        """HYG vs LQD 스프레드로 신용 위험을 평가.

        HYG (하이일드채 ETF)가 LQD (투자등급채 ETF) 대비 outperform하면
        리스크 온 → 경기 긍정적.

        Returns:
            (score, details_dict)
        """
        hyg = self._get_close(cache, 'HYG')
        lqd = self._get_close(cache, 'LQD')

        if hyg is None or lqd is None or len(hyg) < 25 or len(lqd) < 25:
            return float('nan'), {'error': 'insufficient data'}

        # 수익률 계산
        hyg_ret_5d = pct_change(hyg, 5)
        lqd_ret_5d = pct_change(lqd, 5)
        hyg_ret_20d = pct_change(hyg, 20)
        lqd_ret_20d = pct_change(lqd, 20)

        if hyg_ret_5d is None or lqd_ret_5d is None:
            return float('nan'), {'error': 'insufficient return data'}

        # 스프레드 수익률 (HYG - LQD)
        spread_5d = hyg_ret_5d - lqd_ret_5d
        spread_20d = (hyg_ret_20d or 0.0) - (lqd_ret_20d or 0.0)

        # HYG outperforming = risk-on (bullish)
        # 5일 스프레드: 보통 -2% ~ +2%
        # 20일에 더 큰 가중치
        raw_score = (spread_5d * 2500) + (spread_20d * 1500)
        score = float(max(-100.0, min(100.0, raw_score)))

        return score, {
            'hyg_ret_5d': round(hyg_ret_5d, 4),
            'lqd_ret_5d': round(lqd_ret_5d, 4),
            'spread_5d': round(spread_5d, 4),
            'hyg_ret_20d': round(hyg_ret_20d or 0.0, 4),
            'lqd_ret_20d': round(lqd_ret_20d or 0.0, 4),
            'spread_20d': round(spread_20d, 4),
        }

    def _score_dollar(self, cache: Any) -> tuple:
        """UUP 모멘텀으로 달러 강도를 평가.

        달러 강세는 주식에 부정적 → 점수 반전 (invert).

        Returns:
            (score, details_dict)
        """
        uup = self._get_close(cache, 'UUP')

        if uup is None or len(uup) < 25:
            return float('nan'), {'error': 'insufficient data'}

        mom = momentum_score(uup, periods=[5, 20])

        # 강달러 = 주식 약세이므로 반전
        score = -mom

        ret_5d = pct_change(uup, 5)
        ret_20d = pct_change(uup, 20)

        return score, {
            'momentum_raw': round(mom, 2),
            'ret_5d': round(ret_5d or 0.0, 4),
            'ret_20d': round(ret_20d or 0.0, 4),
        }

    def _score_manufacturing(self, cache: Any) -> tuple:
        """XLI 모멘텀 + IWM/SPY 비율로 제조업 경기를 평가.

        XLI (산업재 ETF) 상승 + IWM/SPY (소형주/대형주) 비율 상승
        → 제조업/경기 확장 시그널.

        Returns:
            (score, details_dict)
        """
        xli = self._get_close(cache, 'XLI')
        iwm = self._get_close(cache, 'IWM')
        spy = self._get_close(cache, 'SPY')

        details: Dict[str, Any] = {}

        has_xli = False
        has_iwm_spy = False

        # XLI 모멘텀 (50% 가중)
        xli_mom = 0.0
        if xli is not None and len(xli) >= 25:
            xli_mom = momentum_score(xli, periods=[5, 10, 20])
            details['xli_momentum'] = round(xli_mom, 2)
            has_xli = True
        else:
            details['xli_momentum'] = None

        # IWM/SPY 비율 (50% 가중)
        iwm_spy_score = 0.0
        if (iwm is not None and spy is not None
                and len(iwm) >= 25 and len(spy) >= 25):
            ratio = iwm / spy
            ratio = ratio.dropna()
            if len(ratio) >= 25:
                ratio_mom = momentum_score(ratio, periods=[5, 10, 20])
                iwm_spy_score = ratio_mom
                details['iwm_spy_momentum'] = round(ratio_mom, 2)
                details['iwm_spy_current'] = round(float(ratio.iloc[-1]), 4)
                has_iwm_spy = True
            else:
                details['iwm_spy_momentum'] = None
        else:
            details['iwm_spy_momentum'] = None

        # 데이터가 전혀 없으면 NaN 반환
        if not has_xli and not has_iwm_spy:
            return float('nan'), details

        # 가용 데이터에 따라 가중치 조정
        if has_xli and has_iwm_spy:
            score = float(max(-100.0, min(100.0, xli_mom * 0.5 + iwm_spy_score * 0.5)))
        elif has_xli:
            score = float(max(-100.0, min(100.0, xli_mom)))
        else:
            score = float(max(-100.0, min(100.0, iwm_spy_score)))

        return score, details

    def _score_fed_expectations(self, cache: Any) -> tuple:
        """SHY 가격 변동으로 연준 금리 기대를 평가.

        SHY (1-3년 국채 ETF) 가격 상승 = 단기 금리 하락 기대
        = 연준 비둘기파 (dovish) = 주식에 긍정적.

        Returns:
            (score, details_dict)
        """
        shy = self._get_close(cache, 'SHY')

        if shy is None or len(shy) < 25:
            return float('nan'), {'error': 'insufficient data'}

        mom = momentum_score(shy, periods=[5, 10, 20])

        # SHY 상승 = dovish = bullish for equities
        # SHY는 매우 안정적이라 움직임이 작으므로 스코어를 증폭
        score = float(max(-100.0, min(100.0, mom * 3.0)))

        ret_5d = pct_change(shy, 5)
        ret_20d = pct_change(shy, 20)

        return score, {
            'shy_momentum': round(mom, 2),
            'shy_ret_5d': round(ret_5d or 0.0, 4),
            'shy_ret_20d': round(ret_20d or 0.0, 4),
        }

    # ─── Cycle phase detection ───

    def _detect_cycle_phase(
        self,
        scores: Dict[str, float],
        details: Dict[str, Any],
    ) -> str:
        """서브 메트릭으로 경기 사이클 국면을 판단.

        - expansion: 수익률곡선 + 신용 + 제조업 모두 긍정적
        - late_expansion: 일부 지표만 긍정적 (과열 조짐)
        - contraction: 대부분 지표 부정적
        - early_recovery: 수익률곡선 가파름 + 신용 회복 + 제조업 부진

        Returns:
            "expansion", "late_expansion", "contraction", "early_recovery"
        """
        yc = scores.get('yield_curve', 0.0)
        cs = scores.get('credit_spread', 0.0)
        mf = scores.get('manufacturing', 0.0)

        # NaN을 0으로 치환
        if np.isnan(yc):
            yc = 0.0
        if np.isnan(cs):
            cs = 0.0
        if np.isnan(mf):
            mf = 0.0

        bullish_count = sum(1 for s in [yc, cs, mf] if s > 10)
        bearish_count = sum(1 for s in [yc, cs, mf] if s < -10)

        if bullish_count >= 2 and mf > 10:
            return "expansion"
        elif bullish_count >= 2 and mf <= 10:
            return "late_expansion"
        elif bearish_count >= 2:
            return "contraction"
        elif yc > 10 and cs > 0 and mf < 0:
            # 수익률곡선 steepening + 신용 안정 + 제조업 부진 = 초기 회복
            return "early_recovery"
        elif bullish_count == 1:
            return "late_expansion"
        else:
            return "contraction"

    # ─── Korean interpretation ───

    def _interpret(self, composite: float) -> str:
        """합성 점수를 한국어 해석으로 변환."""
        if composite > 50:
            return "매크로 환경 강한 확장 국면"
        elif composite > 20:
            return "매크로 환경 완만한 확장"
        elif composite > -20:
            return "매크로 환경 중립/전환기"
        elif composite > -50:
            return "매크로 환경 둔화 조짐"
        else:
            return "매크로 환경 침체 우려"

    # ─── Helpers ───
    # _get_close() is inherited from BaseIntelligenceLayer
