"""
Strategy Optimization Script

This script optimizes parameters for all trading strategies across different market conditions.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from trading_bot.strategies import (
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
    StochasticStrategy
)
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.simulation_data import SimulationDataGenerator
import json


def optimize_ma_strategy(df, market_type):
    """Optimize Moving Average Crossover strategy"""
    print(f"\n  Optimizing Moving Average for {market_type} market...")

    param_grid = {
        'fast_period': [5, 10, 15, 20],
        'slow_period': [20, 30, 50, 100]
    }

    optimizer = StrategyOptimizer()
    best_result = optimizer.optimize(
        MovingAverageCrossover,
        df,
        param_grid
    )

    # Get all results and sort by Sharpe ratio
    all_results = optimizer.get_optimization_results()
    all_results = all_results.sort_values('sharpe_ratio', ascending=False)
    best_by_sharpe = all_results.iloc[0]

    return {
        'strategy': 'Moving Average Crossover',
        'market_type': market_type,
        'best_params': best_by_sharpe['params'] if 'params' in best_by_sharpe else {k: best_by_sharpe[k] for k in param_grid.keys()},
        'best_sharpe': best_by_sharpe['sharpe_ratio'],
        'best_return': best_by_sharpe['total_return'],
        'top_3_results': all_results.head(3)[['fast_period', 'slow_period', 'total_return', 'sharpe_ratio', 'max_drawdown']].to_dict('records')
    }


def optimize_rsi_strategy(df, market_type):
    """Optimize RSI strategy"""
    print(f"\n  Optimizing RSI for {market_type} market...")

    param_grid = {
        'period': [7, 14, 21],
        'overbought': [65, 70, 75, 80],
        'oversold': [20, 25, 30, 35]
    }

    optimizer = StrategyOptimizer()
    best_result = optimizer.optimize(
        RSIStrategy,
        df,
        param_grid
    )

    all_results = optimizer.get_optimization_results()
    all_results = all_results.sort_values('sharpe_ratio', ascending=False)
    best_by_sharpe = all_results.iloc[0]

    return {
        'strategy': 'RSI',
        'market_type': market_type,
        'best_params': {k: best_by_sharpe[k] for k in param_grid.keys()},
        'best_sharpe': best_by_sharpe['sharpe_ratio'],
        'best_return': best_by_sharpe['total_return'],
        'top_3_results': all_results.head(3)[list(param_grid.keys()) + ['total_return', 'sharpe_ratio', 'max_drawdown']].to_dict('records')
    }


def optimize_macd_strategy(df, market_type):
    """Optimize MACD strategy"""
    print(f"\n  Optimizing MACD for {market_type} market...")

    param_grid = {
        'fast_period': [8, 12, 16],
        'slow_period': [21, 26, 30],
        'signal_period': [6, 9, 12]
    }

    optimizer = StrategyOptimizer()
    best_result = optimizer.optimize(
        MACDStrategy,
        df,
        param_grid
    )

    all_results = optimizer.get_optimization_results()
    all_results = all_results.sort_values('sharpe_ratio', ascending=False)
    best_by_sharpe = all_results.iloc[0]

    return {
        'strategy': 'MACD',
        'market_type': market_type,
        'best_params': {k: best_by_sharpe[k] for k in param_grid.keys()},
        'best_sharpe': best_by_sharpe['sharpe_ratio'],
        'best_return': best_by_sharpe['total_return'],
        'top_3_results': all_results.head(3)[list(param_grid.keys()) + ['total_return', 'sharpe_ratio', 'max_drawdown']].to_dict('records')
    }


def optimize_bollinger_strategy(df, market_type):
    """Optimize Bollinger Bands strategy"""
    print(f"\n  Optimizing Bollinger Bands for {market_type} market...")

    param_grid = {
        'period': [10, 20, 30],
        'num_std': [1.5, 2.0, 2.5, 3.0]
    }

    optimizer = StrategyOptimizer()
    best_result = optimizer.optimize(
        BollingerBandsStrategy,
        df,
        param_grid
    )

    all_results = optimizer.get_optimization_results()
    all_results = all_results.sort_values('sharpe_ratio', ascending=False)
    best_by_sharpe = all_results.iloc[0]

    return {
        'strategy': 'Bollinger Bands',
        'market_type': market_type,
        'best_params': {k: best_by_sharpe[k] for k in param_grid.keys()},
        'best_sharpe': best_by_sharpe['sharpe_ratio'],
        'best_return': best_by_sharpe['total_return'],
        'top_3_results': all_results.head(3)[list(param_grid.keys()) + ['total_return', 'sharpe_ratio', 'max_drawdown']].to_dict('records')
    }


def optimize_stochastic_strategy(df, market_type):
    """Optimize Stochastic Oscillator strategy"""
    print(f"\n  Optimizing Stochastic for {market_type} market...")

    param_grid = {
        'k_period': [5, 14, 21],
        'd_period': [3, 5, 7],
        'overbought': [70, 80],
        'oversold': [20, 30]
    }

    optimizer = StrategyOptimizer()
    best_result = optimizer.optimize(
        StochasticStrategy,
        df,
        param_grid
    )

    all_results = optimizer.get_optimization_results()
    all_results = all_results.sort_values('sharpe_ratio', ascending=False)
    best_by_sharpe = all_results.iloc[0]

    return {
        'strategy': 'Stochastic Oscillator',
        'market_type': market_type,
        'best_params': {k: best_by_sharpe[k] for k in param_grid.keys()},
        'best_sharpe': best_by_sharpe['sharpe_ratio'],
        'best_return': best_by_sharpe['total_return'],
        'top_3_results': all_results.head(3)[list(param_grid.keys()) + ['total_return', 'sharpe_ratio', 'max_drawdown']].to_dict('records')
    }


def main():
    """Main optimization function"""
    print("="*80)
    print("STRATEGY OPTIMIZATION")
    print("="*80)

    # Generate different market conditions
    generator = SimulationDataGenerator()

    print("\nGenerating market data...")
    market_conditions = {
        'trending_up': generator.generate_trend_data(periods=500, trend='bullish'),
        'trending_down': generator.generate_trend_data(periods=500, trend='bearish'),
        'volatile': generator.generate_volatile_data(periods=500),
        'cyclical': generator.generate_cyclical_data(periods=500, cycle_length=50)
    }

    # Store all results
    all_results = []

    # Optimize each strategy on each market condition
    for market_type, df in market_conditions.items():
        print(f"\n{'='*80}")
        print(f"Market Condition: {market_type.upper()}")
        print(f"{'='*80}")

        # Optimize all strategies
        results = [
            optimize_ma_strategy(df, market_type),
            optimize_rsi_strategy(df, market_type),
            optimize_macd_strategy(df, market_type),
            optimize_bollinger_strategy(df, market_type),
            optimize_stochastic_strategy(df, market_type)
        ]

        all_results.extend(results)

    # Save results to JSON
    output_file = 'docs/optimization_results.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*80}")
    print(f"Optimization complete! Results saved to {output_file}")
    print(f"{'='*80}")

    # Print summary
    print("\n\nSUMMARY - Best Sharpe Ratios by Strategy:")
    print("-" * 80)

    # Group by strategy and find best result
    df_results = pd.DataFrame(all_results)

    # Find best Sharpe ratio for each strategy across all markets
    best_by_strategy = {}
    for strategy in df_results['strategy'].unique():
        strategy_results = df_results[df_results['strategy'] == strategy]
        best_idx = strategy_results['best_sharpe'].idxmax()
        best_by_strategy[strategy] = {
            'sharpe': strategy_results.loc[best_idx, 'best_sharpe'],
            'market': strategy_results.loc[best_idx, 'market_type']
        }

    # Sort and display
    sorted_strategies = sorted(best_by_strategy.items(), key=lambda x: x[1]['sharpe'], reverse=True)

    for strategy, info in sorted_strategies:
        print(f"{strategy:25s} - Sharpe: {info['sharpe']:6.2f} (best on {info['market']} market)")

    print("-" * 80)


if __name__ == '__main__':
    main()
