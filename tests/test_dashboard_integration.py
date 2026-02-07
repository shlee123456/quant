"""
Integration tests for the enhanced dashboard
Tests strategy integration and data flow
"""

import pytest
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy
from trading_bot.backtester import Backtester
from trading_bot.simulation_data import SimulationDataGenerator
from dashboard.charts import ChartGenerator


class TestDashboardIntegration:
    """Test dashboard integration with strategies"""

    @pytest.fixture
    def sample_data(self):
        """Generate sample OHLCV data for testing"""
        generator = SimulationDataGenerator(seed=42)
        return generator.generate_ohlcv(periods=500)

    @pytest.fixture
    def chart_generator(self):
        """Create chart generator instance"""
        return ChartGenerator()

    def test_ma_strategy_backtest(self, sample_data):
        """Test Moving Average strategy backtest"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)

        results = backtester.run(sample_data)

        assert 'total_return' in results
        assert 'sharpe_ratio' in results
        assert 'max_drawdown' in results
        assert 'win_rate' in results
        assert 'total_trades' in results
        assert results['final_capital'] > 0

    def test_rsi_strategy_backtest(self, sample_data):
        """Test RSI strategy backtest"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)

        results = backtester.run(sample_data)

        assert 'total_return' in results
        assert 'sharpe_ratio' in results
        assert 'max_drawdown' in results
        assert 'win_rate' in results
        assert 'total_trades' in results

    def test_macd_strategy_backtest(self, sample_data):
        """Test MACD strategy backtest"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        backtester = Backtester(strategy=strategy, initial_capital=10000)

        results = backtester.run(sample_data)

        assert 'total_return' in results
        assert 'sharpe_ratio' in results
        assert 'max_drawdown' in results
        assert 'win_rate' in results
        assert 'total_trades' in results

    def test_bollinger_strategy_backtest(self, sample_data):
        """Test Bollinger Bands strategy backtest"""
        strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        backtester = Backtester(strategy=strategy, initial_capital=10000)

        results = backtester.run(sample_data)

        assert 'total_return' in results
        assert 'sharpe_ratio' in results
        assert 'max_drawdown' in results
        assert 'win_rate' in results
        assert 'total_trades' in results

    def test_strategy_comparison(self, sample_data):
        """Test comparing multiple strategies"""
        strategies = {
            'MA Crossover': MovingAverageCrossover(fast_period=10, slow_period=30),
            'RSI': RSIStrategy(period=14, overbought=70, oversold=30),
            'MACD': MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
            'Bollinger': BollingerBandsStrategy(period=20, num_std=2.0)
        }

        comparison_results = []

        for strategy_name, strategy in strategies.items():
            backtester = Backtester(strategy=strategy, initial_capital=10000)
            results = backtester.run(sample_data)

            comparison_results.append({
                'Strategy': strategy_name,
                'Total Return (%)': results['total_return'],
                'Sharpe Ratio': results['sharpe_ratio'],
                'Max Drawdown (%)': results['max_drawdown'],
                'Win Rate (%)': results['win_rate'],
                'Total Trades': results['total_trades']
            })

        df_comparison = pd.DataFrame(comparison_results)

        # Verify all strategies were tested
        assert len(df_comparison) == 4
        assert all(df_comparison['Total Trades'] >= 0)

    def test_ma_chart_generation(self, sample_data, chart_generator):
        """Test MA strategy chart generation"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        # Generate chart
        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'Moving Average Crossover'
        )

        assert fig is not None
        assert len(fig.data) > 0  # Should have traces

    def test_rsi_chart_generation(self, sample_data, chart_generator):
        """Test RSI strategy chart generation"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        # Generate chart
        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'RSI Strategy'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_macd_chart_generation(self, sample_data, chart_generator):
        """Test MACD strategy chart generation"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        # Generate chart
        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'MACD Strategy'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_bollinger_chart_generation(self, sample_data, chart_generator):
        """Test Bollinger Bands strategy chart generation"""
        strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        # Generate chart
        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'Bollinger Bands'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_equity_curve_chart(self, sample_data, chart_generator):
        """Test equity curve chart generation"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        equity_df = backtester.get_equity_curve_df()
        fig = chart_generator.plot_equity_curve(equity_df)

        assert fig is not None
        assert len(fig.data) > 0
        assert 'timestamp' in equity_df.columns
        assert 'equity' in equity_df.columns

    def test_indicator_calculations(self, sample_data):
        """Test that all strategies calculate indicators correctly"""
        strategies = [
            MovingAverageCrossover(fast_period=10, slow_period=30),
            RSIStrategy(period=14, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
            BollingerBandsStrategy(period=20, num_std=2.0)
        ]

        for strategy in strategies:
            data_with_indicators = strategy.calculate_indicators(sample_data)

            # All strategies should have these columns
            assert 'signal' in data_with_indicators.columns
            assert 'position' in data_with_indicators.columns

            # Check for strategy-specific indicators
            if isinstance(strategy, MovingAverageCrossover):
                assert 'fast_ma' in data_with_indicators.columns
                assert 'slow_ma' in data_with_indicators.columns

            elif isinstance(strategy, RSIStrategy):
                assert 'rsi' in data_with_indicators.columns

            elif isinstance(strategy, MACDStrategy):
                assert 'macd_line' in data_with_indicators.columns
                assert 'signal_line' in data_with_indicators.columns
                assert 'macd_histogram' in data_with_indicators.columns

            elif isinstance(strategy, BollingerBandsStrategy):
                assert 'bb_upper' in data_with_indicators.columns
                assert 'bb_middle' in data_with_indicators.columns
                assert 'bb_lower' in data_with_indicators.columns

    def test_signal_generation(self, sample_data):
        """Test that all strategies generate valid signals"""
        strategies = [
            MovingAverageCrossover(fast_period=10, slow_period=30),
            RSIStrategy(period=14, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
            BollingerBandsStrategy(period=20, num_std=2.0)
        ]

        for strategy in strategies:
            signal, info = strategy.get_current_signal(sample_data)

            # Signal should be -1, 0, or 1
            assert signal in [-1, 0, 1]

            # Info should be a dictionary
            assert isinstance(info, dict)

            # Info should contain timestamp and close price
            assert 'timestamp' in info or 'close' in info

    def test_minimal_data_handling(self):
        """Test that dashboard can handle minimal valid data"""
        # Create minimal valid OHLCV data (100 rows for indicator warm-up)
        generator = SimulationDataGenerator(seed=42)
        minimal_df = generator.generate_ohlcv(periods=100)

        strategies = [
            MovingAverageCrossover(fast_period=10, slow_period=30),
            RSIStrategy(period=14, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
            BollingerBandsStrategy(period=20, num_std=2.0)
        ]

        for strategy in strategies:
            # Should handle minimal data without errors
            data_with_indicators = strategy.calculate_indicators(minimal_df)
            assert not data_with_indicators.empty

            signal, info = strategy.get_current_signal(minimal_df)
            assert signal in [-1, 0, 1]
            assert isinstance(info, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
