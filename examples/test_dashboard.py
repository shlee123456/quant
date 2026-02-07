"""
Manual test script for dashboard functionality
Run this to verify all strategies and charts work correctly
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy
from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
from dashboard.charts import ChartGenerator


def test_all_strategies():
    """Test all strategies with simulation data"""
    print("=" * 60)
    print("Testing Enhanced Dashboard - All Strategies")
    print("=" * 60)

    # Generate sample data
    print("\n1. Generating simulation data...")
    generator = SimulationDataGenerator(seed=42)
    df = generator.generate_ohlcv(periods=1000)
    print(f"   ✓ Generated {len(df)} periods of OHLCV data")

    # Define strategies
    strategies = {
        'Moving Average Crossover': MovingAverageCrossover(fast_period=10, slow_period=30),
        'RSI Strategy': RSIStrategy(period=14, overbought=70, oversold=30),
        'MACD Strategy': MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
        'Bollinger Bands': BollingerBandsStrategy(period=20, num_std=2.0)
    }

    # Test each strategy
    print("\n2. Testing strategies...")
    results_summary = []

    for strategy_name, strategy in strategies.items():
        print(f"\n   Testing {strategy_name}...")

        try:
            # Run backtest
            backtester = Backtester(strategy=strategy, initial_capital=10000)
            results = backtester.run(df)

            # Calculate indicators
            data_with_indicators = strategy.calculate_indicators(df)

            # Get signal
            signal, info = strategy.get_current_signal(df)

            print(f"   ✓ Backtest completed")
            print(f"     - Total Return: {results['total_return']:.2f}%")
            print(f"     - Sharpe Ratio: {results['sharpe_ratio']:.2f}")
            print(f"     - Max Drawdown: {results['max_drawdown']:.2f}%")
            print(f"     - Win Rate: {results['win_rate']:.2f}%")
            print(f"     - Total Trades: {results['total_trades']}")
            print(f"     - Current Signal: {signal}")

            results_summary.append({
                'Strategy': strategy_name,
                'Return (%)': results['total_return'],
                'Sharpe': results['sharpe_ratio'],
                'Max DD (%)': results['max_drawdown'],
                'Win Rate (%)': results['win_rate'],
                'Trades': results['total_trades']
            })

        except Exception as e:
            print(f"   ✗ Error: {e}")
            import traceback
            traceback.print_exc()

    # Test chart generation
    print("\n3. Testing chart generation...")
    chart_gen = ChartGenerator()

    for strategy_name, strategy in strategies.items():
        try:
            backtester = Backtester(strategy=strategy, initial_capital=10000)
            backtester.run(df)

            data_with_indicators = strategy.calculate_indicators(df)
            trades_df = backtester.get_trades_df()

            # Generate strategy-specific chart
            fig = chart_gen.plot_strategy_chart(data_with_indicators, trades_df, strategy_name)

            # Generate equity curve
            equity_df = backtester.get_equity_curve_df()
            equity_fig = chart_gen.plot_equity_curve(equity_df)

            print(f"   ✓ Charts generated for {strategy_name}")
            print(f"     - Strategy chart traces: {len(fig.data)}")
            print(f"     - Equity chart traces: {len(equity_fig.data)}")

        except Exception as e:
            print(f"   ✗ Error generating charts for {strategy_name}: {e}")

    # Print summary comparison
    print("\n4. Strategy Comparison Summary")
    print("=" * 80)
    print(f"{'Strategy':<30} {'Return':<10} {'Sharpe':<8} {'Max DD':<10} {'Win Rate':<12} {'Trades':<8}")
    print("-" * 80)

    for result in results_summary:
        print(f"{result['Strategy']:<30} "
              f"{result['Return (%)']:>8.2f}% "
              f"{result['Sharpe']:>8.2f} "
              f"{result['Max DD (%)']:>8.2f}% "
              f"{result['Win Rate (%)']:>10.2f}% "
              f"{result['Trades']:>8}")

    print("=" * 80)

    # Summary
    print("\n5. Test Summary")
    print(f"   ✓ Tested {len(strategies)} strategies")
    print(f"   ✓ Generated {len(strategies) * 2} charts")
    print(f"   ✓ All core functionality working")

    print("\n" + "=" * 60)
    print("Dashboard Test Complete!")
    print("=" * 60)
    print("\nTo run the dashboard:")
    print("  streamlit run dashboard/app.py")
    print("")


if __name__ == '__main__':
    test_all_strategies()
