"""
Layer 3: Sector/Factor Rotation - 섹터 및 팩터 로테이션 분석.

11개 S&P500 섹터 ETF와 5개 팩터 ETF를 분석하여
현재 시장의 로테이션 상태와 경기 사이클 위치를 판단합니다.

Sub-metrics:
    - sector_momentum (0.25): 섹터 ETF 복합 모멘텀 (5d/10d/20d ROC)
    - factor_momentum (0.20): 팩터 ETF 모멘텀
    - factor_regime (0.20): MTUM/VLUE 비율 기반 팩터 레짐
    - cross_correlation (0.15): 섹터 간 상관관계 (리스크 지표)
    - cycle_position (0.20): 경기 사이클 위치 추정
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

SECTOR_ETFS: List[str] = [
    'XLK', 'XLF', 'XLE', 'XLV', 'XLI',
    'XLP', 'XLU', 'XLY', 'XLC', 'XLB', 'XLRE',
]

SECTOR_NAMES: Dict[str, str] = {
    'XLK': 'Technology',
    'XLF': 'Financials',
    'XLE': 'Energy',
    'XLV': 'Healthcare',
    'XLI': 'Industrials',
    'XLP': 'Consumer Staples',
    'XLU': 'Utilities',
    'XLY': 'Consumer Discretionary',
    'XLC': 'Communication',
    'XLB': 'Materials',
    'XLRE': 'Real Estate',
}

FACTOR_ETFS: List[str] = ['MTUM', 'VLUE', 'QUAL', 'SIZE', 'USMV']

FACTOR_NAMES: Dict[str, str] = {
    'MTUM': 'Momentum',
    'VLUE': 'Value',
    'QUAL': 'Quality',
    'SIZE': 'Size',
    'USMV': 'Min Volatility',
}

# 경기 사이클별 선도 섹터
EARLY_CYCLE: List[str] = ['XLF', 'XLI', 'XLY']
MID_CYCLE: List[str] = ['XLK', 'XLC']
LATE_CYCLE: List[str] = ['XLE', 'XLB']
RECESSION: List[str] = ['XLU', 'XLP', 'XLV', 'XLRE']

CYCLE_GROUPS: Dict[str, Tuple[List[str], str]] = {
    'early_recovery': (EARLY_CYCLE, "초기 회복기"),
    'expansion': (MID_CYCLE, "확장기"),
    'late_expansion': (LATE_CYCLE, "후기 확장기"),
    'contraction': (RECESSION, "수축기"),
}

# 서브 메트릭 가중치
SUB_WEIGHTS: Dict[str, float] = {
    'sector_momentum': 0.25,
    'factor_momentum': 0.20,
    'factor_regime': 0.20,
    'cross_correlation': 0.15,
    'cycle_position': 0.20,
}


class SectorRotationLayer(BaseIntelligenceLayer):
    """Layer 3: 섹터/팩터 로테이션 분석.

    시장의 섹터 간 자금 흐름과 팩터 선호도를 분석하여
    경기 사이클 위치와 시장 건강성을 판단합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="sector_rotation")

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """섹터/팩터 로테이션 분석 실행.

        Args:
            data: {'cache': MarketDataCache} 형태의 데이터 딕셔너리
                  cache에서 섹터/팩터 ETF OHLCV 데이터를 조회합니다.

        Returns:
            LayerResult with score, signal, confidence, metrics, interpretation
        """
        cache = data.get('cache')
        if cache is None:
            return self._empty_result("캐시 데이터 없음")

        # 섹터/팩터 ETF 데이터 수집
        sector_data = self._get_close_data(cache, SECTOR_ETFS)
        factor_data = self._get_close_data(cache, FACTOR_ETFS)

        if len(sector_data) < 3:
            return self._empty_result(
                f"섹터 데이터 부족 ({len(sector_data)}/{len(SECTOR_ETFS)})"
            )

        # 서브 메트릭 계산
        metrics: Dict[str, float] = {}
        details: Dict[str, Any] = {}

        # 1) Sector Momentum
        sm_score, sm_details = self._calc_sector_momentum(sector_data)
        metrics['sector_momentum'] = sm_score
        details['sector_momentum'] = sm_details

        # 2) Factor Momentum
        fm_score, fm_details = self._calc_factor_momentum(factor_data)
        metrics['factor_momentum'] = fm_score
        details['factor_momentum'] = fm_details

        # 3) Factor Regime (MTUM/VLUE)
        fr_score, fr_details = self._calc_factor_regime(factor_data)
        metrics['factor_regime'] = fr_score
        details['factor_regime'] = fr_details

        # 4) Cross Correlation
        cc_score, cc_details = self._calc_cross_correlation(sector_data)
        metrics['cross_correlation'] = cc_score
        details['cross_correlation'] = cc_details

        # 5) Cycle Position
        cp_score, cp_details = self._calc_cycle_position(sector_data)
        metrics['cycle_position'] = cp_score
        details['cycle_position'] = cp_details

        # 합성 점수
        composite = weighted_composite(metrics, SUB_WEIGHTS)
        signal = self.classify_score(composite)

        # 신뢰도: 데이터 가용성 비율
        available = len(sector_data) + len(factor_data)
        total_needed = len(SECTOR_ETFS) + len(FACTOR_ETFS)
        confidence = min(1.0, available / total_needed)

        # 데이터 신선도 계산
        if cache is not None and hasattr(cache, 'avg_freshness_for_symbols'):
            all_syms = list(sector_data.keys()) + list(factor_data.keys())
            avg_freshness = cache.avg_freshness_for_symbols(all_syms)
        else:
            avg_freshness = 1.0

        confidence = min(1.0, confidence * avg_freshness)

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
            data_symbols_used=available,
            data_symbols_expected=total_needed,
        )

    # ──────────────────────────────────────────────────────────────
    # Sub-metric implementations
    # ──────────────────────────────────────────────────────────────

    def _calc_sector_momentum(
        self, sector_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """섹터별 복합 모멘텀 (5d/10d/20d ROC) 계산.

        Returns:
            (score, details) 튜플
        """
        rankings: Dict[str, float] = {}

        for sym, close in sector_data.items():
            mom = momentum_score(close, periods=[5, 10, 20])
            rankings[sym] = mom

        if not rankings:
            return 0.0, {'top3': [], 'bottom3': [], 'rankings': {}}

        # 순위별 정렬
        sorted_sectors = sorted(
            rankings.items(), key=lambda x: x[1], reverse=True
        )

        top3 = [
            {'symbol': s, 'name': SECTOR_NAMES.get(s, s), 'score': round(v, 1)}
            for s, v in sorted_sectors[:3]
        ]
        bottom3 = [
            {'symbol': s, 'name': SECTOR_NAMES.get(s, s), 'score': round(v, 1)}
            for s, v in sorted_sectors[-3:]
        ]

        # 전체 평균 모멘텀을 레이어 점수로 사용
        avg_momentum = float(np.mean(list(rankings.values())))
        score = max(-100.0, min(100.0, avg_momentum))

        return score, {
            'top3': top3,
            'bottom3': bottom3,
            'rankings': {s: round(v, 1) for s, v in sorted_sectors},
        }

    def _calc_factor_momentum(
        self, factor_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """팩터 ETF 모멘텀 (5d/20d) 계산.

        Returns:
            (score, details) 튜플
        """
        rankings: Dict[str, float] = {}

        for sym, close in factor_data.items():
            mom = momentum_score(close, periods=[5, 20])
            rankings[sym] = mom

        if not rankings:
            return 0.0, {'leading_factor': None, 'rankings': {}}

        sorted_factors = sorted(
            rankings.items(), key=lambda x: x[1], reverse=True
        )
        leading = sorted_factors[0]

        avg_momentum = float(np.mean(list(rankings.values())))
        score = max(-100.0, min(100.0, avg_momentum))

        return score, {
            'leading_factor': {
                'symbol': leading[0],
                'name': FACTOR_NAMES.get(leading[0], leading[0]),
                'score': round(leading[1], 1),
            },
            'rankings': {
                s: round(v, 1) for s, v in sorted_factors
            },
        }

    def _calc_factor_regime(
        self, factor_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """MTUM/VLUE 비율 기반 팩터 레짐 판단.

        MTUM/VLUE 비율이 상승 중이면 모멘텀 레짐 (bullish),
        하락 중이면 밸류 레짐 (보통 후기 사이클).

        Returns:
            (score, details) 튜플
        """
        mtum_close = factor_data.get('MTUM')
        vlue_close = factor_data.get('VLUE')

        if mtum_close is None or vlue_close is None:
            return 0.0, {'regime': 'unknown', 'ratio': None, 'trend': None}

        if len(mtum_close) < 21 or len(vlue_close) < 21:
            return 0.0, {'regime': 'unknown', 'ratio': None, 'trend': None}

        # 길이를 맞춰서 positional 정렬 (인덱스가 다를 수 있으므로)
        min_len = min(len(mtum_close), len(vlue_close))
        mtum_vals = mtum_close.iloc[-min_len:].values.astype(float)
        vlue_vals = vlue_close.iloc[-min_len:].values.astype(float)

        # MTUM/VLUE 비율 계산
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio_vals = np.where(vlue_vals != 0, mtum_vals / vlue_vals, np.nan)
        ratio = pd.Series(ratio_vals).dropna()

        if len(ratio) < 21:
            return 0.0, {'regime': 'unknown', 'ratio': None, 'trend': None}

        current_ratio = float(ratio.iloc[-1])
        ratio_20d_ago = float(ratio.iloc[-21])

        if ratio_20d_ago == 0:
            return 0.0, {'regime': 'unknown', 'ratio': current_ratio, 'trend': None}

        ratio_change = (current_ratio - ratio_20d_ago) / ratio_20d_ago * 100

        # 레짐 판단
        if ratio_change > 2:
            regime = 'momentum'
            score = min(100.0, ratio_change * 10)
        elif ratio_change < -2:
            regime = 'value'
            score = max(-100.0, ratio_change * 10)
        else:
            regime = 'balanced'
            score = ratio_change * 5

        score = max(-100.0, min(100.0, score))

        return score, {
            'regime': regime,
            'ratio': round(current_ratio, 3),
            'ratio_change_20d_pct': round(ratio_change, 2),
            'trend': 'up' if ratio_change > 0 else 'down',
        }

    def _calc_cross_correlation(
        self, sector_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """섹터 간 평균 상관관계 계산.

        높은 상관관계 (>0.8) = 리스크오프 허딩 (약세 시그널)
        낮은 상관관계 (<0.4) = 건강한 분산 (강세 시그널)

        Returns:
            (score, details) 튜플
        """
        if len(sector_data) < 3:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        # 20일 수익률 계산 (positional 정렬 - 인덱스가 다를 수 있으므로)
        returns_dict: Dict[str, np.ndarray] = {}
        for sym, close in sector_data.items():
            if len(close) >= 21:
                ret = close.pct_change(periods=1).dropna().tail(20).values
                if len(ret) >= 5:
                    returns_dict[sym] = ret

        if len(returns_dict) < 3:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        # 최소 공통 길이로 정렬
        min_len = min(len(v) for v in returns_dict.values())
        if min_len < 5:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        returns_df = pd.DataFrame(
            {sym: arr[-min_len:] for sym, arr in returns_dict.items()}
        ).dropna()

        if len(returns_df) < 5:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        # 상관관계 행렬 계산
        corr_matrix = returns_df.corr()

        # 대각선 제외한 평균 상관관계
        n = len(corr_matrix)
        if n < 2:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        # 상삼각 행렬만 사용
        mask = np.triu(np.ones((n, n), dtype=bool), k=1)
        pairwise_corrs = corr_matrix.values[mask]
        pairwise_corrs = pairwise_corrs[~np.isnan(pairwise_corrs)]

        if len(pairwise_corrs) == 0:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        avg_corr = float(np.mean(pairwise_corrs))

        # 점수 매핑: 높은 상관관계 = 부정적 (허딩)
        # avg_corr 0.0 → +100 (매우 건강), 1.0 → -100 (위험)
        # 중간점 0.6 → 0
        score = self.normalize_score(avg_corr, 0.0, 1.0, invert=True)

        if avg_corr > 0.8:
            interp = 'high_herding'
        elif avg_corr > 0.6:
            interp = 'moderate_correlation'
        elif avg_corr > 0.4:
            interp = 'normal'
        else:
            interp = 'healthy_diversification'

        return score, {
            'avg_correlation': round(avg_corr, 3),
            'interpretation': interp,
            'num_pairs': len(pairwise_corrs),
        }

    def _calc_cycle_position(
        self, sector_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """경기 사이클 위치 추정.

        어떤 섹터 그룹이 선도하고 있는지로 현재 경기 사이클을 추정합니다.

        Returns:
            (score, details) 튜플
        """
        # 각 사이클 그룹의 평균 모멘텀 계산
        group_scores: Dict[str, float] = {}

        for cycle_name, (symbols, _label) in CYCLE_GROUPS.items():
            group_momentums = []
            for sym in symbols:
                if sym in sector_data:
                    mom = momentum_score(sector_data[sym], periods=[5, 10, 20])
                    group_momentums.append(mom)
            if group_momentums:
                group_scores[cycle_name] = float(np.mean(group_momentums))

        if not group_scores:
            return 0.0, {'cycle': 'unknown', 'group_scores': {}}

        # 가장 높은 모멘텀 그룹이 현재 사이클 위치
        best_cycle = max(group_scores, key=group_scores.get)  # type: ignore

        # 사이클별 점수 매핑
        cycle_score_map = {
            'early_recovery': 60.0,   # 초기 회복 = 강세
            'expansion': 40.0,        # 확장기 = 중간 강세
            'late_expansion': -20.0,  # 후기 확장 = 약간 약세
            'contraction': -60.0,     # 수축기 = 약세
        }

        score = cycle_score_map.get(best_cycle, 0.0)

        return score, {
            'cycle': best_cycle,
            'cycle_label': CYCLE_GROUPS[best_cycle][1],
            'group_scores': {k: round(v, 1) for k, v in group_scores.items()},
            'leading_group': best_cycle,
        }

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _get_close_data(
        self, cache: Any, symbols: List[str]
    ) -> Dict[str, pd.Series]:
        """캐시에서 심볼별 Close 시리즈를 추출.

        Args:
            cache: MarketDataCache 인스턴스
            symbols: 조회할 심볼 리스트

        Returns:
            {symbol: Close Series} 딕셔너리
        """
        result: Dict[str, pd.Series] = {}
        for sym in symbols:
            df = cache.get(sym)
            if df is not None and not df.empty:
                close = self._extract_close(df)
                if close is not None and len(close.dropna()) >= 5:
                    result[sym] = close.dropna()
        return result

    @staticmethod
    def _extract_close(df: pd.DataFrame) -> Optional[pd.Series]:
        """DataFrame에서 Close 컬럼 추출 (대소문자 무관).

        Args:
            df: OHLCV DataFrame

        Returns:
            Close 시리즈 또는 None
        """
        for col in ['Close', 'close', 'Adj Close', 'adj close']:
            if col in df.columns:
                return df[col]
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
            interpretation=f"섹터 로테이션 분석 불가: {reason}",
            details={'error': reason},
        )

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

        # 사이클 위치
        cycle_info = details.get('cycle_position', {})
        cycle_label = cycle_info.get('cycle_label', '미확인')
        parts.append(f"경기 사이클: {cycle_label}")

        # 상위/하위 섹터
        sm_info = details.get('sector_momentum', {})
        top3 = sm_info.get('top3', [])
        bottom3 = sm_info.get('bottom3', [])
        if top3:
            top_names = [t['name'] for t in top3[:2]]
            parts.append(f"선도 섹터: {', '.join(top_names)}")
        if bottom3:
            bot_names = [b['name'] for b in bottom3[:2]]
            parts.append(f"부진 섹터: {', '.join(bot_names)}")

        # 팩터 레짐
        fr_info = details.get('factor_regime', {})
        regime = fr_info.get('regime', 'unknown')
        regime_labels = {
            'momentum': '모멘텀 레짐 (추세 추종 유리)',
            'value': '밸류 레짐 (후기 사이클 가능)',
            'balanced': '균형 레짐',
        }
        if regime in regime_labels:
            parts.append(regime_labels[regime])

        # 상관관계
        cc_info = details.get('cross_correlation', {})
        avg_corr = cc_info.get('avg_correlation')
        if avg_corr is not None:
            if avg_corr > 0.8:
                parts.append("섹터 허딩 심화 (리스크 주의)")
            elif avg_corr < 0.4:
                parts.append("건강한 섹터 분산")

        return ", ".join(parts)
