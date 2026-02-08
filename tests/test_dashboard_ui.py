"""
Dashboard UI Tests

Tests dashboard tab functionality, chart generation, and error handling.
"""

import pytest
import pandas as pd
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies import RSIStrategy, MACDStrategy, BollingerBandsStrategy, StochasticStrategy
from trading_bot.backtester import Backtester
from dashboard.charts import ChartGenerator
from dashboard.error_handler import (
    ErrorType,
    identify_error_type,
    display_error,
    handle_kis_broker_error
)


class TestDashboardTabs:
    """Test dashboard tab loading and functionality"""

    @pytest.fixture
    def sample_data(self):
        """Generate sample OHLCV data"""
        generator = SimulationDataGenerator(seed=42)
        return generator.generate_ohlcv(periods=500)

    @pytest.fixture
    def sample_backtest_results(self, sample_data):
        """Run a sample backtest and return results"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        return backtester.run(sample_data), backtester

    def test_strategy_comparison_tab_data_structure(self, sample_data):
        """Test Strategy Comparison tab data processing"""
        # Simulate multiple strategy comparison
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

        # Verify DataFrame structure
        assert len(df_comparison) == 4
        assert 'Strategy' in df_comparison.columns
        assert 'Total Return (%)' in df_comparison.columns
        assert 'Sharpe Ratio' in df_comparison.columns
        assert 'Max Drawdown (%)' in df_comparison.columns
        assert 'Win Rate (%)' in df_comparison.columns
        assert 'Total Trades' in df_comparison.columns

    def test_backtesting_tab_results(self, sample_data):
        """Test Backtesting tab results structure"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        results = backtester.run(sample_data)

        # Verify all required metrics are present
        required_metrics = [
            'total_return',
            'sharpe_ratio',
            'max_drawdown',
            'win_rate',
            'total_trades',
            'final_capital'
        ]

        for metric in required_metrics:
            assert metric in results

        # Verify metric types
        assert isinstance(results['total_return'], (int, float))
        assert isinstance(results['sharpe_ratio'], (int, float))
        assert isinstance(results['max_drawdown'], (int, float))
        assert isinstance(results['win_rate'], (int, float))
        assert isinstance(results['total_trades'], int)
        assert isinstance(results['final_capital'], (int, float))

    def test_live_monitor_tab_signal_generation(self, sample_data):
        """Test Live Monitor tab signal generation"""
        strategies = [
            MovingAverageCrossover(fast_period=10, slow_period=30),
            RSIStrategy(period=14, overbought=70, oversold=30),
            MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
            BollingerBandsStrategy(period=20, num_std=2.0),
            StochasticStrategy(k_period=14, d_period=3)
        ]

        for strategy in strategies:
            # Get current signal
            signal, info = strategy.get_current_signal(sample_data)

            # Verify signal is valid
            assert signal in [-1, 0, 1], f"Invalid signal {signal} from {strategy.name}"

            # Verify info dictionary
            assert isinstance(info, dict)
            assert len(info) > 0

    def test_realtime_quotes_tab_data_structure(self):
        """Test Real-time Quotes tab expected data structure"""
        # Simulate KIS broker ticker response
        mock_ticker = {
            'symbol': 'AAPL',
            'last': 150.25,
            'open': 149.50,
            'high': 151.00,
            'low': 149.00,
            'volume': 50000000,
            'change': 0.75,
            'rate': 0.50,
            'timestamp': '2024-01-01 10:30:00'
        }

        # Verify required fields
        required_fields = ['symbol', 'last', 'open', 'high', 'low', 'volume']
        for field in required_fields:
            assert field in mock_ticker

        # Verify data types
        assert isinstance(mock_ticker['symbol'], str)
        assert isinstance(mock_ticker['last'], (int, float))
        assert isinstance(mock_ticker['open'], (int, float))
        assert isinstance(mock_ticker['high'], (int, float))
        assert isinstance(mock_ticker['low'], (int, float))
        assert isinstance(mock_ticker['volume'], (int, float))


