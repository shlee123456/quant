"""WeightOptimizer 테스트 (Ridge Regression + Walk-Forward 가중치 최적화)"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from trading_bot.weight_optimizer import (
    LAYER_NAMES,
    MAX_WEIGHT,
    MIN_WEIGHT,
    OptimizationResult,
    WeightOptimizer,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_mock_daily_scores(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """백테스트 결과를 모방하는 mock daily_scores DataFrame 생성.

    enhanced_technicals에 강한 시그널, macro_regime에 약한 시그널,
    sentiment에 중간 시그널을 부여하여 가중치 최적화가 의미 있게 동작하도록 함.
    """
    np.random.seed(seed)
    dates = pd.date_range('2024-01-01', periods=n, freq='B')
    forward_returns = np.random.randn(n) * 0.02

    df = pd.DataFrame({
        'date': dates,
        'composite_score': np.random.randn(n) * 20,
        'forward_return': forward_returns,
        'layer_macro_regime': np.random.randn(n) * 15 + forward_returns * 100,
        'layer_market_structure': np.random.randn(n) * 20,
        'layer_sector_rotation': np.random.randn(n) * 18,
        'layer_enhanced_technicals': forward_returns * 500 + np.random.randn(n) * 10,
        'layer_sentiment': np.random.randn(n) * 25 + forward_returns * 200,
    })
    return df


@dataclass
class MockBacktestResult:
    """IntelligenceBacktester.run() 결과를 모방하는 mock 객체."""
    total_days: int = 0
    daily_scores: Optional[pd.DataFrame] = None
    summary: str = ""
    information_coefficient: float = 0.0
    signal_hit_rate: float = 0.0
    layer_hit_rates: Dict[str, float] = field(default_factory=dict)
    layer_ic: Dict[str, float] = field(default_factory=dict)


MOCK_LAYER_WEIGHTS = {
    'macro_regime': 0.20,
    'market_structure': 0.20,
    'sector_rotation': 0.15,
    'enhanced_technicals': 0.25,
    'sentiment': 0.20,
}


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

class TestOptimizationResultDefaults:
    """OptimizationResult 기본값 테스트."""

    def test_optimization_result_defaults(self):
        result = OptimizationResult()
        assert result.optimal_weights == {}
        assert result.current_weights == {}
        assert result.stability_score == 0.0
        assert result.oos_ic == 0.0
        assert result.current_ic == 0.0
        assert result.improvement_pct == 0.0
        assert result.is_improvement is False
        assert result.per_window_weights == []
        assert result.recommendation == ""


class TestRidgeOptimize:
    """_ridge_optimize 메서드 테스트."""

    def test_ridge_optimize_basic(self):
        """유효 데이터로 Ridge 최적화 시 가중치 dict 반환."""
        optimizer = WeightOptimizer()
        df = _make_mock_daily_scores(100)
        layer_cols = [f'layer_{name}' for name in LAYER_NAMES]
        available = [c for c in layer_cols if c in df.columns]

        weights = optimizer._ridge_optimize(df, available)

        assert weights is not None
        assert isinstance(weights, dict)
        assert len(weights) == len(available)

    def test_ridge_optimize_bounds(self):
        """모든 가중치가 [MIN_WEIGHT, MAX_WEIGHT] 범위 내."""
        optimizer = WeightOptimizer()
        df = _make_mock_daily_scores(150)
        layer_cols = [f'layer_{name}' for name in LAYER_NAMES]
        available = [c for c in layer_cols if c in df.columns]

        weights = optimizer._ridge_optimize(df, available)

        assert weights is not None
        for name, w in weights.items():
            assert w >= MIN_WEIGHT - 0.001, f"{name} weight {w} < MIN_WEIGHT"
            assert w <= MAX_WEIGHT + 0.001, f"{name} weight {w} > MAX_WEIGHT"

    def test_ridge_optimize_sum_to_one(self):
        """가중치 합이 약 1.0."""
        optimizer = WeightOptimizer()
        df = _make_mock_daily_scores(150)
        layer_cols = [f'layer_{name}' for name in LAYER_NAMES]
        available = [c for c in layer_cols if c in df.columns]

        weights = optimizer._ridge_optimize(df, available)

        assert weights is not None
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.02, f"가중치 합 {total} != 1.0"


class TestApplyWeights:
    """_apply_weights 메서드 테스트."""

    def test_apply_weights(self):
        """가중치 적용 시 composite = 가중 평균."""
        optimizer = WeightOptimizer()

        df = pd.DataFrame({
            'layer_macro_regime': [10.0, 20.0, 30.0],
            'layer_enhanced_technicals': [40.0, 50.0, 60.0],
        })

        weights = {'macro_regime': 0.4, 'enhanced_technicals': 0.6}
        layer_cols = ['layer_macro_regime', 'layer_enhanced_technicals']

        composite = optimizer._apply_weights(df, layer_cols, weights)

        # composite[0] = (10*0.4 + 40*0.6) / (0.4+0.6) = (4+24)/1.0 = 28
        assert abs(composite.iloc[0] - 28.0) < 0.01
        # composite[1] = (20*0.4 + 50*0.6) / 1.0 = (8+30)/1.0 = 38
        assert abs(composite.iloc[1] - 38.0) < 0.01


class TestCalcIC:
    """_calc_ic 메서드 테스트."""

    def test_calc_ic_perfect(self):
        """완벽 상관 -> IC ~= 1.0."""
        scores = pd.Series(range(100), dtype=float)
        returns = pd.Series(range(100), dtype=float)

        ic = WeightOptimizer._calc_ic(scores, returns)
        assert ic > 0.99, f"Perfect correlation IC={ic}, expected ~1.0"

    def test_calc_ic_random(self):
        """랜덤 데이터 -> IC ~= 0."""
        np.random.seed(123)
        scores = pd.Series(np.random.randn(500))
        returns = pd.Series(np.random.randn(500))

        ic = WeightOptimizer._calc_ic(scores, returns)
        assert abs(ic) < 0.15, f"Random IC={ic}, expected near 0"

    def test_calc_ic_insufficient_data(self):
        """데이터 < 10 -> IC = 0.0."""
        scores = pd.Series([1.0, 2.0, 3.0])
        returns = pd.Series([1.0, 2.0, 3.0])

        ic = WeightOptimizer._calc_ic(scores, returns)
        assert ic == 0.0


class TestAverageWeights:
    """_average_weights 메서드 테스트."""

    def test_average_weights(self):
        """여러 윈도우 가중치 -> 평균 + 재정규화."""
        optimizer = WeightOptimizer()

        window_weights = [
            {'a': 0.3, 'b': 0.7},
            {'a': 0.5, 'b': 0.5},
            {'a': 0.4, 'b': 0.6},
        ]

        avg = optimizer._average_weights(window_weights)

        assert 'a' in avg
        assert 'b' in avg
        total = sum(avg.values())
        assert abs(total - 1.0) < 0.02


class TestStability:
    """_calc_stability 메서드 테스트."""

    def test_stability_identical(self):
        """모든 윈도우 동일 가중치 -> stability = 1.0."""
        optimizer = WeightOptimizer()

        window_weights = [
            {'a': 0.5, 'b': 0.5},
            {'a': 0.5, 'b': 0.5},
            {'a': 0.5, 'b': 0.5},
        ]

        stability = optimizer._calc_stability(window_weights)
        assert stability == 1.0

    def test_stability_different(self):
        """매우 다른 가중치 -> 낮은 stability."""
        optimizer = WeightOptimizer()

        window_weights = [
            {'a': 0.9, 'b': 0.1},
            {'a': 0.1, 'b': 0.9},
            {'a': 0.5, 'b': 0.5},
        ]

        stability = optimizer._calc_stability(window_weights)
        assert stability < 0.8, f"Expected low stability, got {stability}"


class TestOptimizeFlow:
    """optimize() 전체 흐름 테스트."""

    @patch('trading_bot.weight_optimizer.LAYER_WEIGHTS', MOCK_LAYER_WEIGHTS)
    def _import_and_patch(self):
        """LAYER_WEIGHTS를 mock으로 패치하여 import 없이 테스트."""
        pass

    def test_optimize_insufficient_data(self):
        """50일 미만 데이터 -> 기존 가중치 유지."""
        optimizer = WeightOptimizer()

        mock_result = MockBacktestResult()
        mock_result.daily_scores = _make_mock_daily_scores(30)
        mock_result.total_days = 30

        with patch.dict('sys.modules', {
            'trading_bot.market_intelligence': type('module', (), {'LAYER_WEIGHTS': MOCK_LAYER_WEIGHTS})()
        }):
            opt_result = optimizer.optimize(mock_result)

        assert opt_result.optimal_weights == MOCK_LAYER_WEIGHTS
        assert "데이터 부족" in opt_result.recommendation

    def test_optimize_none_daily_scores(self):
        """daily_scores가 None -> 기존 가중치 유지."""
        optimizer = WeightOptimizer()

        mock_result = MockBacktestResult()
        mock_result.daily_scores = None

        with patch.dict('sys.modules', {
            'trading_bot.market_intelligence': type('module', (), {'LAYER_WEIGHTS': MOCK_LAYER_WEIGHTS})()
        }):
            opt_result = optimizer.optimize(mock_result)

        assert opt_result.optimal_weights == MOCK_LAYER_WEIGHTS
        assert "데이터 부족" in opt_result.recommendation

    def test_optimize_with_mock_backtest(self):
        """충분한 데이터로 전체 흐름 테스트."""
        optimizer = WeightOptimizer(n_splits=3)

        df = _make_mock_daily_scores(200)
        mock_result = MockBacktestResult()
        mock_result.daily_scores = df
        mock_result.total_days = 200

        with patch.dict('sys.modules', {
            'trading_bot.market_intelligence': type('module', (), {'LAYER_WEIGHTS': MOCK_LAYER_WEIGHTS})()
        }):
            opt_result = optimizer.optimize(mock_result)

        # 기본 검증
        assert opt_result.optimal_weights is not None
        assert len(opt_result.optimal_weights) > 0
        assert opt_result.recommendation != ""
        assert opt_result.stability_score >= 0.0
        assert opt_result.stability_score <= 1.0

        # 가중치 합 ~= 1.0
        total = sum(opt_result.optimal_weights.values())
        assert abs(total - 1.0) < 0.02, f"가중치 합 = {total}"

        # 가중치 범위 확인
        for name, w in opt_result.optimal_weights.items():
            assert w >= MIN_WEIGHT - 0.001
            assert w <= MAX_WEIGHT + 0.001

    def test_optimize_few_layers(self):
        """레이어 2개만 있을 때 -> 기존 가중치 유지."""
        optimizer = WeightOptimizer()

        n = 100
        df = pd.DataFrame({
            'forward_return': np.random.randn(n) * 0.02,
            'layer_macro_regime': np.random.randn(n) * 15,
            'layer_sentiment': np.random.randn(n) * 25,
        })

        mock_result = MockBacktestResult()
        mock_result.daily_scores = df
        mock_result.total_days = n

        with patch.dict('sys.modules', {
            'trading_bot.market_intelligence': type('module', (), {'LAYER_WEIGHTS': MOCK_LAYER_WEIGHTS})()
        }):
            opt_result = optimizer.optimize(mock_result)

        assert "레이어 데이터 부족" in opt_result.recommendation


class TestBuildRecommendation:
    """_build_recommendation 메서드 테스트."""

    def test_build_recommendation_improvement(self):
        """is_improvement=True -> 적용 권장 메시지."""
        optimizer = WeightOptimizer()

        result = OptimizationResult()
        result.current_weights = MOCK_LAYER_WEIGHTS
        result.optimal_weights = {
            'macro_regime': 0.15,
            'market_structure': 0.15,
            'sector_rotation': 0.10,
            'enhanced_technicals': 0.35,
            'sentiment': 0.25,
        }
        result.stability_score = 0.8
        result.oos_ic = 0.12
        result.current_ic = 0.08
        result.improvement_pct = 50.0
        result.is_improvement = True

        msg = optimizer._build_recommendation(result)

        assert "권고" in msg
        assert "적용 권장" in msg

    def test_build_recommendation_no_improvement_stability(self):
        """stability 부족 -> 불안정 경고."""
        optimizer = WeightOptimizer(min_stability=0.5)

        result = OptimizationResult()
        result.current_weights = MOCK_LAYER_WEIGHTS
        result.optimal_weights = MOCK_LAYER_WEIGHTS
        result.stability_score = 0.3
        result.oos_ic = 0.10
        result.current_ic = 0.08
        result.improvement_pct = 25.0
        result.is_improvement = False

        msg = optimizer._build_recommendation(result)

        assert "불안정" in msg

    def test_build_recommendation_no_improvement_marginal(self):
        """개선 미미 -> 기존 유지 권고."""
        optimizer = WeightOptimizer(min_improvement_pct=2.0)

        result = OptimizationResult()
        result.current_weights = MOCK_LAYER_WEIGHTS
        result.optimal_weights = MOCK_LAYER_WEIGHTS
        result.stability_score = 0.8
        result.oos_ic = 0.081
        result.current_ic = 0.080
        result.improvement_pct = 1.25
        result.is_improvement = False

        msg = optimizer._build_recommendation(result)

        assert "개선 미미" in msg


class TestNoSklearnDependency:
    """sklearn 의존성 없이 동작하는지 확인."""

    def test_no_sklearn_dependency(self):
        """weight_optimizer 모듈이 sklearn 없이 import 가능."""
        import importlib
        import sys

        # sklearn이 이미 로드되어 있다면 이 테스트는 의미가 줄어들지만,
        # weight_optimizer의 소스코드에 sklearn import가 없음을 확인
        import inspect
        from trading_bot import weight_optimizer

        source = inspect.getsource(weight_optimizer)
        assert 'sklearn' not in source, "weight_optimizer에 sklearn import가 있음"
        assert 'scikit' not in source, "weight_optimizer에 scikit-learn 참조가 있음"
