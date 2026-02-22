"""
Tests for database.py scheduler commands and maintenance methods
"""

import os
import pytest
from datetime import datetime, timedelta

from trading_bot.database import TradingDatabase


@pytest.fixture
def db(tmp_path):
    """Create a TradingDatabase with isolated tmp_path DB"""
    db_path = str(tmp_path / "test.db")
    return TradingDatabase(db_path=db_path)


class TestSchedulerCommands:
    """scheduler_commands table CRUD tests"""

    def test_insert_command_returns_id(self, db):
        cmd_id = db.insert_command("stop_session", target_label="RSI_preset")
        assert isinstance(cmd_id, int)
        assert cmd_id >= 1

    def test_insert_command_without_target(self, db):
        cmd_id = db.insert_command("cleanup_zombies")
        assert cmd_id >= 1

    def test_get_pending_commands(self, db):
        db.insert_command("stop_session", target_label="preset_A")
        db.insert_command("status_dump")

        pending = db.get_pending_commands()
        assert len(pending) == 2
        assert pending[0]['command'] == 'stop_session'
        assert pending[0]['target_label'] == 'preset_A'
        assert pending[1]['command'] == 'status_dump'
        assert pending[1]['target_label'] is None

    def test_get_pending_commands_empty(self, db):
        pending = db.get_pending_commands()
        assert pending == []

    def test_mark_command_processed(self, db):
        cmd_id = db.insert_command("stop_session", target_label="preset_A")

        # Before processing
        pending = db.get_pending_commands()
        assert len(pending) == 1

        # Mark processed
        db.mark_command_processed(cmd_id)

        # After processing
        pending = db.get_pending_commands()
        assert len(pending) == 0

    def test_mark_only_target_command_processed(self, db):
        id1 = db.insert_command("stop_session", target_label="A")
        id2 = db.insert_command("status_dump")

        db.mark_command_processed(id1)

        pending = db.get_pending_commands()
        assert len(pending) == 1
        assert pending[0]['id'] == id2


