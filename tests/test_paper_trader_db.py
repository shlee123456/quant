"""
Unit tests for PaperTrader database integration
"""

import pytest
import os
import tempfile
import pandas as pd
from datetime import datetime
from trading_bot.paper_trader import PaperTrader
from trading_bot.database import TradingDatabase
from trading_bot.strategies import RSIStrategy


class MockBroker:
    """Mock broker for testing"""

    def fetch_ticker(self, symbol, **kwargs):
        """Mock fetch_ticker"""
        return {
            'symbol': symbol,
            'last': 150.0,
            'open': 149.0,
            'high': 151.0,
            'low': 148.0,
            'volume': 1000000,
            'change': 1.0,
            'rate': 0.67
        }

    def fetch_ohlcv(self, symbol, timeframe='1d', limit=100, **kwargs):
        """Mock fetch_ohlcv"""
        # Generate simple OHLCV data
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')
        data = pd.DataFrame({
            'open': [150.0] * limit,
            'high': [152.0] * limit,
            'low': [148.0] * limit,
            'close': [150.0 + i * 0.5 for i in range(limit)],
            'volume': [1000000] * limit
        }, index=dates)

        return data


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_paper_trading.db')
    db = TradingDatabase(db_path=db_path)

    yield db

    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


@pytest.fixture
def paper_trader_with_db(temp_db):
    """Create PaperTrader with database integration"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    broker = MockBroker()

    trader = PaperTrader(
        strategy=strategy,
        symbols=['AAPL'],
        broker=broker,
        initial_capital=10000.0,
        position_size=0.95,
        db=temp_db
    )

    yield trader

    # Stop trader if running
    if trader.is_running:
        trader.stop()


def test_paper_trader_database_integration(paper_trader_with_db):
    """Test that PaperTrader integrates with database"""
    trader = paper_trader_with_db

    # Start paper trading
    trader.start()

    # Verify session was created
    assert trader.session_id is not None
    assert 'RSI' in trader.session_id  # RSIStrategy name is "RSI_{period}_{oversold}_{overbought}"


def test_session_creation_on_start(paper_trader_with_db):
    """Test that session is created when trading starts"""
    trader = paper_trader_with_db

    # No session before start
    assert trader.session_id is None

    # Start trading
    trader.start()

    # Session should be created
    assert trader.session_id is not None

    # Verify in database
    summary = trader.db.get_session_summary(trader.session_id)
    assert summary is not None
    assert summary['strategy_name'] == 'RSI_14_30_70'  # RSIStrategy name format
    assert summary['initial_capital'] == 10000.0


def test_trade_logging_to_database(paper_trader_with_db):
    """Test that trades are logged to database"""
    trader = paper_trader_with_db
    trader.start()

    # Execute a buy trade
    trader.execute_buy('AAPL', 150.0, datetime.now())

    # Verify trade was logged
    trades = trader.db.get_session_trades(trader.session_id)
    assert len(trades) >= 1

    # Check trade details
    buy_trade = trades[0]
    assert buy_trade['symbol'] == 'AAPL'
    assert buy_trade['type'] == 'BUY'
    assert buy_trade['price'] == 150.0


def test_signal_logging_to_database(temp_db):
    """Test that signals are logged to database"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    broker = MockBroker()

    trader = PaperTrader(
        strategy=strategy,
        symbols=['AAPL'],
        broker=broker,
        initial_capital=10000.0,
        db=temp_db
    )

    trader.start()

    # Simulate update which should generate signals
    # Note: update() method uses data_handler, not broker
    # So we'll use _realtime_iteration pattern manually

    # For testing, we'll manually log a signal
    if trader.db and trader.session_id:
        signal_data = {
            'symbol': 'AAPL',
            'timestamp': datetime.now(),
            'signal': 1,
            'indicator_values': {'rsi': 65.5, 'close': 150.0},
            'market_price': 150.0,
            'executed': False
        }
        trader.db.log_signal(trader.session_id, signal_data)

    # Verify signal was logged
    signals = temp_db.get_session_signals(trader.session_id)
    assert len(signals) >= 1
    assert signals[0]['symbol'] == 'AAPL'


