"""
Unit tests for live trading database tables (DB-001)
"""

import pytest
import os
import sqlite3
import tempfile
from trading_bot.database import TradingDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_live_trading.db')
    db = TradingDatabase(db_path=db_path)

    yield db

    if os.path.exists(db_path):
        os.remove(db_path)
    # Remove WAL/SHM files if they exist
    for suffix in ('-wal', '-shm'):
        wal_path = db_path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)
    os.rmdir(temp_dir)


class TestLiveTradingTables:
    """Test that the 3 new live trading tables are created"""

    def test_tables_created(self, temp_db):
        """Verify 3 live trading tables exist in schema"""
        conn = sqlite3.connect(temp_db.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert 'live_trading_sessions' in tables
        assert 'live_orders' in tables
        assert 'live_trading_state' in tables


class TestLiveSession:
    """Test live trading session CRUD"""

    def test_create_get_live_session(self, temp_db):
        """Create a live session and retrieve it, verify fields"""
        temp_db.create_live_session(
            session_id='live_test_001',
            strategy_name='RSI_14',
            display_name='Test RSI',
            mode='dry_run',
            initial_capital=10000.0,
            broker_name='KIS',
            market_type='overseas'
        )

        session = temp_db.get_live_session('live_test_001')
        assert session is not None
        assert session['session_id'] == 'live_test_001'
        assert session['strategy_name'] == 'RSI_14'
        assert session['display_name'] == 'Test RSI'
        assert session['mode'] == 'dry_run'
        assert session['initial_capital'] == 10000.0
        assert session['status'] == 'active'
        assert session['broker_name'] == 'KIS'
        assert session['market_type'] == 'overseas'
        assert session['start_time'] is not None

    def test_get_live_session_returns_none_for_missing(self, temp_db):
        """get_live_session returns None for non-existent session"""
        result = temp_db.get_live_session('nonexistent')
        assert result is None

    def test_update_live_session(self, temp_db):
        """Update live session fields and verify"""
        temp_db.create_live_session(
            session_id='live_test_002',
            strategy_name='MACD',
            display_name='Test MACD',
            mode='dry_run',
            initial_capital=20000.0
        )

        temp_db.update_live_session('live_test_002', {
            'final_capital': 21000.0,
            'status': 'completed',
            'total_return': 5.0,
            'kill_switch_reason': None,
        })

        session = temp_db.get_live_session('live_test_002')
        assert session['final_capital'] == 21000.0
        assert session['status'] == 'completed'
        assert session['total_return'] == 5.0


class TestLiveOrders:
    """Test live orders CRUD"""

    def test_log_get_live_orders(self, temp_db):
        """Log an order and retrieve by session_id and by status filter"""
        order = {
            'internal_id': 'ord_001',
            'session_id': 'sess_001',
            'broker_order_id': 'broker_123',
            'symbol': 'AAPL',
            'side': 'buy',
            'order_type': 'market',
            'requested_amount': 10.0,
            'requested_price': 150.0,
            'status': 'filled',
            'reason': 'signal',
            'submitted_at': '2026-03-23T10:00:00',
            'filled_at': '2026-03-23T10:00:01',
            'filled_amount': 10.0,
            'filled_price': 150.5,
            'commission': 1.5,
            'slippage_pct': 0.003,
        }
        temp_db.log_live_order(order)

        # Retrieve by session_id (no status filter)
        orders = temp_db.get_live_orders('sess_001')
        assert len(orders) == 1
        assert orders[0]['symbol'] == 'AAPL'
        assert orders[0]['filled_price'] == 150.5

        # Retrieve by status filter
        filled = temp_db.get_live_orders('sess_001', status='filled')
        assert len(filled) == 1

        pending = temp_db.get_live_orders('sess_001', status='pending')
        assert len(pending) == 0

    def test_update_live_order(self, temp_db):
        """Update order status from pending to filled"""
        order = {
            'internal_id': 'ord_002',
            'session_id': 'sess_002',
            'symbol': 'MSFT',
            'side': 'buy',
            'order_type': 'market',
            'requested_amount': 5.0,
            'status': 'pending',
        }
        temp_db.log_live_order(order)

        temp_db.update_live_order('ord_002', {
            'status': 'filled',
            'filled_amount': 5.0,
            'filled_price': 400.0,
            'filled_at': '2026-03-23T10:05:00',
        })

        orders = temp_db.get_live_orders('sess_002', status='filled')
        assert len(orders) == 1
        assert orders[0]['filled_amount'] == 5.0
        assert orders[0]['filled_price'] == 400.0


class TestLiveState:
    """Test live trading state key-value store"""

    def test_get_set_live_state(self, temp_db):
        """Set a key, get it, then overwrite it"""
        temp_db.set_live_state('kill_switch_active', 'false')
        assert temp_db.get_live_state('kill_switch_active') == 'false'

        # Overwrite
        temp_db.set_live_state('kill_switch_active', 'true')
        assert temp_db.get_live_state('kill_switch_active') == 'true'

    def test_live_state_returns_none_for_missing_key(self, temp_db):
        """get_live_state returns None for a key that doesn't exist"""
        result = temp_db.get_live_state('nonexistent_key')
        assert result is None