class TestPruneOldData:
    """prune_old_data tests"""

    def _create_old_session(self, db, session_id: str, days_ago: int, status: str = 'completed'):
        """Helper: create a session that ended days_ago days in the past"""
        end_time = (datetime.now() - timedelta(days=days_ago)).isoformat()
        start_time = (datetime.now() - timedelta(days=days_ago + 1)).isoformat()

        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO paper_trading_sessions
                (session_id, strategy_name, start_time, end_time, initial_capital, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, 'TestStrategy', start_time, end_time, 10000.0, status))

    def _add_snapshot(self, db, session_id: str):
        db.log_portfolio_snapshot(session_id, {
            'timestamp': datetime.now().isoformat(),
            'total_value': 10000.0,
            'cash': 5000.0,
            'positions': {'AAPL': 10}
        })

    def _add_signal(self, db, session_id: str):
        db.log_signal(session_id, {
            'symbol': 'AAPL',
            'timestamp': datetime.now().isoformat(),
            'signal': 1,
            'indicator_values': {'rsi': 30},
            'market_price': 150.0,
            'executed': True
        })

    def _add_regime(self, db, session_id: str):
        db.log_regime(session_id, {
            'symbol': 'AAPL',
            'timestamp': datetime.now().isoformat(),
            'regime': 'BULLISH',
            'confidence': 0.8,
            'adx': 30.0,
            'trend_direction': 1.0,
            'volatility_percentile': 50.0,
            'recommended_strategies': ['RSI'],
            'details': {}
        })

    def _add_llm_decision(self, db, session_id: str):
        db.log_llm_decision(session_id, {
            'symbol': 'AAPL',
            'timestamp': datetime.now().isoformat(),
            'decision_type': 'signal_filter',
            'request_context': {},
            'response': {'action': 'execute'},
            'latency_ms': 100.0,
            'model_name': 'test-model'
        })

    def test_prune_deletes_old_session_data(self, db):
        """Old completed sessions should have snapshots/signals/regimes/llm_decisions pruned"""
        self._create_old_session(db, 'old_session', days_ago=60)
        self._add_snapshot(db, 'old_session')
        self._add_signal(db, 'old_session')
        self._add_regime(db, 'old_session')
        self._add_llm_decision(db, 'old_session')

        result = db.prune_old_data(days_to_keep=30)

        assert result['snapshots'] == 1
        assert result['signals'] == 1
        assert result['regimes'] == 1
        assert result['llm_decisions'] == 1

        # Verify data is gone
        assert db.get_session_snapshots('old_session') == []
        assert db.get_session_signals('old_session') == []

    def test_prune_keeps_recent_session_data(self, db):
        """Recent sessions should not be pruned"""
        self._create_old_session(db, 'recent_session', days_ago=10)
        self._add_snapshot(db, 'recent_session')
        self._add_signal(db, 'recent_session')

        result = db.prune_old_data(days_to_keep=30)

        assert result == {'snapshots': 0, 'signals': 0, 'regimes': 0, 'llm_decisions': 0}

        # Data still present
        assert len(db.get_session_snapshots('recent_session')) == 1
        assert len(db.get_session_signals('recent_session')) == 1

    def test_prune_keeps_active_session_data(self, db):
        """Active sessions should never be pruned regardless of age"""
        self._create_old_session(db, 'active_old', days_ago=60, status='active')
        self._add_snapshot(db, 'active_old')

        result = db.prune_old_data(days_to_keep=30)

        assert result == {'snapshots': 0, 'signals': 0, 'regimes': 0, 'llm_decisions': 0}
        assert len(db.get_session_snapshots('active_old')) == 1

    def test_prune_preserves_session_and_trade_records(self, db):
        """Session and trade records should be preserved even after pruning"""
        self._create_old_session(db, 'old_session', days_ago=60)
        self._add_snapshot(db, 'old_session')
        db.log_trade('old_session', {
            'symbol': 'AAPL',
            'timestamp': datetime.now().isoformat(),
            'type': 'BUY',
            'price': 150.0,
            'size': 10.0,
            'commission': 1.0
        })

        db.prune_old_data(days_to_keep=30)

        # Session still exists
        session = db.get_session_summary('old_session')
        assert session is not None

        # Trade still exists
        trades = db.get_session_trades('old_session')
        assert len(trades) == 1

    def test_prune_no_old_sessions(self, db):
        """No old sessions should return all zeros"""
        result = db.prune_old_data(days_to_keep=30)
        assert result == {'snapshots': 0, 'signals': 0, 'regimes': 0, 'llm_decisions': 0}


class TestVacuum:
    """vacuum() tests"""

    def test_vacuum_runs_without_error(self, db):
        """VACUUM should complete without raising exceptions"""
        # Add some data first
        db.create_session('TestStrategy', 10000.0)
        db.vacuum()
        # No assertion needed - just verify no exception


class TestBackup:
    """backup() tests"""

    def test_backup_creates_file(self, db, tmp_path):
        backup_dir = str(tmp_path / "backups")
        backup_path = db.backup(backup_dir=backup_dir)

        assert os.path.exists(backup_path)
        assert backup_path.startswith(backup_dir)
        assert backup_path.endswith('.db')

    def test_backup_creates_directory(self, db, tmp_path):
        backup_dir = str(tmp_path / "new_backup_dir")
        assert not os.path.exists(backup_dir)

        db.backup(backup_dir=backup_dir)

        assert os.path.exists(backup_dir)

    def test_backup_file_is_valid_db(self, db, tmp_path):
        """Backup should be a valid SQLite database"""
        db.create_session('TestStrategy', 10000.0)

        backup_dir = str(tmp_path / "backups")
        backup_path = db.backup(backup_dir=backup_dir)

        # Open backup and verify it has the sessions table
        backup_db = TradingDatabase(db_path=backup_path)
        sessions = backup_db.get_all_sessions()
        assert len(sessions) == 1
        assert sessions[0]['strategy_name'] == 'TestStrategy'
