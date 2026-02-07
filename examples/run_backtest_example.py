"""
Comprehensive backtesting example demonstrating all features
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.backtester import Backtester
from trading_bot.optimizer import StrategyOptimizer


def example_1_basic_backtest():
    """Example 1: Basic backtest with RSI strategy"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Backtest with RSI Strategy")
    print("="*80)

    # Generate simulation data
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish', volatility=0.02)

    # Create RSI strategy
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)

    # Run backtest
    backtester = Backtester(strategy, initial_capital=10000)
    results = backtester.run(df)

    # Print results
    backtester.print_results(results)

    # Show sample trades
    trades_df = backtester.get_trades_df()
    print("Sample Trades:")
    print(trades_df.head(10))


def example_2_compare_strategies():
    """Example 2: Compare multiple strategies"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Compare Multiple Strategies")
    print("="*80)

    # Generate simulation data
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='sideways', volatility=0.03)

    # Create multiple strategies
    strategies = [
        MovingAverageCrossover(fast_period=10, slow_period=30),
        MovingAverageCrossover(fast_period=20, slow_period=50),
        RSIStrategy(period=14, overbought=70, oversold=30),
        RSIStrategy(period=21, overbought=75, oversold=25),
        MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
    ]

    # Compare strategies
    optimizer = StrategyOptimizer(initial_capital=10000)
    comparison_df = optimizer.compare_strategies(strategies, df)

    print("\nDetailed Comparison:")
    print(comparison_df.to_string())


def example_3_optimize_parameters():
    """Example 3: Optimize RSI parameters"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Optimize RSI Parameters")
    print("="*80)

    # Generate simulation data
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish')

    # Define parameter grid
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [70, 75, 80],
        'oversold': [20, 25, 30]
    }

    # Optimize
    optimizer = StrategyOptimizer(initial_capital=10000)
    best_result = optimizer.optimize(RSIStrategy, df, param_grid)

    # Get top 5 parameter combinations
    top_5 = optimizer.get_top_n_strategies(n=5, metric='total_return')

    print("\nTop 5 Parameter Combinations:")
    for i, result in enumerate(top_5, 1):
        print(f"\n{i}. Parameters: {result['params']}")
        print(f"   Total Return: {result['total_return']:.2f}%")
        print(f"   Sharpe Ratio: {result['sharpe_ratio']:.2f}")
        print(f"   Max Drawdown: {result['max_drawdown']:.2f}%")

    # Analyze parameter sensitivity
    print("\n" + "-"*80)
    sensitivity = optimizer.analyze_parameter_sensitivity('period', 'total_return')


def example_4_market_scenarios():
    """Example 4: Test strategy across different market conditions"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Test Strategy Across Market Scenarios")
    print("="*80)

    # Create strategy
    strategy = MACDStrategy()

    # Generate different market scenarios
    data_gen = SimulationDataGenerator(seed=42)

    scenarios = {
        'Bullish Market': data_gen.generate_trend_data(periods=1000, trend='bullish'),
        'Bearish Market': data_gen.generate_trend_data(periods=1000, trend='bearish'),
        'Sideways Market': data_gen.generate_trend_data(periods=1000, trend='sideways'),
        'Volatile Market': data_gen.generate_volatile_data(periods=1000),
        'Cyclical Market': data_gen.generate_cyclical_data(periods=1000, cycle_length=100),
    }

    # Test strategy on each scenario
    results_summary = []

    for scenario_name, df in scenarios.items():
        backtester = Backtester(strategy, initial_capital=10000)
        results = backtester.run(df)

        results_summary.append({
            'Scenario': scenario_name,
            'Total Return %': results['total_return'],
            'Sharpe Ratio': results['sharpe_ratio'],
            'Max Drawdown %': results['max_drawdown'],
            'Win Rate %': results['win_rate'],
            'Total Trades': results['total_trades']
        })

    # Print summary
    import pandas as pd
    summary_df = pd.DataFrame(results_summary)

    print("\nStrategy Performance Across Market Scenarios:")
    print(summary_df.to_string(index=False))


def example_5_custom_simulation():
    """Example 5: Create custom simulation with market shock"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Custom Simulation with Market Shock")
    print("="*80)

    # Generate base data
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish', volatility=0.02)

    # Add market crash in the middle
    from datetime import timedelta
    crash_date = df.index[500]
    df_with_shock = data_gen.add_market_shock(df, shock_date=crash_date, shock_magnitude=-0.3)

    # Test strategy before and after shock
    strategy = RSIStrategy(period=14)

    # Before shock
    df_before = df_with_shock[:500]
    backtester_before = Backtester(strategy, initial_capital=10000)
    results_before = backtester_before.run(df_before)

    # After shock
    df_after = df_with_shock[500:]
    backtester_after = Backtester(strategy, initial_capital=10000)
    results_after = backtester_after.run(df_after)

    # Full period
    backtester_full = Backtester(strategy, initial_capital=10000)
    results_full = backtester_full.run(df_with_shock)

    print("\nPerformance Before Market Shock:")
    print(f"  Total Return: {results_before['total_return']:.2f}%")
    print(f"  Sharpe Ratio: {results_before['sharpe_ratio']:.2f}")

    print("\nPerformance After Market Shock:")
    print(f"  Total Return: {results_after['total_return']:.2f}%")
    print(f"  Sharpe Ratio: {results_after['sharpe_ratio']:.2f}")

    print("\nPerformance Full Period (with shock):")
    print(f"  Total Return: {results_full['total_return']:.2f}%")
    print(f"  Sharpe Ratio: {results_full['sharpe_ratio']:.2f}")


