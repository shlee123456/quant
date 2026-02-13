"""
Unit tests for TradingDatabase
"""

import pytest
import os
import tempfile
import sqlite3
from datetime import datetime
from trading_bot.database import TradingDatabase, generate_display_name


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_paper_trading.db')

    # Initialize database
    db = TradingDatabase(db_path=db_path)

    yield db

    # Cleanup (including WAL/SHM files)
    for suffix in ('', '-wal', '-shm'):
        path = db_path + suffix
        if os.path.exists(path):
            os.remove(path)
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


# --- generate_display_name 단위 테스트 ---

def test_generate_display_name_single_symbol():
    result = generate_display_name('RSI_14_30_70', ['NVDA'])
    assert result == 'RSI_14_30_70 | NVDA'


def test_generate_display_name_multiple_symbols():
    result = generate_display_name('RSI_14_30_70', ['AAPL', 'MSFT', 'GOOGL'])
    assert result == 'RSI_14_30_70 | AAPL외2'


def test_generate_display_name_with_preset():
    result = generate_display_name('RSI_14_30_70', ['AAPL', 'MSFT', 'GOOGL'], preset_name='보수적RSI')
    assert result == '보수적RSI | AAPL외2'


def test_generate_display_name_empty_symbols():
    result = generate_display_name('RSI_14_30_70', [])
    assert result == 'RSI_14_30_70'


# --- create_session display_name 테스트 ---

def test_create_session_with_display_name(temp_db):
    session_id = temp_db.create_session(
        strategy_name='TestStrategy',
        initial_capital=10000.0,
        display_name='보수적RSI | AAPL외2'
    )
    summary = temp_db.get_session_summary(session_id)
    assert summary['display_name'] == '보수적RSI | AAPL외2'


def test_create_session_without_display_name(temp_db):
    session_id = temp_db.create_session(
        strategy_name='TestStrategy',
        initial_capital=10000.0
    )
    summary = temp_db.get_session_summary(session_id)
    assert summary['display_name'] is None


# --- WAL 모드 + 인덱스 최적화 테스트 ---

def test_wal_mode_enabled(temp_db):
    """WAL 저널 모드가 활성화되어 있는지 확인"""
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()
    assert mode == 'wal'


def test_indexes_exist(temp_db):
    """필수 인덱스가 모두 생성되었는지 확인"""
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    index_names = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected_indexes = {
        'idx_trades_session_id',
        'idx_trades_timestamp',
        'idx_snapshots_session_id',
        'idx_snapshots_timestamp',
        'idx_signals_session_id',
        'idx_signals_timestamp',
        'idx_sessions_status',
    }
    for idx in expected_indexes:
        assert idx in index_names, f"Index {idx} not found"


def test_context_manager_commits_on_success(temp_db):
    """컨텍스트 매니저가 정상 종료 시 커밋하는지 확인"""
    with temp_db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO paper_trading_sessions
            (session_id, strategy_name, start_time, initial_capital, status)
            VALUES ('ctx_test', 'TestStrategy', '2026-01-01T00:00:00', 10000.0, 'active')
        """)

    # 데이터가 커밋되었는지 확인
    summary = temp_db.get_session_summary('ctx_test')
    assert summary is not None
    assert summary['strategy_name'] == 'TestStrategy'


def test_context_manager_rollback_on_error(temp_db):
    """컨텍스트 매니저가 예외 시 롤백하는지 확인"""
    # 먼저 세션 하나 생성
    temp_db.create_session('RollbackTest', 10000.0)

    try:
        with temp_db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO paper_trading_sessions
                (session_id, strategy_name, start_time, initial_capital, status)
                VALUES ('rollback_test', 'TestStrategy', '2026-01-01T00:00:00', 10000.0, 'active')
            """)
            # 강제 예외 발생
            raise ValueError("Intentional error for rollback test")
    except ValueError:
        pass

    # 롤백되었으므로 데이터가 없어야 함
    summary = temp_db.get_session_summary('rollback_test')
    assert summary is None


def test_context_manager_sets_row_factory(temp_db):
    """컨텍스트 매니저가 row_factory를 sqlite3.Row로 설정하는지 확인"""
    temp_db.create_session('RowFactoryTest', 10000.0)

    with temp_db._get_connection() as conn:
        assert conn.row_factory == sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM paper_trading_sessions LIMIT 1")
        row = cursor.fetchone()
        # sqlite3.Row는 dict처럼 키로 접근 가능
        assert row['strategy_name'] == 'RowFactoryTest'
