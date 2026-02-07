"""
Strategy Comparison Script

This script compares the performance of all trading strategies using their default parameters
across different market conditions.
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
from trading_bot.backtester import Backtester


def compare_strategies_on_market(df, market_type):
    """Compare all strategies on a given market condition"""
    print(f"\n{'='*80}")
    print(f"Market Condition: {market_type.upper()}")
    print(f"{'='*80}")

    # Initialize all strategies with default parameters
    strategies = {
        'Moving Average (10/30)': MovingAverageCrossover(fast_period=10, slow_period=30),
        'RSI (14, 30/70)': RSIStrategy(period=14, overbought=70, oversold=30),
        'MACD (12/26/9)': MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
        'Bollinger Bands (20, 2.0)': BollingerBandsStrategy(period=20, num_std=2.0),
        'Stochastic (14/3, 20/80)': StochasticStrategy(k_period=14, d_period=3, overbought=80, oversold=20)
    }

    results = []

    for name, strategy in strategies.items():
        backtester = Backtester(strategy, initial_capital=10000)
        metrics = backtester.run(df)

        results.append({
            'Strategy': name,
            'Market': market_type,
            'Total Return (%)': metrics['total_return'],
            'Sharpe Ratio': metrics['sharpe_ratio'],
            'Max Drawdown (%)': metrics['max_drawdown'],
            'Win Rate (%)': metrics['win_rate'],
            'Total Trades': metrics['total_trades'],
            'Final Capital': metrics['final_capital']
        })

    # Create DataFrame and display
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('Sharpe Ratio', ascending=False)

    print(f"\n{df_results.to_string(index=False)}")

    return df_results


def print_overall_summary(all_results):
    """Print overall summary across all market conditions"""
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY - Average Performance Across All Market Conditions")
    print(f"{'='*80}\n")

    # Calculate average metrics for each strategy
    summary = all_results.groupby('Strategy').agg({
        'Total Return (%)': 'mean',
        'Sharpe Ratio': 'mean',
        'Max Drawdown (%)': 'mean',
        'Win Rate (%)': 'mean',
        'Total Trades': 'mean'
    }).round(2)

    summary = summary.sort_values('Sharpe Ratio', ascending=False)

    print(summary.to_string())
    print("\n")

    # Best strategy for each market condition
    print("Best Strategy by Market Condition:")
    print("-" * 80)
    for market in all_results['Market'].unique():
        market_data = all_results[all_results['Market'] == market]
        best = market_data.loc[market_data['Sharpe Ratio'].idxmax()]
        print(f"{market:15s} - {best['Strategy']:30s} (Sharpe: {best['Sharpe Ratio']:6.2f})")
    print("-" * 80)


def main():
    """Main comparison function"""
    print("="*80)
    print("STRATEGY COMPARISON")
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

    all_results = []

    # Compare strategies on each market condition
    for market_type, df in market_conditions.items():
        result_df = compare_strategies_on_market(df, market_type)
        all_results.append(result_df)

    # Combine all results
    combined_results = pd.concat(all_results, ignore_index=True)

    # Print overall summary
    print_overall_summary(combined_results)

    # Save results to CSV
    output_file = 'docs/strategy_comparison_results.csv'
    combined_results.to_csv(output_file, index=False)
    print(f"\nResults saved to {output_file}")

    # Create a pivot table for easy viewing
    print("\n\nPivot Table - Sharpe Ratio by Strategy and Market:")
    print("="*80)
    pivot = combined_results.pivot(index='Strategy', columns='Market', values='Sharpe Ratio')
    pivot['Average'] = pivot.mean(axis=1)
    pivot = pivot.sort_values('Average', ascending=False)
    print(pivot.round(2).to_string())
    print("="*80)


if __name__ == '__main__':
    main()