def example_6_optimization_comparison():
    """Example 6: Optimize and compare different strategy types"""
    print("\n" + "="*80)
    print("EXAMPLE 6: Optimize and Compare Different Strategy Types")
    print("="*80)

    # Generate data
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish')

    optimizer = StrategyOptimizer(initial_capital=10000)

    # Optimize MA strategy
    print("\nOptimizing Moving Average Crossover...")
    ma_best = optimizer.optimize(
        MovingAverageCrossover,
        df,
        param_grid={
            'fast_period': [5, 10, 20],
            'slow_period': [30, 50, 100]
        }
    )

    # Optimize RSI strategy
    print("\nOptimizing RSI Strategy...")
    rsi_best = optimizer.optimize(
        RSIStrategy,
        df,
        param_grid={
            'period': [7, 14, 21],
            'overbought': [70, 75],
            'oversold': [25, 30]
        }
    )

    # Optimize MACD strategy
    print("\nOptimizing MACD Strategy...")
    macd_best = optimizer.optimize(
        MACDStrategy,
        df,
        param_grid={
            'fast_period': [8, 12, 16],
            'slow_period': [20, 26, 32],
            'signal_period': [7, 9, 11]
        }
    )

    # Compare optimized strategies
    print("\n" + "="*80)
    print("OPTIMIZED STRATEGIES COMPARISON")
    print("="*80)

    import pandas as pd
    comparison = pd.DataFrame([
        {
            'Strategy': 'MA Crossover',
            'Parameters': ma_best['params'],
            'Return %': ma_best['total_return'],
            'Sharpe': ma_best['sharpe_ratio'],
            'Max DD %': ma_best['max_drawdown']
        },
        {
            'Strategy': 'RSI',
            'Parameters': rsi_best['params'],
            'Return %': rsi_best['total_return'],
            'Sharpe': rsi_best['sharpe_ratio'],
            'Max DD %': rsi_best['max_drawdown']
        },
        {
            'Strategy': 'MACD',
            'Parameters': macd_best['params'],
            'Return %': macd_best['total_return'],
            'Sharpe': macd_best['sharpe_ratio'],
            'Max DD %': macd_best['max_drawdown']
        }
    ])

    print(comparison.to_string(index=False))


def main():
    """Run all examples"""
    print("\n" + "#"*80)
    print("# CRYPTO TRADING BOT - COMPREHENSIVE EXAMPLES")
    print("#"*80)

    examples = [
        ("Basic Backtest", example_1_basic_backtest),
        ("Compare Strategies", example_2_compare_strategies),
        ("Optimize Parameters", example_3_optimize_parameters),
        ("Market Scenarios", example_4_market_scenarios),
        ("Custom Simulation", example_5_custom_simulation),
        ("Optimization Comparison", example_6_optimization_comparison),
    ]

    print("\nAvailable Examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print("\nRunning all examples...\n")

    for name, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"\nError in {name}: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "#"*80)
    print("# ALL EXAMPLES COMPLETED")
    print("#"*80 + "\n")


if __name__ == "__main__":
    main()