class TestChartGeneration:
    """Test ChartGenerator methods"""

    @pytest.fixture
    def chart_generator(self):
        """Create ChartGenerator instance"""
        return ChartGenerator()

    @pytest.fixture
    def sample_data(self):
        """Generate sample data"""
        generator = SimulationDataGenerator(seed=42)
        return generator.generate_ohlcv(periods=200)

    @pytest.fixture
    def sample_backtest_data(self, sample_data):
        """Generate sample backtest data"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()
        equity_df = backtester.get_equity_curve_df()

        return data_with_indicators, trades_df, equity_df

    def test_plot_equity_curve(self, chart_generator, sample_backtest_data):
        """Test equity curve chart generation"""
        _, _, equity_df = sample_backtest_data

        fig = chart_generator.plot_equity_curve(equity_df)

        assert fig is not None
        assert len(fig.data) > 0
        assert fig.layout.title.text is not None or fig.layout.xaxis.title.text is not None

    def test_plot_price_with_signals(self, chart_generator, sample_backtest_data):
        """Test price with signals chart generation"""
        data_with_indicators, trades_df, _ = sample_backtest_data

        fig = chart_generator.plot_price_with_signals(data_with_indicators, trades_df)

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_price_with_ma(self, chart_generator, sample_data):
        """Test price with moving average chart generation"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        data_with_ma = strategy.calculate_indicators(sample_data)

        fig = chart_generator.plot_price_with_ma(data_with_ma)

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_drawdown(self, chart_generator, sample_backtest_data):
        """Test drawdown chart generation"""
        _, _, equity_df = sample_backtest_data

        fig = chart_generator.plot_drawdown(equity_df)

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_trade_analysis(self, chart_generator, sample_backtest_data):
        """Test trade analysis chart generation"""
        _, trades_df, _ = sample_backtest_data

        if not trades_df.empty:
            fig = chart_generator.plot_trade_analysis(trades_df)

            assert fig is not None
            assert len(fig.data) > 0

    def test_plot_strategy_chart_ma(self, chart_generator, sample_data):
        """Test Moving Average strategy chart"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'Moving Average Crossover'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_strategy_chart_rsi(self, chart_generator, sample_data):
        """Test RSI strategy chart"""
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'RSI Strategy'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_strategy_chart_macd(self, chart_generator, sample_data):
        """Test MACD strategy chart"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'MACD Strategy'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_strategy_chart_bollinger(self, chart_generator, sample_data):
        """Test Bollinger Bands strategy chart"""
        strategy = BollingerBandsStrategy(period=20, num_std=2.0)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'Bollinger Bands'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_plot_strategy_chart_stochastic(self, chart_generator, sample_data):
        """Test Stochastic strategy chart"""
        strategy = StochasticStrategy(k_period=14, d_period=3)
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        backtester.run(sample_data)

        data_with_indicators = strategy.calculate_indicators(sample_data)
        trades_df = backtester.get_trades_df()

        fig = chart_generator.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'Stochastic Oscillator'
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_chart_with_empty_trades(self, chart_generator, sample_data):
        """Test chart generation with no trades"""
        strategy = MovingAverageCrossover(fast_period=40, slow_period=50)
        data_with_indicators = strategy.calculate_indicators(sample_data)
        empty_trades = pd.DataFrame()

        # Should handle empty trades gracefully
        fig = chart_generator.plot_price_with_signals(data_with_indicators, empty_trades)

        assert fig is not None
        assert len(fig.data) > 0


