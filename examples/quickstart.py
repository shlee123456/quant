"""
Quick start example - Simple backtest with simulation data
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.backtester import Backtester
from trading_bot.optimizer import StrategyOptimizer


def main():
    print("="*80)
    print("Crypto Trading Bot - Quick Start")
    print("="*80)

    # 1. Generate simulation data
    print("\n1. Generating simulation data...")
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=500, trend='bullish')
    print(f"   ✓ Generated {len(df)} candlesticks")
    print(f"   ✓ Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    # 2. Create and test RSI strategy
    print("\n2. Testing RSI Strategy...")
    rsi_strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    backtester = Backtester(rsi_strategy, initial_capital=10000)
    rsi_results = backtester.run(df)
    print(f"   ✓ Total Return: {rsi_results['total_return']:.2f}%")
    print(f"   ✓ Win Rate: {rsi_results['win_rate']:.2f}%")
    print(f"   ✓ Sharpe Ratio: {rsi_results['sharpe_ratio']:.2f}")

    # 3. Compare strategies
    print("\n3. Comparing multiple strategies...")
    strategies = [
        MovingAverageCrossover(fast_period=10, slow_period=30),
        RSIStrategy(period=14),
        MACDStrategy()
    ]

    optimizer = StrategyOptimizer(initial_capital=10000)
    comparison = optimizer.compare_strategies(strategies, df)

    print("\n   Strategy Performance:")
    for _, row in comparison.iterrows():
        print(f"   • {row['strategy']:<30} Return: {row['total_return']:>7.2f}%")

    # 4. Find optimal parameters
    print("\n4. Optimizing RSI parameters...")
    param_grid = {
        'period': [7, 14, 21],
        'overbought': [70, 75],
        'oversold': [25, 30]
    }

    best_result = optimizer.optimize(RSIStrategy, df, param_grid)
    print(f"\n   ✓ Best Parameters: {best_result['params']}")
    print(f"   ✓ Optimized Return: {best_result['total_return']:.2f}%")

    print("\n" + "="*80)
    print("✅ Quick start completed successfully!")
    print("="*80)
    print("\nNext steps:")
    print("  • Try different market scenarios (bullish, bearish, sideways)")
    print("  • Experiment with different strategy parameters")
    print("  • Run: python examples/run_backtest_example.py for more examples")
    print("  • Read README.md for detailed documentation")


if __name__ == "__main__":
    main()
