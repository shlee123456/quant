"""
End-to-end tests for paper trading functionality

Tests the complete paper trading workflow:
1. Simulation data generation
2. Strategy execution
3. Order generation
4. Balance updates
5. Trade tracking
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from trading_bot.paper_trader import PaperTrader
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.data_handler import DataHandler


class TestPaperTradingE2E:
    """End-to-end tests for paper trading"""

    @pytest.fixture
    def simulation_data(self):
        """Generate simulation data for testing"""
        generator = SimulationDataGenerator(seed=42)
        return generator.generate_ohlcv(
            initial_price=50000.0,
            periods=200,
            drift=0.001,
            volatility=0.02
        )

    @pytest.fixture
    def trending_data(self):
        """Generate trending data with clear buy/sell signals"""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')

        # Create data with clear trend changes for MA crossover signals
        prices = np.concatenate([
            np.linspace(100, 80, 25),   # Downtrend (MA death cross)
            np.linspace(80, 120, 50),   # Strong uptrend (MA golden cross)
            np.linspace(120, 100, 25)   # Downtrend again
        ])

        return pd.DataFrame({
            'open': prices,
            'high': prices + 2,
            'low': prices - 2,
            'close': prices,
            'volume': np.full(100, 10000)
        }, index=dates)

    @pytest.fixture
    def mock_data_handler(self, trending_data):
        """Create a mock DataHandler that returns simulation data"""
        handler = Mock(spec=DataHandler)
        handler.fetch_ohlcv.return_value = trending_data
        return handler

    def test_paper_trader_initialization(self):
        """Test paper trader initializes correctly"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        data_handler = Mock(spec=DataHandler)

        trader = PaperTrader(
            strategy=strategy,
            data_handler=data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        assert trader.initial_capital == 10000.0
        assert trader.capital == 10000.0
        assert trader.position == 0
        assert trader.entry_price == 0
        assert trader.last_signal == 0
        assert trader.trades == []
        assert trader.equity_history == []
        assert trader.is_running is False

    def test_buy_order_execution(self, mock_data_handler):
        """Test buy order creates correct position and updates capital"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        # Execute buy at $100
        buy_price = 100.0
        buy_time = datetime(2024, 1, 1, 12, 0)
        trader.execute_buy(buy_price, buy_time)

        # Check position and capital
        trade_capital = 10000.0 * 0.95  # $9500
        expected_position = trade_capital / buy_price * (1 - 0.001)  # 94.905
        expected_capital = 10000.0 - trade_capital  # $500

        assert trader.position == pytest.approx(expected_position, rel=1e-4)
        assert trader.capital == pytest.approx(expected_capital, rel=1e-4)
        assert trader.entry_price == buy_price

        # Check trade was recorded
        assert len(trader.trades) == 1
        assert trader.trades[0]['type'] == 'BUY'
        assert trader.trades[0]['price'] == buy_price
        assert trader.trades[0]['size'] == pytest.approx(expected_position, rel=1e-4)

    def test_sell_order_execution(self, mock_data_handler):
        """Test sell order closes position and calculates P&L"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        # First buy at $100
        buy_price = 100.0
        trader.execute_buy(buy_price, datetime(2024, 1, 1, 12, 0))

        # Record position before sell
        position_before_sell = trader.position

        # Then sell at $110 (10% profit)
        sell_price = 110.0
        sell_time = datetime(2024, 1, 1, 18, 0)
        trader.execute_sell(sell_price, sell_time)

        # Check position closed
        assert trader.position == 0
        assert trader.entry_price == 0

        # Check capital includes profit
        # Sale proceeds = position * sell_price * (1 - commission)
        sale_proceeds = position_before_sell * sell_price * (1 - 0.001)
        expected_capital = 500.0 + sale_proceeds  # Remaining capital + sale proceeds

        assert trader.capital == pytest.approx(expected_capital, rel=1e-3)

        # Check trade was recorded with P&L
        assert len(trader.trades) == 2
        sell_trade = trader.trades[1]
        assert sell_trade['type'] == 'SELL'
        assert sell_trade['price'] == sell_price
        assert 'pnl' in sell_trade
        assert 'pnl_pct' in sell_trade
        assert sell_trade['pnl'] > 0  # Profitable trade

    def test_full_trading_cycle(self, mock_data_handler, trending_data):
        """Test complete trading cycle: data → signal → order → balance update"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        initial_capital = trader.capital

        # Execute one update cycle (should trigger signals on trending data)
        trader.update('BTC/USDT', '1h')

        # Should have recorded equity history
        assert len(trader.equity_history) > 0

        # Equity history should track portfolio value
        equity_record = trader.equity_history[-1]
        assert 'timestamp' in equity_record
        assert 'equity' in equity_record
        assert 'price' in equity_record
        assert 'position' in equity_record

        # Get portfolio value
        current_price = trending_data.iloc[-1]['close']
        portfolio_value = trader.get_portfolio_value(current_price)

        # Portfolio value should equal capital + position value
        if trader.position > 0:
            expected_value = trader.capital + (trader.position * current_price)
        else:
            expected_value = trader.capital

        assert portfolio_value == pytest.approx(expected_value, rel=1e-6)

    def test_multiple_trading_cycles(self, mock_data_handler, trending_data):
        """Test multiple update cycles execute trades correctly"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        # Simulate multiple updates (each update gets full data from handler)
        for i in range(5):
            trader.update('BTC/USDT', '1h')

        # Should have equity history for each update
        assert len(trader.equity_history) == 5

        # Each equity record should have all required fields
        for record in trader.equity_history:
            assert 'timestamp' in record
            assert 'equity' in record
            assert 'price' in record
            assert 'position' in record

    def test_no_duplicate_trades_on_same_signal(self, mock_data_handler, trending_data):
        """Test that duplicate signals don't create duplicate trades"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.001
        )

        # Execute first update
        trader.update('BTC/USDT', '1h')
        trades_after_first = len(trader.trades)

        # Execute second update with same data (should have same signal)
        trader.update('BTC/USDT', '1h')
        trades_after_second = len(trader.trades)

        # Should not create duplicate trades if signal hasn't changed
        # (Only new signals should create trades)
        assert trades_after_second == trades_after_first

    def test_portfolio_value_calculation(self, mock_data_handler):
        """Test portfolio value calculation with and without position"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0
        )

        # Test with no position (flat)
        assert trader.get_portfolio_value(100.0) == 10000.0

        # Execute buy
        trader.execute_buy(100.0, datetime.now())

        # Test with position at same price
        portfolio_at_entry = trader.get_portfolio_value(100.0)
        assert portfolio_at_entry == pytest.approx(10000.0, rel=0.01)  # ~initial (minus commission)

        # Test with position at higher price
        portfolio_at_profit = trader.get_portfolio_value(110.0)
        assert portfolio_at_profit > 10000.0  # Should be profitable

        # Test with position at lower price
        portfolio_at_loss = trader.get_portfolio_value(90.0)
        assert portfolio_at_loss < 10000.0  # Should be at loss

    def test_trade_dataframe_export(self, mock_data_handler, trending_data):
        """Test exporting trades to DataFrame"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0
        )

        # Execute some updates
        for _ in range(3):
            trader.update('BTC/USDT', '1h')

        # Get trades DataFrame
        trades_df = trader.get_trades_df()

        # Should be a DataFrame
        assert isinstance(trades_df, pd.DataFrame)

        # If trades exist, check structure
        if len(trader.trades) > 0:
            assert 'type' in trades_df.columns
            assert 'price' in trades_df.columns
            assert 'size' in trades_df.columns
            assert 'timestamp' in trades_df.columns

    def test_equity_dataframe_export(self, mock_data_handler, trending_data):
        """Test exporting equity history to DataFrame"""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0
        )

        # Execute some updates
        for _ in range(3):
            trader.update('BTC/USDT', '1h')

        # Get equity DataFrame
        equity_df = trader.get_equity_df()

        # Should be a DataFrame
        assert isinstance(equity_df, pd.DataFrame)

        # Should have records
        assert len(equity_df) == 3

        # Check structure
        assert 'timestamp' in equity_df.columns
        assert 'equity' in equity_df.columns
        assert 'price' in equity_df.columns
        assert 'position' in equity_df.columns

    def test_rsi_strategy_integration(self, simulation_data):
        """Test paper trading with RSI strategy"""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)

        # Create mock handler that returns simulation data
        mock_handler = Mock(spec=DataHandler)
        mock_handler.fetch_ohlcv.return_value = simulation_data

        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_handler,
            initial_capital=10000.0
        )

        # Execute update
        trader.update('BTC/USDT', '1h')

        # Should work without errors
        assert len(trader.equity_history) > 0

    def test_macd_strategy_integration(self, simulation_data):
        """Test paper trading with MACD strategy"""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)

        # Create mock handler that returns simulation data
        mock_handler = Mock(spec=DataHandler)
        mock_handler.fetch_ohlcv.return_value = simulation_data

        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_handler,
            initial_capital=10000.0
        )

        # Execute update
        trader.update('BTC/USDT', '1h')

        # Should work without errors
        assert len(trader.equity_history) > 0

    def test_empty_data_handling(self, mock_data_handler):
        """Test paper trader handles empty data gracefully"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)

        # Mock handler returns empty DataFrame
        empty_handler = Mock(spec=DataHandler)
        empty_handler.fetch_ohlcv.return_value = pd.DataFrame()

        trader = PaperTrader(
            strategy=strategy,
            data_handler=empty_handler,
            initial_capital=10000.0
        )

        # Should not raise error
        trader.update('BTC/USDT', '1h')

        # Should not create equity history for empty data
        assert len(trader.equity_history) == 0

    def test_commission_impact(self, mock_data_handler):
        """Test that commission reduces capital correctly"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0,
            position_size=0.95,
            commission=0.01  # 1% commission
        )

        # Buy at $100
        buy_price = 100.0
        trader.execute_buy(buy_price, datetime.now())

        # With 1% commission, position should be 1% smaller
        trade_capital = 9500.0
        expected_position = trade_capital / buy_price * 0.99  # 99% after commission

        assert trader.position == pytest.approx(expected_position, rel=1e-4)

        # Sell at same price (should result in loss due to commission)
        initial_position = trader.position
        trader.execute_sell(buy_price, datetime.now())

        # Capital should be less than initial due to round-trip commission
        assert trader.capital < 10000.0

    def test_skip_buy_when_already_in_position(self, mock_data_handler):
        """Test that BUY signal is ignored when already holding position"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0
        )

        # First buy
        trader.execute_buy(100.0, datetime.now())
        trades_after_first_buy = len(trader.trades)
        position_after_first_buy = trader.position

        # Try to buy again (should be ignored)
        trader.execute_buy(100.0, datetime.now())

        # Should not create new trade
        assert len(trader.trades) == trades_after_first_buy

        # Position should not change
        assert trader.position == position_after_first_buy

    def test_skip_sell_when_no_position(self, mock_data_handler):
        """Test that SELL signal is ignored when not holding position"""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
        trader = PaperTrader(
            strategy=strategy,
            data_handler=mock_data_handler,
            initial_capital=10000.0
        )

        # Try to sell without position (should be ignored)
        trader.execute_sell(100.0, datetime.now())

        # Should not create trade
        assert len(trader.trades) == 0

        # Capital should not change
        assert trader.capital == 10000.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
