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


def _create_session_helper(db: TradingDatabase, name: str, status: str = 'completed') -> str:
    """테스트용 세션 생성 헬퍼"""
    session_id = db.create_session(name, initial_capital=10000.0)
    if status != 'active':
        db.update_session(session_id, {
            'status': status,
            'end_time': datetime.now().isoformat(),
        })
    return session_id


def _add_snapshots_bulk(db: TradingDatabase, session_id: str, count: int,
                        start_time: datetime, interval_minutes: int = 1):
    """지정 간격으로 스냅샷 벌크 추가"""
    for i in range(count):
        ts = start_time + timedelta(minutes=i * interval_minutes)
        db.log_portfolio_snapshot(session_id, {
            'timestamp': ts,
            'total_value': 10000.0 + i,
            'cash': 5000.0,
            'positions': {'AAPL': 10},
        })


def _add_signals_bulk(db: TradingDatabase, session_id: str, count: int,
                      start_time: datetime, executed_ratio: float = 0.1):
    """시그널 벌크 추가 (executed_ratio 비율만 executed=True)"""
    executed_count = int(count * executed_ratio)
    for i in range(count):
        ts = start_time + timedelta(minutes=i)
        db.log_signal(session_id, {
            'symbol': 'AAPL',
            'timestamp': ts,
            'signal': 1 if i % 2 == 0 else -1,
            'indicator_values': {'rsi': 30 + i},
            'market_price': 150.0 + i * 0.1,
            'executed': i < executed_count,
        })


class TestDownsampleCompletedSessions:
    """downsample_completed_sessions 메서드 테스트"""

    def test_downsamples_snapshots_to_hourly(self, db):
        """1분 간격 스냅샷 → 1시간 간격으로 축소"""
        session_id = _create_session_helper(db, 'TestStrategy', 'completed')
        start = datetime(2026, 2, 20, 10, 0, 0)

        # 3시간분(180개) 1분 간격 스냅샷 추가
        _add_snapshots_bulk(db, session_id, 180, start, interval_minutes=1)

        # 다운샘플링 전 확인
        snapshots_before = db.get_session_snapshots(session_id)
        assert len(snapshots_before) == 180

        # 다운샘플링
        result = db.downsample_completed_sessions(hours_interval=1)

        # 다운샘플링 후 확인: 3시간이니 대략 3~4개
        snapshots_after = db.get_session_snapshots(session_id)
        assert len(snapshots_after) <= 4
        assert len(snapshots_after) < 180
        assert result['snapshots_removed'] == 180 - len(snapshots_after)

    def test_removes_unexecuted_signals(self, db):
        """executed=False 시그널만 삭제"""
        session_id = _create_session_helper(db, 'TestStrategy', 'completed')
        start = datetime(2026, 2, 20, 10, 0, 0)

        # 100개 시그널 추가 (10%만 executed)
        _add_signals_bulk(db, session_id, 100, start, executed_ratio=0.1)

        # 다운샘플링
        result = db.downsample_completed_sessions(hours_interval=1)

        # executed=True인 10개만 남아야 함
        signals_after = db.get_session_signals(session_id)
        assert len(signals_after) == 10
        assert all(s['executed'] == 1 for s in signals_after)
        assert result['signals_removed'] == 90

    def test_does_not_touch_active_sessions(self, db):
        """active 세션은 건드리지 않음"""
        active_id = _create_session_helper(db, 'ActiveStrategy', 'active')
        start = datetime(2026, 2, 20, 10, 0, 0)

        _add_snapshots_bulk(db, active_id, 60, start)
        _add_signals_bulk(db, active_id, 50, start, executed_ratio=0.1)

        # 다운샘플링
        result = db.downsample_completed_sessions(hours_interval=1)

        # active 세션은 그대로
        snapshots = db.get_session_snapshots(active_id)
        signals = db.get_session_signals(active_id)
        assert len(snapshots) == 60
        assert len(signals) == 50
        assert result['snapshots_removed'] == 0
        assert result['signals_removed'] == 0

    def test_handles_multiple_completed_sessions(self, db):
        """여러 완료된 세션을 모두 처리"""
        start = datetime(2026, 2, 20, 10, 0, 0)

        session1 = _create_session_helper(db, 'Strategy1', 'completed')
        _add_snapshots_bulk(db, session1, 120, start)
        _add_signals_bulk(db, session1, 50, start, executed_ratio=0.2)

        session2 = _create_session_helper(db, 'Strategy2', 'interrupted')
        _add_snapshots_bulk(db, session2, 60, start)
        _add_signals_bulk(db, session2, 30, start, executed_ratio=0.0)

        result = db.downsample_completed_sessions(hours_interval=1)

        assert result['snapshots_removed'] > 0
        assert result['signals_removed'] > 0

        # session2의 모든 시그널은 executed=False이므로 전부 삭제
        signals2 = db.get_session_signals(session2)
        assert len(signals2) == 0

    def test_no_completed_sessions_returns_zero(self, db):
        """완료된 세션이 없으면 0 반환"""
        active_id = _create_session_helper(db, 'ActiveOnly', 'active')
        start = datetime(2026, 2, 20, 10, 0, 0)
        _add_snapshots_bulk(db, active_id, 60, start)

        result = db.downsample_completed_sessions(hours_interval=1)
        assert result == {'snapshots_removed': 0, 'signals_removed': 0}

    def test_terminated_sessions_also_processed(self, db):
        """terminated 상태 세션도 다운샘플링 대상"""
        session_id = _create_session_helper(db, 'TerminatedStrategy', 'terminated')
        start = datetime(2026, 2, 20, 10, 0, 0)
        _add_snapshots_bulk(db, session_id, 120, start)

        result = db.downsample_completed_sessions(hours_interval=1)
        snapshots_after = db.get_session_snapshots(session_id)

        assert result['snapshots_removed'] > 0
        assert len(snapshots_after) < 120

    def test_idempotent_when_run_twice(self, db):
        """두 번 실행해도 결과 동일"""
        session_id = _create_session_helper(db, 'TestStrategy', 'completed')
        start = datetime(2026, 2, 20, 10, 0, 0)
        _add_snapshots_bulk(db, session_id, 120, start)

        # 1차 실행
        result1 = db.downsample_completed_sessions(hours_interval=1)
        count_after_first = len(db.get_session_snapshots(session_id))

        # 2차 실행
        result2 = db.downsample_completed_sessions(hours_interval=1)
        count_after_second = len(db.get_session_snapshots(session_id))

        assert result1['snapshots_removed'] > 0
        assert result2['snapshots_removed'] == 0
        assert count_after_first == count_after_second


