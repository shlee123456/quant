"""
Layer 2 (KR): 한국 시장 구조 - VKOSPI + 시장 폭 + 섹터 브레드스

한국 시장의 내부 구조를 수치화합니다:
- vkospi_level (0.25): VKOSPI 수준 (비선형 스코어링)
- breadth_50ma (0.25): 한국 대형주 25개 중 50MA 위 비율
- breadth_200ma (0.15): 한국 대형주 25개 중 200MA 위 비율
- sector_breadth (0.20): KODEX 섹터 ETF 중 양의 5일 수익률 비율
- mcclellan_proxy (0.15): 한국 섹터 ETF 전진/후퇴 비율 EMA 오실레이터

Note: US Layer 2에 있는 VIX term structure 메트릭은
    한국에서 사용할 수 없으므로 VKOSPI에 가중치 재분배.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .base_layer import BaseIntelligenceLayer, LayerResult
from .scoring import percentile_rank, pct_change, weighted_composite

logger = logging.getLogger(__name__)

# 서브 메트릭 가중치 (VIX term structure 없음 → VKOSPI에 재분배)
KR_STRUCTURE_WEIGHTS: Dict[str, float] = {
    'vkospi_level': 0.25,
    'breadth_50ma': 0.25,
    'breadth_200ma': 0.15,
    'sector_breadth': 0.20,
    'mcclellan_proxy': 0.15,
}

# VKOSPI 심볼
VKOSPI_SYMBOL = '^VKOSPI'

# 한국 대형주 25개 (breadth 계산용)
KR_BREADTH_STOCKS: List[str] = [
    '005930.KS',  # 삼성전자
    '000660.KS',  # SK하이닉스
    '373220.KS',  # LG에너지솔루션
    '207940.KS',  # 삼성바이오로직스
    '005380.KS',  # 현대차
    '006400.KS',  # 삼성SDI
    '051910.KS',  # LG화학
    '035420.KS',  # NAVER
    '000270.KS',  # 기아
    '035720.KS',  # 카카오
    '068270.KS',  # 셀트리온
    '105560.KS',  # KB금융
    '055550.KS',  # 신한지주
    '012330.KS',  # 현대모비스
    '003670.KS',  # 포스코홀딩스
    '066570.KS',  # LG전자
    '096770.KS',  # SK이노베이션
    '028260.KS',  # 삼성물산
    '034730.KS',  # SK
    '032830.KS',  # 삼성생명
    '003550.KS',  # LG
    '010130.KS',  # 고려아연
    '015760.KS',  # 한국전력
    '009150.KS',  # 삼성전기
    '018260.KS',  # 삼성에스디에스
]

# KODEX 섹터 ETF (sector breadth 및 McClellan 프록시용)
KR_SECTOR_ETFS: List[str] = [
    '091160.KS',  # KODEX 반도체
    '091170.KS',  # KODEX 자동차
    '117700.KS',  # KODEX 건설
    '140710.KS',  # KODEX 은행
    '266360.KS',  # KODEX 바이오
    '315270.KS',  # KODEX 2차전지
    '305720.KS',  # KODEX 헬스케어
    '098560.KS',  # KODEX 미디어&엔터
]


class KRMarketStructureLayer(BaseIntelligenceLayer):
    """Layer 2 (KR): 한국 시장 구조 분석.

    VKOSPI 레벨, 시장 폭(breadth), McClellan Oscillator 프록시를
    종합하여 한국 시장 내부 건강도를 평가합니다.

    Args:
        weights: 서브 메트릭 가중치 딕셔너리 (기본: KR_STRUCTURE_WEIGHTS)
        breadth_symbols: breadth 계산에 사용할 종목 리스트
        sector_symbols: 섹터 breadth에 사용할 ETF 리스트
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        breadth_symbols: Optional[List[str]] = None,
        sector_symbols: Optional[List[str]] = None,
    ):
        super().__init__(name="kr_market_structure")
        self.weights = weights or KR_STRUCTURE_WEIGHTS.copy()
        self.breadth_symbols = breadth_symbols or KR_BREADTH_STOCKS
        self.sector_symbols = sector_symbols or KR_SECTOR_ETFS

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """한국 시장 구조 분석 실행.

        Args:
            data: {'cache': MarketDataCache 또는 MockCache} 딕셔너리

        Returns:
            LayerResult with market structure composite score
        """
        cache = data.get('cache')

        sub_scores: Dict[str, float] = {}
        sub_details: Dict[str, Any] = {}

        # 1. VKOSPI Level
        score, detail = self._score_vkospi_level(cache)
        sub_scores['vkospi_level'] = score
        sub_details['vkospi_level'] = detail

        # 2. Breadth 50MA
        score, detail = self._score_breadth_ma(cache, window=50)
        sub_scores['breadth_50ma'] = score
        sub_details['breadth_50ma'] = detail

        # 3. Breadth 200MA
        score, detail = self._score_breadth_ma(cache, window=200)
        sub_scores['breadth_200ma'] = score
        sub_details['breadth_200ma'] = detail

        # 4. Sector Breadth
        score, detail = self._score_sector_breadth(cache)
        sub_scores['sector_breadth'] = score
        sub_details['sector_breadth'] = detail

        # 5. McClellan Proxy
        score, detail = self._score_mcclellan_proxy(cache)
        sub_scores['mcclellan_proxy'] = score
        sub_details['mcclellan_proxy'] = detail

        # 합성 점수 계산
        composite = weighted_composite(sub_scores, self.weights)

        # 신뢰도: 유효한 메트릭 수에 비례
        valid_count = sum(1 for v in sub_scores.values() if not np.isnan(v))
        confidence = valid_count / len(self.weights)

        # 데이터 신선도 계산
        if cache is not None and hasattr(cache, 'avg_freshness_for_symbols'):
            all_syms = [VKOSPI_SYMBOL] + self.breadth_symbols + self.sector_symbols
            avg_freshness = cache.avg_freshness_for_symbols(all_syms)
        else:
            avg_freshness = 1.0

        confidence = confidence * avg_freshness

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
            avg_freshness=round(avg_freshness, 2),
            data_symbols_used=valid_count,
            data_symbols_expected=len(self.weights),
        )

    # ─── Sub-metric scoring ───

    def _score_vkospi_level(self, cache: Any) -> tuple:
        """VKOSPI 수준을 평가.

        - VKOSPI < 15: 과도한 안도감 (약간 부정적)
        - VKOSPI 15-20: 건강한 범위 (긍정적)
        - VKOSPI 20-30: 경계 (약간 부정적)
        - VKOSPI > 30: 공포 (역발상 긍정적)

        Returns:
            (score, details_dict)
        """
        vkospi_series = self._get_close(cache, VKOSPI_SYMBOL)

        if vkospi_series is None or len(vkospi_series) < 10:
            return float('nan'), {'error': 'no VKOSPI data'}

        current_vkospi = float(vkospi_series.iloc[-1])
        pct_rank = percentile_rank(current_vkospi, vkospi_series)

        score = self._vkospi_nonlinear_score(current_vkospi)

        return score, {
            'source': VKOSPI_SYMBOL,
            'current': round(current_vkospi, 2),
            'percentile_rank': round(pct_rank, 1),
        }

    @staticmethod
    def _vkospi_nonlinear_score(vkospi_value: float) -> float:
        """VKOSPI 연속 점수 (구간선형 보간).

        US VIX와 유사한 비선형 커브를 한국 시장에 맞게 조정.
        VKOSPI는 VIX보다 평균적으로 약간 높은 수준에서 거래됨.
        """
        control_points = [
            (10, 30), (15, 50), (18, 30), (22, -10),
            (25, -30), (30, -50), (35, -30), (45, 0),
        ]
        if vkospi_value <= control_points[0][0]:
            return float(control_points[0][1])
        if vkospi_value >= control_points[-1][0]:
            return float(control_points[-1][1])
        for i in range(len(control_points) - 1):
            x0, y0 = control_points[i]
            x1, y1 = control_points[i + 1]
            if x0 <= vkospi_value <= x1:
                t = (vkospi_value - x0) / (x1 - x0)
                return float(y0 + t * (y1 - y0))
        return 0.0

    def _score_breadth_ma(self, cache: Any, window: int = 50) -> tuple:
        """한국 대형주 중 N-MA 위에 있는 비율을 평가.

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

        # 스코어: 50%를 중립으로
        score = float(max(-100.0, min(100.0, (pct_above - 50) * 2)))

        return score, {
            'window': window,
            'pct_above': round(pct_above, 1),
            'above_count': above_count,
            'total_count': total_count,
            'above_symbols': above_list[:5],
            'below_symbols': below_list[:5],
        }

    def _score_sector_breadth(self, cache: Any) -> tuple:
        """KODEX 섹터 ETF 중 양의 5일 수익률을 가진 비율을 평가.

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
            sector_returns[sym] = round(ret * 100, 2)
            if ret > 0:
                positive_count += 1

        if total_count == 0:
            return float('nan'), {'error': 'no sector data'}

        pct_positive = positive_count / total_count * 100

        score = float(max(-100.0, min(100.0, (pct_positive - 50) * 2)))

        return score, {
            'positive_count': positive_count,
            'total_count': total_count,
            'pct_positive': round(pct_positive, 1),
            'sector_returns': sector_returns,
        }

    def _score_mcclellan_proxy(self, cache: Any) -> tuple:
        """McClellan Oscillator 프록시를 계산.

        한국 섹터 ETF의 일일 수익률 부호를 전진/후퇴로 대리하여
        EMA(19) - EMA(39) 오실레이터를 계산합니다.

        Returns:
            (score, details_dict)
        """
        sector_data: Dict[str, pd.Series] = {}
        for sym in self.sector_symbols:
            close = self._get_close(cache, sym)
            if close is not None and len(close) >= 45:
                sector_data[sym] = close.pct_change()

        if len(sector_data) < 3:
            return float('nan'), {'error': 'insufficient sector data for McClellan'}

        # 전진비율 시리즈 생성
        combined = pd.DataFrame(sector_data)
        advancing = (combined > 0).sum(axis=1)
        total = combined.notna().sum(axis=1)
        adv_ratio = advancing / total.replace(0, np.nan)
        adv_ratio = adv_ratio.dropna()

        if len(adv_ratio) < 45:
            return float('nan'), {'error': 'insufficient history for McClellan'}

        # EMA(19) - EMA(39)
        ema19 = adv_ratio.ewm(span=19, min_periods=10, adjust=False).mean()
        ema39 = adv_ratio.ewm(span=39, min_periods=20, adjust=False).mean()
        oscillator = ema19 - ema39

        current_osc = float(oscillator.iloc[-1])

        # 오실레이터 범위: 대략 -0.5 ~ +0.5
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
        vkospi_info = sub_details.get('vkospi_level', {})
        vkospi_val = vkospi_info.get('current', '?')

        breadth_info = sub_details.get('breadth_50ma', {})
        breadth_pct = breadth_info.get('pct_above', '?')

        if composite > 30:
            direction = "한국 시장 구조 양호"
        elif composite > -30:
            direction = "한국 시장 구조 중립"
        else:
            direction = "한국 시장 구조 취약"

        return f"{direction} (VKOSPI {vkospi_val}, {breadth_pct}% > 50MA)"
