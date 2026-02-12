"""
Unit tests for TradingDatabase
"""

import pytest
import os
import tempfile
import sqlite3
from datetime import datetime
from trading_bot.database import TradingDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_paper_trading.db')

    # Initialize database
    db = TradingDatabase(db_path=db_path)

    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


def test_database_schema_creation(temp_db):
    """Test that database schema is created correctly"""
    # Database should be initialized in fixture
    assert temp_db.db_path is not None

    # Check that tables exist by creating a connection and querying
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()

    # Check paper_trading_sessions table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trading_sessions'")
    assert cursor.fetchone() is not None

    # Check trades table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
    assert cursor.fetchone() is not None

    # Check portfolio_snapshots table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio_snapshots'")
    assert cursor.fetchone() is not None

    # Check strategy_signals table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_signals'")
    assert cursor.fetchone() is not None

    conn.close()


def test_create_session(temp_db):
    """Test creating a new paper trading session"""
    session_id = temp_db.create_session(
        strategy_name='TestStrategy',
        initial_capital=10000.0
    )

    assert session_id is not None
    assert 'TestStrategy' in session_id

    # Verify session was created
    summary = temp_db.get_session_summary(session_id)
    assert summary is not None
    assert summary['strategy_name'] == 'TestStrategy'
    assert summary['initial_capital'] == 10000.0
    assert summary['status'] == 'active'


def test_log_trade(temp_db):
    """Test logging a trade"""
    # Create session first
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # Log a trade
    trade_data = {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'type': 'BUY',
        'price': 150.0,
        'size': 10.0,
        'commission': 1.5
    }

    temp_db.log_trade(session_id, trade_data)

    # Verify trade was logged
    trades = temp_db.get_session_trades(session_id)
    assert len(trades) == 1
    assert trades[0]['symbol'] == 'AAPL'
    assert trades[0]['type'] == 'BUY'
    assert trades[0]['price'] == 150.0


def test_log_signal(temp_db):
    """Test logging a strategy signal"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    signal_data = {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'signal': 1,
        'indicator_values': {'rsi': 65.5, 'price': 150.0},
        'market_price': 150.0,
        'executed': False
    }

    temp_db.log_signal(session_id, signal_data)

    # Verify signal was logged
    signals = temp_db.get_session_signals(session_id)
    assert len(signals) == 1
    assert signals[0]['symbol'] == 'AAPL'
    assert signals[0]['signal'] == 1
    assert signals[0]['indicator_values']['rsi'] == 65.5


def test_log_portfolio_snapshot(temp_db):
    """Test logging a portfolio snapshot"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    snapshot_data = {
        'timestamp': datetime.now(),
        'total_value': 10500.0,
        'cash': 5000.0,
        'positions': {'AAPL': 10.0, 'MSFT': 5.0}
    }

    temp_db.log_portfolio_snapshot(session_id, snapshot_data)

    # Verify snapshot was logged
    snapshots = temp_db.get_session_snapshots(session_id)
    assert len(snapshots) == 1
    assert snapshots[0]['total_value'] == 10500.0
    assert snapshots[0]['positions']['AAPL'] == 10.0


def test_json_serialization(temp_db):
    """Test JSON serialization/deserialization"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # Test complex nested JSON structure
    complex_indicators = {
        'rsi': 65.5,
        'macd': {'line': 12.5, 'signal': 10.2, 'histogram': 2.3},
        'moving_averages': [50.0, 100.0, 200.0]
    }

    signal_data = {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'signal': 1,
        'indicator_values': complex_indicators,
        'market_price': 150.0,
        'executed': False
    }

    temp_db.log_signal(session_id, signal_data)

    # Retrieve and verify
    signals = temp_db.get_session_signals(session_id)
    assert len(signals) == 1
    retrieved_indicators = signals[0]['indicator_values']
    assert retrieved_indicators['macd']['histogram'] == 2.3
    assert retrieved_indicators['moving_averages'][2] == 200.0


def test_update_session(temp_db):
    """Test updating session data"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # Update session
    temp_db.update_session(session_id, {
        'final_capital': 12000.0,
        'total_return': 20.0,
        'status': 'completed'
    })

    # Verify update
    summary = temp_db.get_session_summary(session_id)
    assert summary['final_capital'] == 12000.0
    assert summary['total_return'] == 20.0
    assert summary['status'] == 'completed'