class TestGetDbStats:
    """get_db_stats 메서드 테스트"""

    def test_returns_all_table_counts(self, db):
        """모든 테이블의 row 수 반환"""
        stats = db.get_db_stats()

        assert 'tables' in stats
        expected_tables = [
            'paper_trading_sessions', 'trades', 'portfolio_snapshots',
            'strategy_signals', 'regime_history', 'llm_decisions',
            'scheduler_commands'
        ]
        for table in expected_tables:
            assert table in stats['tables']

    def test_counts_reflect_data(self, db):
        """데이터 추가 후 count가 반영됨"""
        session_id = _create_session_helper(db, 'TestStrategy', 'active')
        start = datetime(2026, 2, 20, 10, 0, 0)
        _add_snapshots_bulk(db, session_id, 5, start)
        _add_signals_bulk(db, session_id, 3, start, executed_ratio=1.0)

        stats = db.get_db_stats()

        assert stats['tables']['paper_trading_sessions'] == 1
        assert stats['tables']['portfolio_snapshots'] == 5
        assert stats['tables']['strategy_signals'] == 3

    def test_returns_file_size(self, db):
        """DB 파일 크기 반환"""
        stats = db.get_db_stats()

        assert 'file_size_bytes' in stats
        assert 'file_size_mb' in stats
        assert stats['file_size_bytes'] > 0
        assert isinstance(stats['file_size_mb'], float)

    def test_empty_db_returns_zero_counts(self, db):
        """빈 DB는 모든 count가 0"""
        stats = db.get_db_stats()

        for table, count in stats['tables'].items():
            assert count == 0


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
