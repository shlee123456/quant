"""
Integration tests for real-time paper trading
"""

import pytest
import os
import tempfile
import pandas as pd
import time
import threading
from datetime import datetime
from trading_bot.paper_trader import PaperTrader
from trading_bot.database import TradingDatabase
from trading_bot.strategies import RSIStrategy, MACDStrategy


class MockBroker:
    """Mock broker for integration testing"""

    def __init__(self):
        self.call_count = 0
        self.symbols_fetched = []

    def fetch_ticker(self, symbol, **kwargs):
        """Mock fetch_ticker with varying prices"""
        self.call_count += 1
        self.symbols_fetched.append(symbol)

        # Simulate price movement
        base_price = 150.0
        price = base_price + (self.call_count % 10) * 0.5

        return {
            'symbol': symbol,
            'last': price,
            'open': price - 1.0,
            'high': price + 1.0,
            'low': price - 1.0,
            'volume': 1000000,
            'change': 0.5,
            'rate': 0.33
        }

    def fetch_ohlcv(self, symbol, timeframe='1d', limit=100, **kwargs):
        """Mock fetch_ohlcv with trending data"""
        dates = pd.date_range(end=datetime.now(), periods=limit, freq='D')

        # Create trending data for RSI to generate signals
        close_prices = []
        for i in range(limit):
            if i < 30:
                # Downtrend - should trigger oversold (BUY signal)
                price = 150.0 - i * 0.5
            elif i < 60:
                # Uptrend - should trigger overbought (SELL signal)
                price = 135.0 + (i - 30) * 0.7
            else:
                # Sideways with slight uptrend
                price = 156.0 + (i - 60) * 0.1
            close_prices.append(price)

        data = pd.DataFrame({
            'open': [p - 0.5 for p in close_prices],
            'high': [p + 1.0 for p in close_prices],
            'low': [p - 1.0 for p in close_prices],
            'close': close_prices,
            'volume': [1000000] * limit
        }, index=dates)

        return data