def test_portfolio_snapshot_logging(paper_trader_with_db):
    """Test that portfolio snapshots are logged"""
    trader = paper_trader_with_db
    trader.start()

    # Take a portfolio snapshot
    current_prices = {'AAPL': 150.0}
    portfolio_value = trader.get_portfolio_value(current_prices)
    trader._take_portfolio_snapshot(datetime.now(), portfolio_value, current_prices)

    # Verify snapshot was logged
    snapshots = trader.db.get_session_snapshots(trader.session_id)
    assert len(snapshots) >= 1

    snapshot = snapshots[0]
    assert snapshot['total_value'] == portfolio_value
    assert snapshot['cash'] == trader.capital


def test_session_finalization_on_stop(paper_trader_with_db):
    """Test that session is finalized when trading stops"""
    trader = paper_trader_with_db
    trader.start()

    # Execute some trades
    trader.execute_buy('AAPL', 150.0, datetime.now())
    trader.execute_sell('AAPL', 155.0, datetime.now())

    # Stop trading
    trader.stop()

    # Verify session was finalized
    summary = trader.db.get_session_summary(trader.session_id)
    assert summary['status'] == 'completed'
    assert summary['final_capital'] is not None
    assert summary['total_return'] is not None


def test_multi_symbol_tracking(temp_db):
    """Test tracking multiple symbols in database"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    broker = MockBroker()

    symbols = ['AAPL', 'MSFT', 'GOOGL']
    trader = PaperTrader(
        strategy=strategy,
        symbols=symbols,
        broker=broker,
        initial_capital=10000.0,
        db=temp_db
    )

    trader.start()

    # Execute trades for different symbols
    trader.execute_buy('AAPL', 150.0, datetime.now())
    trader.execute_buy('MSFT', 300.0, datetime.now())
    trader.execute_buy('GOOGL', 2800.0, datetime.now())

    # Verify all trades were logged
    trades = temp_db.get_session_trades(trader.session_id)
    assert len(trades) == 3

    # Verify different symbols
    symbols_traded = {t['symbol'] for t in trades}
    assert 'AAPL' in symbols_traded
    assert 'MSFT' in symbols_traded
    assert 'GOOGL' in symbols_traded


def test_multi_symbol_positions_in_snapshot(temp_db):
    """Test that multi-symbol positions are correctly stored in snapshots"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    broker = MockBroker()

    symbols = ['AAPL', 'MSFT']
    trader = PaperTrader(
        strategy=strategy,
        symbols=symbols,
        broker=broker,
        initial_capital=10000.0,
        db=temp_db
    )

    trader.start()

    # Execute trades
    trader.execute_buy('AAPL', 150.0, datetime.now())
    trader.execute_buy('MSFT', 300.0, datetime.now())

    # Take snapshot
    current_prices = {'AAPL': 150.0, 'MSFT': 300.0}
    portfolio_value = trader.get_portfolio_value(current_prices)
    trader._take_portfolio_snapshot(datetime.now(), portfolio_value, current_prices)

    # Verify snapshot includes all positions
    snapshots = temp_db.get_session_snapshots(trader.session_id)
    assert len(snapshots) >= 1

    positions = snapshots[0]['positions']
    assert 'AAPL' in positions
    assert 'MSFT' in positions
    assert positions['AAPL'] > 0
    assert positions['MSFT'] > 0


def test_performance_metrics_calculation(paper_trader_with_db):
    """Test that performance metrics are calculated correctly"""
    trader = paper_trader_with_db
    trader.start()

    # Execute profitable trade
    trader.execute_buy('AAPL', 150.0, datetime.now())

    # Add some equity history for metrics calculation
    trader.equity_history.append({'equity': 10000.0, 'timestamp': datetime.now()})
    trader.equity_history.append({'equity': 10500.0, 'timestamp': datetime.now()})
    trader.equity_history.append({'equity': 11000.0, 'timestamp': datetime.now()})

    trader.execute_sell('AAPL', 160.0, datetime.now())

    # Stop and finalize
    trader.stop()

    # Verify metrics were calculated
    summary = trader.db.get_session_summary(trader.session_id)
    assert summary['sharpe_ratio'] is not None
    assert summary['max_drawdown'] is not None
    assert summary['win_rate'] is not None
