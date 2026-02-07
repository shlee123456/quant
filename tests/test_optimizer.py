"""
Tests for Strategy Optimizer
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
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.simulation_data import SimulationDataGenerator


@pytest.fixture
def sample_data():
    """Create sample data for testing"""
    gen = SimulationDataGenerator(seed=42)
    return gen.generate_trend_data(periods=500, trend='bullish')


@pytest.fixture
def optimizer():
    """Create optimizer instance"""
    return StrategyOptimizer(initial_capital=10000, position_size=0.95, commission=0.001)


def test_optimizer_initialization():
    """Test optimizer initialization"""
    optimizer = StrategyOptimizer(initial_capital=10000, position_size=0.95, commission=0.001)

    assert optimizer.initial_capital == 10000
    assert optimizer.position_size == 0.95
    assert optimizer.commission == 0.001
    assert optimizer.results == []


def test_optimize_rsi(optimizer, sample_data):
    """Test optimizing RSI strategy"""
    param_grid = {
        'period': [7, 14],
        'overbought': [70, 75],
        'oversold': [25, 30]
    }

    result = optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Should return best result
    assert 'params' in result
    assert 'total_return' in result
    assert 'sharpe_ratio' in result
    assert 'max_drawdown' in result

    # Should have tested all combinations (2 * 2 * 2 = 8)
    assert len(optimizer.results) == 8

    # Results should be sorted by total_return
    returns = [r['total_return'] for r in optimizer.results]
    assert returns == sorted(returns, reverse=True)


def test_optimize_macd(optimizer, sample_data):
    """Test optimizing MACD strategy"""
    param_grid = {
        'fast_period': [8, 12],
        'slow_period': [20, 26],
        'signal_period': [7, 9]
    }

    result = optimizer.optimize(MACDStrategy, sample_data, param_grid)

    assert 'params' in result
    # Should have tested all combinations (2 * 2 * 2 = 8)
    assert len(optimizer.results) == 8


def test_compare_strategies(optimizer, sample_data):
    """Test comparing multiple strategies"""
    strategies = [
        RSIStrategy(period=14),
        MACDStrategy(),
        MovingAverageCrossover(fast_period=10, slow_period=30)
    ]

    comparison_df = optimizer.compare_strategies(strategies, sample_data)

    # Should return DataFrame
    assert isinstance(comparison_df, pd.DataFrame)

    # Should have all strategies
    assert len(comparison_df) == 3

    # Should have required columns
    required_cols = ['strategy', 'total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']
    assert all(col in comparison_df.columns for col in required_cols)

    # Should be sorted by total_return descending
    assert comparison_df['total_return'].is_monotonic_decreasing


def test_get_optimization_results(optimizer, sample_data):
    """Test getting optimization results as DataFrame"""
    param_grid = {
        'period': [7, 14],
        'overbought': [70],
        'oversold': [30]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)
    results_df = optimizer.get_optimization_results()

    # Should return DataFrame
    assert isinstance(results_df, pd.DataFrame)

    # Should have all results
    assert len(results_df) == 2

    # Should have parameter columns
    assert 'period' in results_df.columns
    assert 'overbought' in results_df.columns
    assert 'oversold' in results_df.columns

    # Should have metrics
    assert 'total_return' in results_df.columns
    assert 'sharpe_ratio' in results_df.columns


def test_get_optimization_results_empty(optimizer):
    """Test getting results when no optimization has been run"""
    results_df = optimizer.get_optimization_results()

    assert isinstance(results_df, pd.DataFrame)
    assert results_df.empty


def test_get_top_n_strategies(optimizer, sample_data):
    """Test getting top N strategies"""
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [70],
        'oversold': [30]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Get top 2
    top_2 = optimizer.get_top_n_strategies(n=2, metric='total_return')

    assert len(top_2) == 2
    assert top_2[0]['total_return'] >= top_2[1]['total_return']


def test_get_top_n_strategies_empty(optimizer):
    """Test getting top N when no results"""
    top_n = optimizer.get_top_n_strategies(n=5)

    assert top_n == []


def test_analyze_parameter_sensitivity(optimizer, sample_data):
    """Test parameter sensitivity analysis"""
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [70, 75],
        'oversold': [25, 30]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Analyze period sensitivity
    sensitivity = optimizer.analyze_parameter_sensitivity('period', 'total_return')

    assert isinstance(sensitivity, pd.DataFrame)
    assert len(sensitivity) == 3  # 3 different period values
    assert 'mean' in sensitivity.columns
    assert 'std' in sensitivity.columns


def test_analyze_parameter_sensitivity_empty(optimizer):
    """Test sensitivity analysis with no results"""
    sensitivity = optimizer.analyze_parameter_sensitivity('period', 'total_return')

    assert isinstance(sensitivity, pd.DataFrame)
    assert sensitivity.empty


def test_optimization_with_single_param(optimizer, sample_data):
    """Test optimization with single parameter"""
    param_grid = {
        'period': [7, 14, 21, 28]
    }

    result = optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Should have tested all values
    assert len(optimizer.results) == 4

    # Best result should have one of the tested periods
    assert result['params']['period'] in [7, 14, 21, 28]


def test_optimization_stores_all_metrics(optimizer, sample_data):
    """Test that optimization stores all backtest metrics"""
    param_grid = {
        'period': [14]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    result = optimizer.results[0]

    # Should have all standard metrics
    required_metrics = [
        'initial_capital', 'final_capital', 'total_return',
        'total_trades', 'winning_trades', 'losing_trades',
        'win_rate', 'max_drawdown', 'sharpe_ratio'
    ]

    for metric in required_metrics:
        assert metric in result


def test_different_ranking_metrics(optimizer, sample_data):
    """Test getting top strategies by different metrics"""
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [70],
        'oversold': [30]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Get top by return
    top_return = optimizer.get_top_n_strategies(n=1, metric='total_return')[0]

    # Get top by Sharpe
    top_sharpe = optimizer.get_top_n_strategies(n=1, metric='sharpe_ratio')[0]

    # Should have the metrics
    assert 'total_return' in top_return
    assert 'sharpe_ratio' in top_sharpe


def test_compare_strategies_with_same_type(optimizer, sample_data):
    """Test comparing multiple instances of same strategy type"""
    strategies = [
        RSIStrategy(period=7),
        RSIStrategy(period=14),
        RSIStrategy(period=21)
    ]

    comparison_df = optimizer.compare_strategies(strategies, sample_data)

    assert len(comparison_df) == 3

    # All should be RSI strategies with different names
    assert all('RSI' in name for name in comparison_df['strategy'])


def test_optimizer_with_different_capital(sample_data):
    """Test optimizer with different initial capital"""
    optimizer1 = StrategyOptimizer(initial_capital=10000)
    optimizer2 = StrategyOptimizer(initial_capital=50000)

    param_grid = {'period': [14]}

    result1 = optimizer1.optimize(RSIStrategy, sample_data, param_grid)
    result2 = optimizer2.optimize(RSIStrategy, sample_data, param_grid)

    # Initial capital should be different
    assert result1['initial_capital'] == 10000
    assert result2['initial_capital'] == 50000

    # Total return percentage should be similar (capital shouldn't affect %)
    assert abs(result1['total_return'] - result2['total_return']) < 1.0


def test_optimizer_with_different_commission(sample_data):
    """Test that commission affects results"""
    optimizer_low_comm = StrategyOptimizer(commission=0.0001)
    optimizer_high_comm = StrategyOptimizer(commission=0.01)

    param_grid = {'period': [14]}

    result_low = optimizer_low_comm.optimize(RSIStrategy, sample_data, param_grid)
    result_high = optimizer_high_comm.optimize(RSIStrategy, sample_data, param_grid)

    # Higher commission should result in lower returns
    assert result_low['total_return'] > result_high['total_return']


def test_optimization_with_ma_strategy(optimizer, sample_data):
    """Test optimization with MovingAverageCrossover strategy"""
    param_grid = {
        'fast_period': [5, 10],
        'slow_period': [20, 30]
    }

    result = optimizer.optimize(MovingAverageCrossover, sample_data, param_grid)

    assert 'params' in result
    assert 'fast_period' in result['params']
    assert 'slow_period' in result['params']
    assert len(optimizer.results) == 4


def test_parameter_combinations_count(optimizer, sample_data):
    """Test that correct number of parameter combinations are tested"""
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [65, 70, 75],
        'oversold': [25, 30, 35]
    }

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    # Should test 3 * 3 * 3 = 27 combinations
    assert len(optimizer.results) == 27


def test_strategy_name_in_results(optimizer, sample_data):
    """Test that strategy name is stored in results"""
    param_grid = {'period': [14]}

    optimizer.optimize(RSIStrategy, sample_data, param_grid)

    result = optimizer.results[0]
    assert 'strategy_name' in result
    assert 'RSI' in result['strategy_name']


def test_compare_empty_strategy_list(optimizer, sample_data):
    """Test comparing empty strategy list"""
    comparison_df = optimizer.compare_strategies([], sample_data)

    assert isinstance(comparison_df, pd.DataFrame)
    assert len(comparison_df) == 0
