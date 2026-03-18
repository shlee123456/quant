"""ML 기반 5-Layer Intelligence 가중치 최적화.

백테스트 데이터에서 Information Coefficient를 최대화하는
최적의 레이어 가중치를 Walk-Forward 방식으로 탐색합니다.

사용법:
    from trading_bot.weight_optimizer import WeightOptimizer
    from trading_bot.intelligence_backtest import IntelligenceBacktester

    bt = IntelligenceBacktester(lookback_years=2)
    result = bt.run()

    optimizer = WeightOptimizer()
    opt_result = optimizer.optimize(result)
    print(opt_result.recommendation)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 레이어 이름 (Layer score column prefix: 'layer_')
LAYER_NAMES = [
    'macro_regime',
    'market_structure',
    'sector_rotation',
    'enhanced_technicals',
    'sentiment',
]

# 가중치 범위 제한
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.40


@dataclass
class OptimizationResult:
    """가중치 최적화 결과."""
    optimal_weights: Dict[str, float] = field(default_factory=dict)
    current_weights: Dict[str, float] = field(default_factory=dict)

    stability_score: float = 0.0    # 0-1, 윈도우 간 가중치 일관성
    oos_ic: float = 0.0             # Out-of-Sample IC
    current_ic: float = 0.0         # 현재 가중치의 IC
    improvement_pct: float = 0.0    # IC 개선율 (%)

    is_improvement: bool = False
    per_window_weights: List[Dict] = field(default_factory=list)
    recommendation: str = ""


class WeightOptimizer:
    """Ridge Regression + Walk-Forward 기반 레이어 가중치 최적화.

    Args:
        n_splits: Walk-Forward 분할 수 (기본 5)
        min_improvement_pct: 최소 개선율 기준 (기본 2.0%)
        min_stability: 최소 안정성 기준 (기본 0.5)
    """

    def __init__(
        self,
        n_splits: int = 5,
        min_improvement_pct: float = 2.0,
        min_stability: float = 0.5,
    ):
        self.n_splits = n_splits
        self.min_improvement_pct = min_improvement_pct
        self.min_stability = min_stability

    def optimize(self, backtest_result: Any) -> OptimizationResult:
        """백테스트 결과에서 최적 레이어 가중치를 탐색.

        Walk-Forward 방식:
        1. daily_scores를 n_splits 구간으로 분할
        2. 각 구간에서 train으로 Ridge -> test에서 IC 측정
        3. 모든 구간에서 안정적인 가중치 -> 최종 가중치

        Args:
            backtest_result: IntelligenceBacktester.run() 결과

        Returns:
            OptimizationResult
        """
        from trading_bot.market_intelligence import LAYER_WEIGHTS

        result = OptimizationResult()
        result.current_weights = dict(LAYER_WEIGHTS)

        df = backtest_result.daily_scores
        if df is None or len(df) < 50:
            result.recommendation = "데이터 부족 (최소 50일 필요). 기존 가중치 유지 권장."
            result.optimal_weights = dict(LAYER_WEIGHTS)
            return result

        # 레이어 점수 컬럼 추출
        layer_cols = [f'layer_{name}' for name in LAYER_NAMES]
        available_cols = [c for c in layer_cols if c in df.columns]

        if len(available_cols) < 3:
            result.recommendation = f"레이어 데이터 부족 ({len(available_cols)}/5). 기존 가중치 유지."
            result.optimal_weights = dict(LAYER_WEIGHTS)
            return result

        # NaN 제거
        clean_df = df[['forward_return'] + available_cols].dropna()
        if len(clean_df) < 50:
            result.recommendation = "유효 데이터 부족. 기존 가중치 유지."
            result.optimal_weights = dict(LAYER_WEIGHTS)
            return result

        # Walk-Forward 최적화
        window_weights = []
        oos_ics = []
        current_ics = []

        split_size = len(clean_df) // self.n_splits

        for i in range(self.n_splits):
            test_start = i * split_size
            test_end = (i + 1) * split_size if i < self.n_splits - 1 else len(clean_df)

            # Anchored: train은 처음부터 test 시작 전까지
            train = clean_df.iloc[:test_start] if test_start > 0 else clean_df.iloc[:split_size]
            test = clean_df.iloc[test_start:test_end]

            if len(train) < 20 or len(test) < 10:
                continue

            # Ridge Regression으로 최적 가중치 탐색
            weights = self._ridge_optimize(train, available_cols)
            if weights is None:
                continue

            window_weights.append(weights)

            # OOS IC 측정 (최적화된 가중치)
            oos_composite = self._apply_weights(test, available_cols, weights)
            oos_ic = self._calc_ic(oos_composite, test['forward_return'])
            oos_ics.append(oos_ic)

            # 현재 가중치 IC 측정
            current_composite = self._apply_weights(test, available_cols, LAYER_WEIGHTS)
            current_ic = self._calc_ic(current_composite, test['forward_return'])
            current_ics.append(current_ic)

        if not window_weights:
            result.recommendation = "최적화 실패 (모든 윈도우 건너뜀). 기존 가중치 유지."
            result.optimal_weights = dict(LAYER_WEIGHTS)
            return result

        # 결과 집계
        avg_weights = self._average_weights(window_weights)
        result.optimal_weights = avg_weights
        result.per_window_weights = window_weights
        result.stability_score = self._calc_stability(window_weights)
        result.oos_ic = float(np.mean(oos_ics)) if oos_ics else 0.0
        result.current_ic = float(np.mean(current_ics)) if current_ics else 0.0

        # 개선율 계산
        if result.current_ic != 0:
            result.improvement_pct = ((result.oos_ic - result.current_ic) / abs(result.current_ic)) * 100
        else:
            result.improvement_pct = 0.0

        result.is_improvement = (
            result.improvement_pct >= self.min_improvement_pct
            and result.stability_score >= self.min_stability
        )

        # 추천 메시지
        result.recommendation = self._build_recommendation(result)

        return result

    def _ridge_optimize(
        self, train_df: pd.DataFrame, layer_cols: List[str]
    ) -> Optional[Dict[str, float]]:
        """Ridge Regression으로 최적 가중치 계산.

        X = 레이어별 점수 (n_samples, n_layers)
        y = forward_return (n_samples,)
        coefficients -> softmax -> 가중치
        """
        X = train_df[layer_cols].values
        y = train_df['forward_return'].values

        # 표준화
        X_mean = X.mean(axis=0)
        X_std = X.std(axis=0)
        X_std[X_std == 0] = 1.0
        X_norm = (X - X_mean) / X_std

        # Ridge Regression (closed-form): w = (X'X + aI)^(-1) X'y
        alpha = 1.0  # 정규화 강도
        n_features = X_norm.shape[1]

        try:
            XtX = X_norm.T @ X_norm
            Xty = X_norm.T @ y
            w = np.linalg.solve(XtX + alpha * np.eye(n_features), Xty)
        except np.linalg.LinAlgError:
            return None

        # abs() 후 정규화 -- Ridge coefficients가 음수일 수 있으므로
        abs_w = np.abs(w)
        if abs_w.sum() == 0:
            return None

        raw_weights = abs_w / abs_w.sum()

        # 범위 제한 (MIN_WEIGHT ~ MAX_WEIGHT) + 반복 재정규화
        clamped = raw_weights.copy()
        for _ in range(10):
            clamped = np.clip(clamped, MIN_WEIGHT, MAX_WEIGHT)
            total = clamped.sum()
            if total == 0:
                return None
            clamped = clamped / total
            # 수렴 확인: 모두 범위 안이면 종료
            if np.all(clamped >= MIN_WEIGHT - 1e-9) and np.all(clamped <= MAX_WEIGHT + 1e-9):
                break

        # Dict으로 변환
        weights = {}
        for col, w_val in zip(layer_cols, clamped):
            layer_name = col.replace('layer_', '')
            weights[layer_name] = round(float(w_val), 3)

        return weights

    def _apply_weights(
        self, df: pd.DataFrame, layer_cols: List[str], weights: Dict[str, float]
    ) -> pd.Series:
        """가중치를 적용하여 composite score 계산."""
        composite = pd.Series(0.0, index=df.index)
        total_weight = 0.0

        for col in layer_cols:
            layer_name = col.replace('layer_', '')
            w = weights.get(layer_name, 0.0)
            if w > 0 and col in df.columns:
                composite += df[col] * w
                total_weight += w

        if total_weight > 0:
            composite /= total_weight

        return composite

    @staticmethod
    def _calc_ic(scores: pd.Series, returns: pd.Series) -> float:
        """Spearman rank correlation (IC) 계산."""
        try:
            valid = pd.DataFrame({'s': scores, 'r': returns}).dropna()
            if len(valid) < 10:
                return 0.0
            rank_s = valid['s'].rank()
            rank_r = valid['r'].rank()
            corr = rank_s.corr(rank_r)
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0

    def _average_weights(self, window_weights: List[Dict]) -> Dict[str, float]:
        """윈도우별 가중치의 평균."""
        if not window_weights:
            return {}

        all_keys = set()
        for w in window_weights:
            all_keys.update(w.keys())

        avg = {}
        for key in all_keys:
            values = [w.get(key, 0.0) for w in window_weights]
            avg[key] = round(float(np.mean(values)), 3)

        # 재정규화
        total = sum(avg.values())
        if total > 0:
            avg = {k: round(v / total, 3) for k, v in avg.items()}

        return avg

    def _calc_stability(self, window_weights: List[Dict]) -> float:
        """윈도우 간 가중치 안정성. 1.0=완전 안정, 0.0=매번 다름."""
        if len(window_weights) < 2:
            return 1.0

        all_keys = set()
        for w in window_weights:
            all_keys.update(w.keys())

        stabilities = []
        for key in all_keys:
            values = [w.get(key, 0.0) for w in window_weights]
            if max(values) - min(values) > 0:
                cv = np.std(values) / (np.mean(values) + 1e-8)
                stabilities.append(max(0.0, 1.0 - cv))
            else:
                stabilities.append(1.0)

        return round(float(np.mean(stabilities)), 2) if stabilities else 0.5

    def _build_recommendation(self, result: OptimizationResult) -> str:
        """사람이 읽을 수 있는 추천 메시지."""
        lines = []

        lines.append(f"현재 IC: {result.current_ic:+.4f}")
        lines.append(f"최적화 IC: {result.oos_ic:+.4f} ({result.improvement_pct:+.1f}%)")
        lines.append(f"안정성: {result.stability_score:.2f}")
        lines.append("")

        lines.append("현재 가중치 → 최적 가중치:")
        for key in sorted(result.current_weights.keys()):
            curr = result.current_weights.get(key, 0)
            opt = result.optimal_weights.get(key, 0)
            delta = opt - curr
            arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")
            lines.append(f"  {key}: {curr:.2f} → {opt:.3f} {arrow}")

        lines.append("")

        if result.is_improvement:
            lines.append("권고: 최적 가중치 적용 권장 (IC 개선 + 안정성 충족)")
        elif result.stability_score < self.min_stability:
            lines.append(f"권고: 가중치 불안정 (stability={result.stability_score:.2f} < {self.min_stability}). 기존 유지.")
        elif result.improvement_pct < self.min_improvement_pct:
            lines.append(f"권고: 개선 미미 ({result.improvement_pct:+.1f}% < {self.min_improvement_pct}%). 기존 유지.")
        else:
            lines.append("권고: 기존 가중치 유지.")

        return "\n".join(lines)


WEIGHTS_PATH = Path('data/optimized_weights.json')


def save_weights(result: OptimizationResult) -> Path:
    """최적화 결과를 JSON으로 저장."""
    payload = {
        'weights': result.optimal_weights,
        'oos_ic': result.oos_ic,
        'current_ic': result.current_ic,
        'improvement_pct': result.improvement_pct,
        'stability_score': result.stability_score,
        'is_improvement': result.is_improvement,
        'recommendation': result.recommendation,
        'saved_at': datetime.now().isoformat(),
    }
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return WEIGHTS_PATH


def load_weights() -> Optional[Dict[str, float]]:
    """저장된 최적화 가중치 로드. 없거나 is_improvement=False면 None."""
    if not WEIGHTS_PATH.exists():
        return None
    try:
        payload = json.loads(WEIGHTS_PATH.read_text())
        if not payload.get('is_improvement', False):
            return None
        return payload.get('weights')
    except (json.JSONDecodeError, KeyError):
        return None
