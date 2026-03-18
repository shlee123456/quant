"""
Layer 3 (KR): 한국 섹터 로테이션 - 섹터 모멘텀 + 대/소형주 비율 + 경기 사이클

한국 KODEX 섹터 ETF를 분석하여 현재 시장의 로테이션 상태와
경기 사이클 위치를 판단합니다.

Sub-metrics:
    - sector_momentum (0.25): 섹터 ETF 복합 모멘텀 (5d/10d/20d ROC)
    - large_small_ratio (0.20): KOSPI200/KOSDAQ150 비율 모멘텀
    - cross_correlation (0.15): 섹터 간 상관관계 (리스크 지표)
    - cycle_position (0.20): 경기 사이클 위치 추정
    - sector_dispersion (0.20): 섹터 수익률 분산 (건강한 시장 = 높은 분산)

Note: US Layer 3의 factor_momentum, factor_regime은 한국에
    대응하는 팩터 ETF가 부족하므로 large_small_ratio, sector_dispersion으로 대체.
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

KR_SECTOR_ETFS: Dict[str, str] = {
    '091160.KS': '반도체',      # KODEX 반도체
    '091170.KS': '자동차',      # KODEX 자동차
    '117700.KS': '건설',        # KODEX 건설
    '140710.KS': '은행',        # KODEX 은행
    '266360.KS': '바이오',      # KODEX 바이오
    '315270.KS': '2차전지',     # KODEX 2차전지
    '305720.KS': '헬스케어',    # KODEX 헬스케어
    '098560.KS': '미디어통신',  # KODEX 미디어&엔터
}

KR_CYCLE_GROUPS: Dict[str, Tuple[List[str], str]] = {
    'early_recovery': (['반도체', '자동차'], "초기 회복기"),
    'expansion': (['미디어통신', '헬스케어'], "확장기"),
    'late_expansion': (['건설', '2차전지'], "후기 확장기"),
    'contraction': (['은행', '바이오'], "수축기"),
}

# KOSPI200 / KOSDAQ150 ETF
KOSPI200_ETF = '069500.KS'   # KODEX 200
KOSDAQ150_ETF = '229200.KS'  # KODEX KOSDAQ150

# 서브 메트릭 가중치
KR_SUB_WEIGHTS: Dict[str, float] = {
    'sector_momentum': 0.25,
    'large_small_ratio': 0.20,
    'cross_correlation': 0.15,
    'cycle_position': 0.20,
    'sector_dispersion': 0.20,
}

# 섹터명 → ETF 심볼 역매핑 (사이클 그룹 매칭용)
_SECTOR_TO_SYMBOL: Dict[str, str] = {v: k for k, v in KR_SECTOR_ETFS.items()}


class KRSectorRotationLayer(BaseIntelligenceLayer):
    """Layer 3 (KR): 한국 섹터 로테이션 분석.

    한국 시장의 섹터 간 자금 흐름과 대/소형주 선호도를 분석하여
    경기 사이클 위치와 시장 건강성을 판단합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="kr_sector_rotation")

    def analyze(self, data: Dict[str, Any]) -> LayerResult:
        """한국 섹터/팩터 로테이션 분석 실행.

        Args:
            data: {'cache': MarketDataCache} 형태의 데이터 딕셔너리

        Returns:
            LayerResult with score, signal, confidence, metrics, interpretation
        """
        cache = data.get('cache')
        if cache is None:
            return self._empty_result("캐시 데이터 없음")

        # 섹터 ETF 데이터 수집
        sector_data = self._get_close_data(cache, list(KR_SECTOR_ETFS.keys()))

        if len(sector_data) < 3:
            return self._empty_result(
                f"섹터 데이터 부족 ({len(sector_data)}/{len(KR_SECTOR_ETFS)})"
            )

        # 서브 메트릭 계산
        metrics: Dict[str, float] = {}
        details: Dict[str, Any] = {}

        # 1) Sector Momentum
        sm_score, sm_details = self._calc_sector_momentum(sector_data)
        metrics['sector_momentum'] = sm_score
        details['sector_momentum'] = sm_details

        # 2) Large/Small Ratio (KOSPI200/KOSDAQ150)
        ls_score, ls_details = self._calc_large_small_ratio(cache)
        metrics['large_small_ratio'] = ls_score
        details['large_small_ratio'] = ls_details

        # 3) Cross Correlation
        cc_score, cc_details = self._calc_cross_correlation(sector_data)
        metrics['cross_correlation'] = cc_score
        details['cross_correlation'] = cc_details

        # 4) Cycle Position
        cp_score, cp_details = self._calc_cycle_position(sector_data)
        metrics['cycle_position'] = cp_score
        details['cycle_position'] = cp_details

        # 5) Sector Dispersion
        sd_score, sd_details = self._calc_sector_dispersion(sector_data)
        metrics['sector_dispersion'] = sd_score
        details['sector_dispersion'] = sd_details

        # 합성 점수
        composite = weighted_composite(metrics, KR_SUB_WEIGHTS)
        signal = self.classify_score(composite)

        # 신뢰도: 데이터 가용성 비율
        # 섹터 ETF + KOSPI200 + KOSDAQ150
        total_needed = len(KR_SECTOR_ETFS) + 2
        available = len(sector_data)
        # large_small_ratio가 NaN이 아니면 +2
        if not np.isnan(metrics.get('large_small_ratio', float('nan'))):
            available += 2
        confidence = min(1.0, available / total_needed)

        # 데이터 신선도 계산
        if cache is not None and hasattr(cache, 'avg_freshness_for_symbols'):
            all_syms = list(sector_data.keys()) + [KOSPI200_ETF, KOSDAQ150_ETF]
            avg_freshness = cache.avg_freshness_for_symbols(all_syms)
        else:
            avg_freshness = 1.0

        confidence = min(1.0, confidence * avg_freshness)

        interpretation = self._build_interpretation(composite, details, metrics)

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

        sorted_sectors = sorted(
            rankings.items(), key=lambda x: x[1], reverse=True
        )

        top3 = [
            {'symbol': s, 'name': KR_SECTOR_ETFS.get(s, s), 'score': round(v, 1)}
            for s, v in sorted_sectors[:3]
        ]
        bottom3 = [
            {'symbol': s, 'name': KR_SECTOR_ETFS.get(s, s), 'score': round(v, 1)}
            for s, v in sorted_sectors[-3:]
        ]

        avg_momentum = float(np.mean(list(rankings.values())))
        score = max(-100.0, min(100.0, avg_momentum))

        return score, {
            'top3': top3,
            'bottom3': bottom3,
            'rankings': {s: round(v, 1) for s, v in sorted_sectors},
        }

    def _calc_large_small_ratio(
        self, cache: Any
    ) -> Tuple[float, Dict[str, Any]]:
        """KOSPI200/KOSDAQ150 비율 모멘텀 계산.

        비율 상승 = 대형주 선호 (risk-off 성향)
        비율 하락 = 소형주 선호 (risk-on 성향)

        US Layer 3의 factor_regime 대체.

        Returns:
            (score, details) 튜플
        """
        kospi200 = self._get_close(cache, KOSPI200_ETF)
        kosdaq150 = self._get_close(cache, KOSDAQ150_ETF)

        if kospi200 is None or kosdaq150 is None:
            return 0.0, {'ratio': None, 'trend': None}

        if len(kospi200) < 21 or len(kosdaq150) < 21:
            return 0.0, {'ratio': None, 'trend': None}

        # 길이 맞추기 (positional 정렬)
        min_len = min(len(kospi200), len(kosdaq150))
        k200_vals = kospi200.iloc[-min_len:].values.astype(float)
        kq150_vals = kosdaq150.iloc[-min_len:].values.astype(float)

        # KOSPI200/KOSDAQ150 비율 계산
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio_vals = np.where(kq150_vals != 0, k200_vals / kq150_vals, np.nan)
        ratio = pd.Series(ratio_vals).dropna()

        if len(ratio) < 21:
            return 0.0, {'ratio': None, 'trend': None}

        current_ratio = float(ratio.iloc[-1])
        ratio_20d_ago = float(ratio.iloc[-21])

        if ratio_20d_ago == 0:
            return 0.0, {'ratio': current_ratio, 'trend': None}

        ratio_change = (current_ratio - ratio_20d_ago) / ratio_20d_ago * 100

        # 대형주 선호 증가 (비율 상승) → 약간 방어적 (neutral ~ slightly negative)
        # 소형주 선호 증가 (비율 하락) → risk-on (positive)
        if ratio_change > 2:
            score = max(-100.0, -ratio_change * 8)  # 대형주 편향 = 약간 부정적
        elif ratio_change < -2:
            score = min(100.0, -ratio_change * 8)   # 소형주 편향 = 긍정적
        else:
            score = -ratio_change * 4  # 중립 근처

        score = max(-100.0, min(100.0, score))

        return score, {
            'ratio': round(current_ratio, 3),
            'ratio_change_20d_pct': round(ratio_change, 2),
            'trend': 'large_cap_favored' if ratio_change > 0 else 'small_cap_favored',
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

        # 20일 수익률 계산
        returns_dict: Dict[str, np.ndarray] = {}
        for sym, close in sector_data.items():
            if len(close) >= 21:
                ret = close.pct_change(periods=1).dropna().tail(20).values
                if len(ret) >= 5:
                    returns_dict[sym] = ret

        if len(returns_dict) < 3:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        min_len = min(len(v) for v in returns_dict.values())
        if min_len < 5:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        returns_df = pd.DataFrame(
            {sym: arr[-min_len:] for sym, arr in returns_dict.items()}
        ).dropna()

        if len(returns_df) < 5:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        corr_matrix = returns_df.corr()

        n = len(corr_matrix)
        if n < 2:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        mask = np.triu(np.ones((n, n), dtype=bool), k=1)
        pairwise_corrs = corr_matrix.values[mask]
        pairwise_corrs = pairwise_corrs[~np.isnan(pairwise_corrs)]

        if len(pairwise_corrs) == 0:
            return 0.0, {'avg_correlation': None, 'interpretation': 'data_insufficient'}

        avg_corr = float(np.mean(pairwise_corrs))

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
        group_scores: Dict[str, float] = {}

        for cycle_name, (sector_names, _label) in KR_CYCLE_GROUPS.items():
            group_momentums = []
            for name in sector_names:
                sym = _SECTOR_TO_SYMBOL.get(name)
                if sym and sym in sector_data:
                    mom = momentum_score(sector_data[sym], periods=[5, 10, 20])
                    group_momentums.append(mom)
            if group_momentums:
                group_scores[cycle_name] = float(np.mean(group_momentums))

        if not group_scores:
            return 0.0, {'cycle': 'unknown', 'group_scores': {}}

        best_cycle = max(group_scores, key=group_scores.get)  # type: ignore

        cycle_score_map = {
            'early_recovery': 60.0,
            'expansion': 40.0,
            'late_expansion': -20.0,
            'contraction': -60.0,
        }

        score = cycle_score_map.get(best_cycle, 0.0)

        return score, {
            'cycle': best_cycle,
            'cycle_label': KR_CYCLE_GROUPS[best_cycle][1],
            'group_scores': {k: round(v, 1) for k, v in group_scores.items()},
            'leading_group': best_cycle,
        }

    def _calc_sector_dispersion(
        self, sector_data: Dict[str, pd.Series]
    ) -> Tuple[float, Dict[str, Any]]:
        """섹터 수익률 분산 계산.

        높은 분산 = 분명한 섹터 선택 (bullish, 트렌드 형성)
        낮은 분산 = 무차별 하락/상승 (중립/bearish)

        US Layer 3의 factor_momentum 대체.

        Returns:
            (score, details) 튜플
        """
        sector_returns: List[float] = []

        for sym, close in sector_data.items():
            ret = pct_change(close, 20)
            if ret is not None:
                sector_returns.append(ret)

        if len(sector_returns) < 3:
            return 0.0, {'dispersion': None, 'interpretation': 'data_insufficient'}

        dispersion = float(np.std(sector_returns))
        avg_return = float(np.mean(sector_returns))

        # 분산이 크고 평균 수익률이 양수 → bullish
        # 분산이 크고 평균 수익률이 음수 → bearish
        # 분산이 작으면 → neutral
        if dispersion > 0.05:
            if avg_return > 0:
                score = min(100.0, dispersion * 1000 + avg_return * 200)
            else:
                score = max(-100.0, avg_return * 300)
        else:
            score = avg_return * 200

        score = max(-100.0, min(100.0, score))

        if dispersion > 0.08:
            interp = 'high_dispersion'
        elif dispersion > 0.04:
            interp = 'moderate_dispersion'
        else:
            interp = 'low_dispersion'

        return score, {
            'dispersion': round(dispersion, 4),
            'avg_return_20d': round(avg_return, 4),
            'interpretation': interp,
            'num_sectors': len(sector_returns),
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
            close = self._get_close(cache, sym)
            if close is not None and len(close) >= 5:
                result[sym] = close
        return result

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
            interpretation=f"한국 섹터 로테이션 분석 불가: {reason}",
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

        # 대/소형주 비율
        ls_info = details.get('large_small_ratio', {})
        ls_trend = ls_info.get('trend')
        if ls_trend == 'large_cap_favored':
            parts.append("대형주 선호 (방어적)")
        elif ls_trend == 'small_cap_favored':
            parts.append("소형주 선호 (공격적)")

        # 상관관계
        cc_info = details.get('cross_correlation', {})
        avg_corr = cc_info.get('avg_correlation')
        if avg_corr is not None:
            if avg_corr > 0.8:
                parts.append("섹터 허딩 심화 (리스크 주의)")
            elif avg_corr < 0.4:
                parts.append("건강한 섹터 분산")

        return ", ".join(parts)