def test_get_all_sessions(temp_db):
    """Test retrieving all sessions"""
    # Create multiple sessions
    session1 = temp_db.create_session('Strategy1', 10000.0)
    session2 = temp_db.create_session('Strategy2', 20000.0)

    all_sessions = temp_db.get_all_sessions()

    assert len(all_sessions) >= 2
    session_ids = [s['session_id'] for s in all_sessions]
    assert session1 in session_ids
    assert session2 in session_ids


def test_error_handling_invalid_session(temp_db):
    """Test error handling for invalid session ID"""
    # Try to get summary for non-existent session
    summary = temp_db.get_session_summary('invalid_session_id')
    assert summary is None

    # Try to get trades for non-existent session
    trades = temp_db.get_session_trades('invalid_session_id')
    assert trades == []


def test_multiple_trades_same_session(temp_db):
    """Test logging multiple trades for same session"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # Log multiple trades
    for i in range(5):
        trade_data = {
            'symbol': 'AAPL',
            'timestamp': datetime.now(),
            'type': 'BUY' if i % 2 == 0 else 'SELL',
            'price': 150.0 + i,
            'size': 10.0,
            'commission': 1.5
        }
        temp_db.log_trade(session_id, trade_data)

    trades = temp_db.get_session_trades(session_id)
    assert len(trades) == 5

    # Verify trades are in order
    assert trades[0]['price'] == 150.0
    assert trades[4]['price'] == 154.0


def test_delete_completed_session(temp_db):
    """완료된 세션 삭제 성공"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # 세션을 completed 상태로 변경
    temp_db.update_session(session_id, {'status': 'completed'})

    result = temp_db.delete_session(session_id)
    assert result is True

    # 세션이 삭제되었는지 확인
    summary = temp_db.get_session_summary(session_id)
    assert summary is None


def test_delete_active_session_rejected(temp_db):
    """active 세션 삭제 거부"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # active 상태 세션 삭제 시도
    result = temp_db.delete_session(session_id)
    assert result is False

    # 세션이 여전히 존재하는지 확인
    summary = temp_db.get_session_summary(session_id)
    assert summary is not None
    assert summary['status'] == 'active'


def test_delete_session_cascades_related_data(temp_db):
    """삭제 시 관련 trades, snapshots, signals도 함께 삭제됨"""
    session_id = temp_db.create_session('TestStrategy', 10000.0)

    # 관련 데이터 추가
    temp_db.log_trade(session_id, {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'type': 'BUY',
        'price': 150.0,
        'size': 10.0,
        'commission': 1.5
    })

    temp_db.log_portfolio_snapshot(session_id, {
        'timestamp': datetime.now(),
        'total_value': 10500.0,
        'cash': 5000.0,
        'positions': {'AAPL': 10.0}
    })

    temp_db.log_signal(session_id, {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'signal': 1,
        'indicator_values': {'rsi': 65.5},
        'market_price': 150.0,
        'executed': False
    })

    # 세션을 completed로 변경 후 삭제
    temp_db.update_session(session_id, {'status': 'completed'})
    result = temp_db.delete_session(session_id)
    assert result is True

    # 모든 관련 데이터가 삭제되었는지 확인
    assert temp_db.get_session_trades(session_id) == []
    assert temp_db.get_session_snapshots(session_id) == []
    assert temp_db.get_session_signals(session_id) == []


def test_delete_nonexistent_session(temp_db):
    """존재하지 않는 세션 삭제 시 False 반환"""
    result = temp_db.delete_session('nonexistent_session_id')
    assert result is False