class TestErrorHandler:
    """Test error handling functionality"""

    def test_identify_rate_limit_error(self):
        """Test rate limit error identification"""
        error = Exception("rate limit exceeded")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.RATE_LIMIT

        error = Exception("Too many requests")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.RATE_LIMIT

        error = Exception("HTTP 429 error")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.RATE_LIMIT

    def test_identify_network_error(self):
        """Test network error identification"""
        error = Exception("connection timeout")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.NETWORK

        error = Exception("network unreachable")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.NETWORK

    def test_identify_authentication_error(self):
        """Test authentication error identification"""
        error = Exception("unauthorized access")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.AUTHENTICATION

        error = Exception("HTTP 401 forbidden")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.AUTHENTICATION

        error = Exception("invalid key")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.AUTHENTICATION

    def test_identify_invalid_symbol_error(self):
        """Test invalid symbol error identification"""
        error = Exception("invalid symbol XYZ")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.INVALID_SYMBOL

        error = Exception("symbol not found")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.INVALID_SYMBOL

    def test_identify_market_closed_error(self):
        """Test market closed error identification"""
        error = Exception("market closed")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.MARKET_CLOSED

        error = Exception("outside trading hours")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.MARKET_CLOSED

    def test_identify_generic_error(self):
        """Test generic error identification"""
        error = Exception("some unknown error")
        error_type = identify_error_type(error)
        assert error_type == ErrorType.GENERIC

    @patch('dashboard.error_handler.st')
    def test_display_error_rate_limit(self, mock_st):
        """Test display_error for rate limit"""
        error = Exception("rate limit exceeded")

        # Mock streamlit components
        mock_st.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
        mock_st.error = MagicMock()
        mock_st.markdown = MagicMock()

        display_error(error, lang='en', context='fetching quote')

        # Verify st.error was called
        assert mock_st.error.called

    @patch('dashboard.error_handler.st')
    def test_display_error_network(self, mock_st):
        """Test display_error for network error"""
        error = Exception("connection timeout")

        # Mock streamlit components
        mock_st.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
        mock_st.error = MagicMock()
        mock_st.markdown = MagicMock()

        display_error(error, lang='en')

        # Verify st.error was called
        assert mock_st.error.called

    @patch('dashboard.error_handler.st')
    def test_handle_kis_broker_error(self, mock_st):
        """Test KIS broker error handler"""
        error = Exception("invalid key")

        # Mock streamlit components
        mock_st.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
        mock_st.error = MagicMock()
        mock_st.markdown = MagicMock()

        handle_kis_broker_error(error, lang='en', symbol='AAPL')

        # Verify st.error was called
        assert mock_st.error.called


class TestDashboardDataFlow:
    """Test data flow through dashboard components"""

    @pytest.fixture
    def sample_data(self):
        """Generate sample data"""
        generator = SimulationDataGenerator(seed=42)
        return generator.generate_ohlcv(periods=300)

    def test_complete_backtest_workflow(self, sample_data):
        """Test complete backtest workflow from strategy to chart"""
        # 1. Initialize strategy
        strategy = RSIStrategy(period=14, overbought=70, oversold=30)

        # 2. Calculate indicators
        data_with_indicators = strategy.calculate_indicators(sample_data)
        assert 'rsi' in data_with_indicators.columns
        assert 'signal' in data_with_indicators.columns

        # 3. Run backtest
        backtester = Backtester(strategy=strategy, initial_capital=10000)
        results = backtester.run(sample_data)
        assert 'total_return' in results

        # 4. Get trade data
        trades_df = backtester.get_trades_df()
        assert isinstance(trades_df, pd.DataFrame)

        # 5. Generate charts
        chart_gen = ChartGenerator()
        fig = chart_gen.plot_strategy_chart(
            data_with_indicators,
            trades_df,
            'RSI Strategy'
        )
        assert fig is not None

    def test_strategy_comparison_workflow(self, sample_data):
        """Test strategy comparison workflow"""
        strategies = {
            'MA': MovingAverageCrossover(fast_period=10, slow_period=30),
            'RSI': RSIStrategy(period=14),
            'MACD': MACDStrategy()
        }

        results_list = []
        for name, strategy in strategies.items():
            backtester = Backtester(strategy=strategy, initial_capital=10000)
            results = backtester.run(sample_data)
            results_list.append({
                'strategy': name,
                'return': results['total_return'],
                'sharpe': results['sharpe_ratio']
            })

        # Verify all strategies completed
        assert len(results_list) == 3

        # Verify all have valid results
        for result in results_list:
            assert isinstance(result['return'], (int, float))
            assert isinstance(result['sharpe'], (int, float))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
