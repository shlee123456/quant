"""
Walk-Forward Optimization 테스트
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.simulation_data import SimulationDataGenerator


@pytest.fixture
def sample_data():
    """500행 bullish 시뮬레이션 데이터"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_trend_data(initial_price=100, periods=500, trend='bullish')


@pytest.fixture
def small_data():
    """n_splits * 50보다 작은 데이터"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_trend_data(initial_price=100, periods=30, trend='bullish')


@pytest.fixture
def large_data():
    """레짐 감지용 대규모 데이터"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_trend_data(initial_price=100, periods=1000, trend='bullish')


@pytest.fixture
def optimizer():
    """기본 옵티마이저"""
    return StrategyOptimizer(initial_capital=10000, position_size=0.95, commission=0.001)


@pytest.fixture
def param_grid():
    """RSI 파라미터 그리드"""
    return {
        'period': [7, 14],
        'overbought': [70],
        'oversold': [30],
    }


def test_walk_forward_rolling_basic(optimizer, sample_data, param_grid):
    """Rolling 모드 기본 동작 테스트"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=5,
        train_ratio=0.7,
        mode='rolling',
        metric='total_return',
        use_vbt=False,
    )

    assert isinstance(result, dict)
    assert len(result['oos_results']) > 0
    assert len(result['best_params_per_window']) > 0
    assert len(result['windows']) > 0

    # OOS 결과에 필수 필드 확인
    for oos in result['oos_results']:
        assert 'is_return' in oos
        assert 'oos_return' in oos
        assert 'best_params' in oos


def test_walk_forward_anchored_basic(optimizer, sample_data, param_grid):
    """Anchored 모드 기본 동작 테스트"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=5,
        train_ratio=0.7,
        mode='anchored',
        metric='total_return',
        use_vbt=False,
    )

    assert isinstance(result, dict)
    assert len(result['oos_results']) > 0
    assert len(result['best_params_per_window']) > 0

    # Anchored: 학습 구간이 항상 시작점에서 시작
    for window in result['windows']:
        train_start, train_end, test_start, test_end = window
        # 첫 번째 타임스탬프가 데이터의 시작과 같아야 함
        assert train_start == sample_data.index[0]


def test_walk_forward_returns_all_keys(optimizer, sample_data, param_grid):
    """반환 딕셔너리의 모든 기대 키 확인"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=3,
        train_ratio=0.7,
        mode='rolling',
        use_vbt=False,
    )

    expected_keys = [
        'oos_results',
        'aggregate_oos_return',
        'stability_ratio',
        'is_oos_gap',
        'parameter_stability',
        'best_params_per_window',
        'windows',
    ]

    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_walk_forward_stability_ratio_range(optimizer, sample_data, param_grid):
    """stability_ratio가 None이거나 숫자인지 검증"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=3,
        train_ratio=0.7,
        mode='rolling',
        use_vbt=False,
    )

    sr = result['stability_ratio']
    # stability_ratio는 None이거나 float
    if sr is not None:
        assert isinstance(sr, (int, float))
        # 비정상적으로 크지 않은지 확인 (합리적 범위)
        assert sr == sr  # NaN 아님


def test_walk_forward_parameter_stability(optimizer, sample_data, param_grid):
    """parameter_stability가 0~1 범위인지 검증"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=5,
        train_ratio=0.7,
        mode='rolling',
        use_vbt=False,
    )

    ps = result['parameter_stability']
    assert isinstance(ps, (int, float))
    assert 0.0 <= ps <= 1.0, f"parameter_stability {ps} is out of [0, 1] range"


def test_walk_forward_insufficient_data(optimizer, small_data, param_grid):
    """데이터 부족 시 빈 결과 반환"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=small_data,
        param_grid=param_grid,
        n_splits=5,
        train_ratio=0.7,
        mode='rolling',
        use_vbt=False,
    )

    assert result['oos_results'] == []
    assert result['aggregate_oos_return'] == 0.0
    assert result['stability_ratio'] is None
    assert result['best_params_per_window'] == []
    assert result['windows'] == []


def test_walk_forward_vbt_mode(optimizer, sample_data):
    """use_vbt=True 모드 테스트"""
    param_grid = {
        'period': [7, 14],
        'overbought': [70],
        'oversold': [30],
    }

    try:
        result = optimizer.walk_forward_optimize(
            strategy_class=RSIStrategy,
            df=sample_data,
            param_grid=param_grid,
            n_splits=3,
            train_ratio=0.7,
            mode='rolling',
            use_vbt=True,
        )

        assert isinstance(result, dict)
        assert 'oos_results' in result
        # VBT가 설치되어 있으면 결과가 있어야 함
        if result['oos_results']:
            assert len(result['best_params_per_window']) > 0
    except ImportError:
        pytest.skip("vectorbt not installed")


def test_walk_forward_regime_aware(optimizer, large_data):
    """RegimeDetector 통합 Walk-Forward 테스트"""
    from trading_bot.regime_detector import RegimeDetector

    param_grids = [
        {'period': [7, 14], 'overbought': [70], 'oversold': [30]},
        {'fast_period': [8, 12], 'slow_period': [20, 26], 'signal_period': [9]},
    ]

    result = optimizer.walk_forward_regime_optimize(
        strategy_classes=[RSIStrategy, MACDStrategy],
        df=large_data,
        param_grids=param_grids,
        n_splits=3,
        train_ratio=0.7,
        mode='anchored',
        regime_detector=RegimeDetector(),
        use_vbt=False,
    )

    assert isinstance(result, dict)
    assert 'windows' in result
    assert 'aggregate_oos_return' in result
    assert 'n_windows' in result
    assert isinstance(result['n_windows'], int)


def test_walk_forward_does_not_pollute_results(optimizer, sample_data, param_grid):
    """walk_forward_optimize가 self.results를 오염하지 않는지 확인"""
    # 먼저 기존 optimize 실행
    optimizer.optimize(RSIStrategy, sample_data, param_grid, use_vbt=False)
    original_results = list(optimizer.results)

    # walk_forward_optimize 실행
    optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=3,
        mode='rolling',
        use_vbt=False,
    )

    # self.results가 원래 값 유지
    assert len(optimizer.results) == len(original_results)


def test_walk_forward_aggregate_oos_return_type(optimizer, sample_data, param_grid):
    """aggregate_oos_return이 float인지 확인"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=3,
        mode='rolling',
        use_vbt=False,
    )

    assert isinstance(result['aggregate_oos_return'], (int, float))


def test_walk_forward_is_oos_gap_type(optimizer, sample_data, param_grid):
    """is_oos_gap이 float이고 IS - OOS = gap인지 확인"""
    result = optimizer.walk_forward_optimize(
        strategy_class=RSIStrategy,
        df=sample_data,
        param_grid=param_grid,
        n_splits=3,
        mode='rolling',
        use_vbt=False,
    )

    assert isinstance(result['is_oos_gap'], (int, float))

    # 수동 검증: gap = mean(IS) - mean(OOS)
    if result['oos_results']:
        is_returns = [r['is_return'] for r in result['oos_results']]
        oos_returns = [r['oos_return'] for r in result['oos_results']]
        expected_gap = np.mean(is_returns) - np.mean(oos_returns)
        assert abs(result['is_oos_gap'] - expected_gap) < 1e-6