@pytest.fixture
def temp_db():
    """Create temporary database"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_integration.db')
    db = TradingDatabase(db_path=db_path)

    yield db

    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


@pytest.fixture
def paper_trader_realtime(temp_db):
    """Create PaperTrader for real-time testing"""
    strategy = RSIStrategy(period=14, overbought=70, oversold=30)
    broker = MockBroker()

    trader = PaperTrader(
        strategy=strategy,
        symbols=['AAPL', 'MSFT'],
        broker=broker,
        initial_capital=10000.0,
        position_size=0.5,  # Lower position size for multi-symbol
        db=temp_db
    )

    yield trader, broker

    if trader.is_running:
        trader.stop()


def test_run_realtime_with_mock_broker(paper_trader_realtime, temp_db):
    """Test PaperTrader.run_realtime() with mock broker"""
    trader, broker = paper_trader_realtime

    # Start in background thread
    trader.start()

    # Run for a short duration in thread
    def run_limited():
        # Run 3 iterations (3 seconds)
        for _ in range(3):
            if not trader.is_running:
                break
            trader._realtime_iteration('1d')
            time.sleep(1)
        trader.is_running = False

    thread = threading.Thread(target=run_limited, daemon=True)
    thread.start()
    thread.join(timeout=10)

    # Verify session was created
    assert trader.session_id is not None

    # Verify broker was called
    assert broker.call_count > 0

    # Verify data was logged
    snapshots = temp_db.get_session_snapshots(trader.session_id)
    assert len(snapshots) > 0

    trader.stop()


def test_multi_symbol_iteration(paper_trader_realtime, temp_db):
    """Test that run_realtime iterates through multiple symbols"""
    trader, broker = paper_trader_realtime

    trader.start()

    # Run one iteration manually
    trader._realtime_iteration('1d')

    # Verify both symbols were processed
    assert 'AAPL' in broker.symbols_fetched
    assert 'MSFT' in broker.symbols_fetched

    # Verify snapshot was taken
    snapshots = temp_db.get_session_snapshots(trader.session_id)
    assert len(snapshots) >= 1

    trader.stop()


def test_start_stop_control_flow(paper_trader_realtime):
    """Test start/stop control flow"""
    trader, _ = paper_trader_realtime

    # Initial state
    assert not trader.is_running
    assert trader.session_id is None

    # Start
    trader.start()
    assert trader.is_running
    assert trader.session_id is not None

    # Stop
    trader.stop()
    assert not trader.is_running


def test_database_logging_during_execution(paper_trader_realtime, temp_db):
    """Test that database logging happens during execution"""
    trader, broker = paper_trader_realtime

    trader.start()

    # Run multiple iterations
    for _ in range(3):
        trader._realtime_iteration('1d')
        time.sleep(0.1)

    # Verify session exists
    summary = temp_db.get_session_summary(trader.session_id)
    assert summary is not None
    assert summary['strategy_name'] == 'RSI_14_30_70'

    # Verify snapshots were logged
    snapshots = temp_db.get_session_snapshots(trader.session_id)
    assert len(snapshots) >= 3

    # Verify signals were logged (if any were generated)
    signals = temp_db.get_session_signals(trader.session_id)
    # Signals may or may not be generated depending on market conditions
    # Just verify the query works
    assert signals is not None

    trader.stop()


def test_portfolio_snapshot_creation(paper_trader_realtime, temp_db):
    """Test that portfolio snapshots are created correctly"""
    trader, _ = paper_trader_realtime

    trader.start()

    # Execute some trades
    trader.execute_buy('AAPL', 150.0, datetime.now())
    trader.execute_buy('MSFT', 300.0, datetime.now())

    # Take snapshot manually
    current_prices = {'AAPL': 151.0, 'MSFT': 305.0}
    portfolio_value = trader.get_portfolio_value(current_prices)
    trader._take_portfolio_snapshot(datetime.now(), portfolio_value, current_prices)

    # Verify snapshot
    snapshots = temp_db.get_session_snapshots(trader.session_id)
    assert len(snapshots) >= 1

    snapshot = snapshots[-1]
    assert snapshot['total_value'] > 0
    assert 'AAPL' in snapshot['positions']
    assert 'MSFT' in snapshot['positions']

    trader.stop()


def test_session_state_transitions(paper_trader_realtime, temp_db):
    """Test session state transitions (active -> completed)"""
    trader, _ = paper_trader_realtime

    trader.start()

    # Verify initial state
    summary = temp_db.get_session_summary(trader.session_id)
    assert summary['status'] == 'active'
    assert summary['final_capital'] is None

    # Execute some trades and add equity history
    trader.execute_buy('AAPL', 150.0, datetime.now())
    trader.equity_history.append({'equity': 10000.0, 'timestamp': datetime.now()})
    trader.equity_history.append({'equity': 10200.0, 'timestamp': datetime.now()})
    trader.execute_sell('AAPL', 155.0, datetime.now())

    # Stop trading
    trader.stop()

    # Verify final state
    summary = temp_db.get_session_summary(trader.session_id)
    assert summary['status'] == 'completed'
    assert summary['final_capital'] is not None
    assert summary['total_return'] is not None


def test_run_realtime_with_macd_strategy(temp_db):
    """Test run_realtime with different strategy (MACD)"""
    strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    broker = MockBroker()

    trader = PaperTrader(
        strategy=strategy,
        symbols=['AAPL'],
        broker=broker,
        initial_capital=10000.0,
        db=temp_db
    )

    trader.start()

    # Run one iteration
    trader._realtime_iteration('1d')

    # Verify session created with correct strategy
    summary = temp_db.get_session_summary(trader.session_id)
    assert 'MACD' in summary['strategy_name']

    trader.stop()


def test_error_handling_in_realtime_iteration(paper_trader_realtime):
    """Test error handling when broker fails"""
    trader, broker = paper_trader_realtime

    # Make broker raise error
    def failing_fetch(*args, **kwargs):
        raise Exception("Broker connection failed")

    original_fetch = broker.fetch_ticker
    broker.fetch_ticker = failing_fetch

    trader.start()

    # Run iteration - should handle error gracefully
    try:
        trader._realtime_iteration('1d')
        # Should not raise exception, just log error
    except Exception:
        pytest.fail("_realtime_iteration should handle broker errors gracefully")

    # Restore original
    broker.fetch_ticker = original_fetch

    trader.stop()


def test_position_tracking_across_iterations(paper_trader_realtime, temp_db):
    """Test that positions are tracked correctly across iterations"""
    trader, _ = paper_trader_realtime

    trader.start()

    # Execute buy
    trader.execute_buy('AAPL', 150.0, datetime.now())

    initial_position = trader.positions['AAPL']
    assert initial_position > 0

    # Run iteration
    trader._realtime_iteration('1d')

    # Position should be maintained
    assert trader.positions['AAPL'] == initial_position

    # Execute sell
    trader.execute_sell('AAPL', 155.0, datetime.now())
    assert trader.positions['AAPL'] == 0

    trader.stop()


def test_concurrent_symbol_processing(paper_trader_realtime):
    """Test that all symbols are processed in each iteration"""
    trader, broker = paper_trader_realtime

    trader.start()

    # Clear previous fetches
    broker.symbols_fetched.clear()

    # Run iteration
    trader._realtime_iteration('1d')

    # Both symbols should be fetched
    assert 'AAPL' in broker.symbols_fetched
    assert 'MSFT' in broker.symbols_fetched

    # Each symbol should be fetched at least once (ticker + ohlcv)
    aapl_count = broker.symbols_fetched.count('AAPL')
    msft_count = broker.symbols_fetched.count('MSFT')
    assert aapl_count >= 1
    assert msft_count >= 1

    trader.stop()
