"""
Tests for Optimizer VBT path (use_vbt=True)

optimize() 및 compare_strategies()가 use_vbt=True일 때
use_vbt=False와 동일한 결과 형식을 반환하는지 테스트
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy


@pytest.fixture
def sample_data():
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_ohlcv(periods=300, volatility=0.03)


@pytest.fixture
def small_param_grid():
    """작은 파라미터 그리드 (2-3 조합)"""
    return {
        'period': [10, 14],
        'overbought': [70],
        'oversold': [30],
    }


class TestOptimizeVBT:
    """optimize() with use_vbt=True"""

    def test_returns_dict_with_params(self, sample_data, small_param_grid):
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        assert isinstance(result, dict)
        assert 'params' in result
        assert 'total_return' in result
        assert 'sharpe_ratio' in result
        assert 'max_drawdown' in result
        assert 'win_rate' in result

    def test_same_format_as_legacy(self, sample_data, small_param_grid):
        """use_vbt=True와 False가 동일한 키를 반환"""
        optimizer_legacy = StrategyOptimizer(initial_capital=10000)
        optimizer_vbt = StrategyOptimizer(initial_capital=10000)

        r_legacy = optimizer_legacy.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=False)
        r_vbt = optimizer_vbt.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        # 키가 동일해야 함
        assert set(r_legacy.keys()) == set(r_vbt.keys())

    def test_best_params_in_grid(self, sample_data, small_param_grid):
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        assert result['params']['period'] in small_param_grid['period']
        assert result['params']['overbought'] in small_param_grid['overbought']
        assert result['params']['oversold'] in small_param_grid['oversold']

    def test_results_stored(self, sample_data, small_param_grid):
        optimizer = StrategyOptimizer(initial_capital=10000)
        optimizer.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        assert len(optimizer.results) == 2  # 2 combos from grid

    def test_total_return_not_nan(self, sample_data, small_param_grid):
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        assert not np.isnan(result['total_return'])

    def test_get_optimization_results_df(self, sample_data, small_param_grid):
        """get_optimization_results()가 DataFrame을 반환"""
        optimizer = StrategyOptimizer(initial_capital=10000)
        optimizer.optimize(RSIStrategy, sample_data, small_param_grid, use_vbt=True)

        df = optimizer.get_optimization_results()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2


class TestCompareStrategiesVBT:
    """compare_strategies() with use_vbt=True"""

    def test_returns_dataframe(self, sample_data):
        strategies = [
            RSIStrategy(period=10, overbought=70, oversold=30),
            RSIStrategy(period=14, overbought=70, oversold=30),
        ]
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.compare_strategies(strategies, sample_data, use_vbt=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_same_columns_as_legacy(self, sample_data):
        """use_vbt=True와 False가 동일한 컬럼을 반환"""
        strategies = [
            RSIStrategy(period=10, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
        ]
        optimizer_legacy = StrategyOptimizer(initial_capital=10000)
        optimizer_vbt = StrategyOptimizer(initial_capital=10000)

        df_legacy = optimizer_legacy.compare_strategies(strategies, sample_data, use_vbt=False)
        df_vbt = optimizer_vbt.compare_strategies(strategies, sample_data, use_vbt=True)

        assert set(df_legacy.columns) == set(df_vbt.columns)

    def test_empty_strategy_list(self, sample_data):
        optimizer = StrategyOptimizer()
        result = optimizer.compare_strategies([], sample_data, use_vbt=True)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_comparison_has_expected_columns(self, sample_data):
        strategies = [RSIStrategy(period=14)]
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.compare_strategies(strategies, sample_data, use_vbt=True)

        expected_cols = {'strategy', 'total_return', 'sharpe_ratio', 'max_drawdown',
                         'win_rate', 'total_trades', 'final_capital'}
        assert expected_cols.issubset(set(result.columns))


class TestLegacyUnchanged:
    """use_vbt=False (기본값)이 기존 동작과 동일한지 확인"""

    def test_optimize_default_uses_legacy(self, sample_data, small_param_grid):
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.optimize(RSIStrategy, sample_data, small_param_grid)

        assert 'params' in result
        assert 'total_return' in result

    def test_compare_default_uses_legacy(self, sample_data):
        strategies = [RSIStrategy(period=14)]
        optimizer = StrategyOptimizer(initial_capital=10000)
        result = optimizer.compare_strategies(strategies, sample_data)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
