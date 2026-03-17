"""
Layer 2: Market Structure - VIX + 시장 폭 + 옵션 프록시

시장의 내부 구조를 수치화합니다:
- vix_level (0.20): VIX 수준 및 백분위
- vix_term_structure (0.15): VIX / VIX3M 비율 (콘탱고/백워데이션)
- breadth_50ma (0.25): 대표 25종목 중 50MA 위 비율
- breadth_200ma (0.15): 대표 25종목 중 200MA 위 비율
- sector_breadth (0.15): 11개 섹터 ETF 중 양의 5일 수익률 비율
- mcclellan_proxy (0.10): 섹터 전진/후퇴 비율의 EMA(19)-EMA(39)
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .data_fetcher import LAYER_SYMBOLS
from .scoring import percentile_rank, pct_change, weighted_composite

logger = logging.getLogger(__name__)

# 서브 메트릭 가중치
STRUCTURE_WEIGHTS: Dict[str, float] = {
    'vix_level': 0.20,
    'vix_term_structure': 0.15,
    'breadth_50ma': 0.25,
    'breadth_200ma': 0.15,
    'sector_breadth': 0.15,
    'mcclellan_proxy': 0.10,
}


class MarketStructureLayer(BaseIntelligenceLayer):
    """Layer 2: 시장 구조 분석.

    VIX 레벨/기간구조, 시장 폭(breadth), McClellan Oscillator 프록시를
    종합하여 시장 내부 건강도를 평가합니다.

    Args:
        weights: 서브 메트릭 가중치 딕셔너리 (기본: STRUCTURE_WEIGHTS)
        breadth_symbols: breadth 계산에 사용할 종목 리스트
            (기본: LAYER_SYMBOLS['breadth_stocks'])
        sector_symbols: 섹터 breadth에 사용할 ETF 리스트
            (기본: LAYER_SYMBOLS['sectors'])
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        breadth_symbols: Optional[List[str]] = None,
        sector_symbols: Optional[List[str]] = None,
    ):
        super().__init__(name="market_structure")
        self.weights = weights or STRUCTURE_WEIGHTS.copy()
        self.breadth_symbols = breadth_symbols or LAYER_SYMBOLS['breadth_stocks']
        self.sector_symbols = sector_symbols or LAYER_SYMBOLS['sectors']

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """시장 구조 분석 실행.

        Args:
            data: {'cache': MarketDataCache 또는 MockCache} 딕셔너리

        Returns:
            LayerResult with market structure composite score
        """
        cache = data.get('cache')

        sub_scores: Dict[str, float] = {}
        sub_details: Dict[str, Any] = {}

        # 1. VIX Level
        score, detail = self._score_vix_level(cache)
        sub_scores['vix_level'] = score
        sub_details['vix_level'] = detail

        # 2. VIX Term Structure
        score, detail = self._score_vix_term_structure(cache)
        sub_scores['vix_term_structure'] = score
        sub_details['vix_term_structure'] = detail

        # 3. Breadth 50MA
        score, detail = self._score_breadth_ma(cache, window=50)
        sub_scores['breadth_50ma'] = score
        sub_details['breadth_50ma'] = detail

        # 4. Breadth 200MA
        score, detail = self._score_breadth_ma(cache, window=200)
        sub_scores['breadth_200ma'] = score
        sub_details['breadth_200ma'] = detail

        # 5. Sector Breadth
        score, detail = self._score_sector_breadth(cache)
        sub_scores['sector_breadth'] = score
        sub_details['sector_breadth'] = detail

        # 6. McClellan Proxy
        score, detail = self._score_mcclellan_proxy(cache)
        sub_scores['mcclellan_proxy'] = score
        sub_details['mcclellan_proxy'] = detail

        # 합성 점수 계산
        composite = weighted_composite(sub_scores, self.weights)

        # 신뢰도: 유효한 메트릭 수에 비례
        valid_count = sum(1 for v in sub_scores.values() if not np.isnan(v))
        confidence = valid_count / len(self.weights)

        signal = self.classify_score(composite)
        interpretation = self._interpret(composite, sub_details)

        return LayerResult(
            layer_name=self.name,
            score=composite,
            signal=signal,
            confidence=confidence,
            metrics=sub_scores,
            interpretation=interpretation,
            details={
                'sub_details': sub_details,
                'weights': self.weights,
            },
        )

    # ─── Sub-metric scoring ───

    def _score_vix_level(self, cache: Any) -> tuple:
        """VIX 수준을 평가.

        - VIX < 15: 과도한 안도감 (약간 부정적)
        - VIX 15-20: 건강한 범위 (긍정적)
        - VIX 20-30: 경계 (약간 부정적)
        - VIX > 30: 공포 (역발상 긍정적)

        ^VIX가 없으면 VIXY ETF를 폴백으로 사용합니다.

        Returns:
            (score, details_dict)
        """
        vix_series = self._get_close(cache, '^VIX')
        source = '^VIX'

        # ^VIX 실패 시 VIXY 폴백
        if vix_series is None or len(vix_series) < 10:
            vix_series = self._get_close(cache, 'VIXY')
            source = 'VIXY'
            if vix_series is None or len(vix_series) < 10:
                return float('nan'), {'error': 'no VIX data'}

        current_vix = float(vix_series.iloc[-1])
        pct_rank = percentile_rank(current_vix, vix_series)

        # 비선형 스코어링: 중간 VIX가 가장 긍정적
        if source == '^VIX':
            score = self._vix_nonlinear_score(current_vix)
        else:
            # VIXY는 가격이므로 백분위 기반 간접 스코어링
            # 높은 VIXY = 높은 VIX = 공포
            score = self._vix_percentile_score(pct_rank)

        return score, {
            'source': source,
            'current': round(current_vix, 2),
            'percentile_rank': round(pct_rank, 1),
        }

    @staticmethod
    def _vix_nonlinear_score(vix_value: float) -> float:
        """VIX 연속 점수 (구간선형 보간)."""
        control_points = [
            (10, 30), (15, 50), (18, 30), (22, -10),
            (25, -30), (30, -50), (35, -30), (45, 0),
        ]
        if vix_value <= control_points[0][0]:
            return float(control_points[0][1])
        if vix_value >= control_points[-1][0]:
            return float(control_points[-1][1])
        for i in range(len(control_points) - 1):
            x0, y0 = control_points[i]
            x1, y1 = control_points[i + 1]
            if x0 <= vix_value <= x1:
                t = (vix_value - x0) / (x1 - x0)
                return float(y0 + t * (y1 - y0))
        return 0.0

    @staticmethod
    def _vix_percentile_score(pct_rank: float) -> float:
        """VIX 백분위를 스코어로 변환 (VIXY 폴백용).

        낮은 백분위 = 낮은 VIX = bullish
        """
        # 백분위 0~100 → -100~+100 (반전)
        return float(max(-100.0, min(100.0, (50.0 - pct_rank) * 2)))

    def _score_vix_term_structure(self, cache: Any) -> tuple:
        """VIX 기간 구조를 평가.

        VIX / VIX3M 비율:
        - < 1.0: 콘탱고 (정상, bullish)
        - > 1.0: 백워데이션 (패닉, bearish)

        ^VIX, ^VIX3M이 없으면 VIXY/VIXM ETF를 폴백으로 사용합니다.

        Returns:
            (score, details_dict)
        """
        vix = self._get_close(cache, '^VIX')
        vix3m = self._get_close(cache, '^VIX3M')
        source = '^VIX/^VIX3M'

        if vix is None or vix3m is None or len(vix) < 5 or len(vix3m) < 5:
            # 폴백: VIXY / VIXM
            vix = self._get_close(cache, 'VIXY')
            vix3m = self._get_close(cache, 'VIXM')
            source = 'VIXY/VIXM'

        if vix is None or vix3m is None or len(vix) < 5 or len(vix3m) < 5:
            return float('nan'), {'error': 'no term structure data'}

        ratio = vix / vix3m
        ratio = ratio.dropna()

        if len(ratio) < 5:
            return float('nan'), {'error': 'insufficient ratio data'}

        current_ratio = float(ratio.iloc[-1])

        # 콘탱고 (ratio < 1) = bullish, 백워데이션 (ratio > 1) = bearish
        # ratio 0.8 → +60, ratio 1.0 → 0, ratio 1.2 → -60
        score = float(max(-100.0, min(100.0, (1.0 - current_ratio) * 300)))

        return score, {
            'source': source,
            'current_ratio': round(current_ratio, 4),
            'is_contango': current_ratio < 1.0,
        }

    def _score_breadth_ma(self, cache: Any, window: int = 50) -> tuple:
        """대표 종목 중 N-MA 위에 있는 비율을 평가.

        Args:
            cache: 데이터 캐시
            window: 이동평균 기간 (50 또는 200)

        Returns:
            (score, details_dict)
        """
        above_count = 0
        total_count = 0
        above_list: List[str] = []
        below_list: List[str] = []

        for sym in self.breadth_symbols:
            close = self._get_close(cache, sym)
            if close is None or len(close) < window + 5:
                continue

            ma = close.rolling(window=window).mean()
            current_price = float(close.iloc[-1])
            current_ma = float(ma.iloc[-1])

            if np.isnan(current_ma):
                continue

            total_count += 1
            if current_price > current_ma:
                above_count += 1
                above_list.append(sym)
            else:
                below_list.append(sym)

        if total_count == 0:
            return float('nan'), {'error': 'no breadth data', 'window': window}

        pct_above = above_count / total_count * 100

        # 스코어: 50%를 중립으로, 70%+를 bullish, 30%-를 bearish
        # pct_above 0% → -100, 50% → 0, 100% → +100
        score = float(max(-100.0, min(100.0, (pct_above - 50) * 2)))

        return score, {
            'window': window,
            'pct_above': round(pct_above, 1),
            'above_count': above_count,
            'total_count': total_count,
            'above_symbols': above_list[:5],  # 상위 5개만
            'below_symbols': below_list[:5],
        }

    def _score_sector_breadth(self, cache: Any) -> tuple:
        """11개 섹터 ETF 중 양의 5일 수익률을 가진 비율을 평가.

        > 8개: 광범위한 랠리 (bullish)
        < 3개: 광범위한 하락 (bearish)

        Returns:
            (score, details_dict)
        """
        positive_count = 0
        total_count = 0
        sector_returns: Dict[str, float] = {}

        for sym in self.sector_symbols:
            close = self._get_close(cache, sym)
            if close is None or len(close) < 10:
                continue

            ret = pct_change(close, 5)
            if ret is None:
                continue

            total_count += 1
            sector_returns[sym] = round(ret * 100, 2)  # 퍼센트로 변환
            if ret > 0:
                positive_count += 1

        if total_count == 0:
            return float('nan'), {'error': 'no sector data'}

        pct_positive = positive_count / total_count * 100

        # 스코어: 50%를 중립으로
        score = float(max(-100.0, min(100.0, (pct_positive - 50) * 2)))

        return score, {
            'positive_count': positive_count,
            'total_count': total_count,
            'pct_positive': round(pct_positive, 1),
            'sector_returns': sector_returns,
        }

    def _score_mcclellan_proxy(self, cache: Any) -> tuple:
        """McClellan Oscillator 프록시를 계산.

        실제 McClellan은 NYSE 전진/후퇴 종목 수를 사용하지만,
        여기서는 11개 섹터 ETF의 일일 수익률 부호를 전진/후퇴로 대리합니다.

        매일의 전진비율 (advancing / total)을 구한 후,
        EMA(19) - EMA(39)로 오실레이터를 계산합니다.

        Returns:
            (score, details_dict)
        """
        # 각 섹터의 일일 수익률 부호 시리즈 수집
        sector_data: Dict[str, pd.Series] = {}
        for sym in self.sector_symbols:
            close = self._get_close(cache, sym)
            if close is not None and len(close) >= 45:
                sector_data[sym] = close.pct_change()

        if len(sector_data) < 3:
            return float('nan'), {'error': 'insufficient sector data for McClellan'}

        # 전진비율 시리즈 생성 (each day: advancing sectors / total sectors)
        combined = pd.DataFrame(sector_data)
        advancing = (combined > 0).sum(axis=1)
        total = combined.notna().sum(axis=1)
        # 0 division 방지
        adv_ratio = advancing / total.replace(0, np.nan)
        adv_ratio = adv_ratio.dropna()

        if len(adv_ratio) < 45:
            return float('nan'), {'error': 'insufficient history for McClellan'}

        # EMA(19) - EMA(39) of advancing ratio
        ema19 = adv_ratio.ewm(span=19, min_periods=10, adjust=False).mean()
        ema39 = adv_ratio.ewm(span=39, min_periods=20, adjust=False).mean()
        oscillator = ema19 - ema39

        current_osc = float(oscillator.iloc[-1])

        # 오실레이터 범위: 대략 -0.5 ~ +0.5
        # -0.5 → -100, 0 → 0, +0.5 → +100
        score = float(max(-100.0, min(100.0, current_osc * 200)))

        return score, {
            'current_oscillator': round(current_osc, 4),
            'ema19': round(float(ema19.iloc[-1]), 4),
            'ema39': round(float(ema39.iloc[-1]), 4),
        }

    # ─── Korean interpretation ───

    def _interpret(
        self,
        composite: float,
        sub_details: Dict[str, Any],
    ) -> str:
        """합성 점수와 세부 정보를 한국어 해석으로 변환."""
        # VIX 정보 추출
        vix_info = sub_details.get('vix_level', {})
        vix_val = vix_info.get('current', '?')

        # breadth 정보 추출
        breadth_info = sub_details.get('breadth_50ma', {})
        breadth_pct = breadth_info.get('pct_above', '?')

        # 기본 방향 설명
        if composite > 30:
            direction = "시장 구조 양호"
        elif composite > -30:
            direction = "시장 구조 중립"
        else:
            direction = "시장 구조 취약"

        return f"{direction} (VIX {vix_val}, {breadth_pct}% > 50MA)"

    # ─── Helpers ───
    # _get_close() is inherited from BaseIntelligenceLayer
