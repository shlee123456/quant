"""
대시보드 DB 명령 큐 연동 테스트

SchedulerManager의 DB 명령 큐 메서드와
session_manager의 중지 명령 전송 기능을 테스트합니다.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.database import TradingDatabase
from trading_bot.health import SchedulerHealth


class TestSchedulerManagerCommandQueue:
    """SchedulerManager DB 명령 큐 메서드 테스트"""

    def test_send_stop_command(self, tmp_path):
        """send_stop_command가 DB에 stop_session 명령을 삽입하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            cmd_id = manager.send_stop_command("test-session")

        commands = db.get_pending_commands()
        assert len(commands) == 1
        assert commands[0]['command'] == 'stop_session'
        assert commands[0]['target_label'] == 'test-session'
        assert cmd_id == commands[0]['id']

    def test_send_stop_all_command(self, tmp_path):
        """send_stop_all_command가 모든 활성 세션에 명령을 삽입하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))
        db.create_session("strategy_1", 10000.0, display_name="Session A")
        db.create_session("strategy_2", 10000.0, display_name="Session B")

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            cmd_ids = manager.send_stop_all_command()

        assert len(cmd_ids) == 2
        commands = db.get_pending_commands()
        assert len(commands) == 2
        targets = {c['target_label'] for c in commands}
        assert 'Session A' in targets
        assert 'Session B' in targets

    def test_send_stop_all_no_active(self, tmp_path):
        """활성 세션이 없으면 빈 리스트 반환"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            cmd_ids = manager.send_stop_all_command()

        assert cmd_ids == []

    def test_send_cleanup_command(self, tmp_path):
        """send_cleanup_command가 cleanup_zombies 명령을 삽입하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            cmd_id = manager.send_cleanup_command()

        commands = db.get_pending_commands()
        assert len(commands) == 1
        assert commands[0]['command'] == 'cleanup_zombies'
        assert commands[0]['target_label'] is None

    def test_get_pending_commands(self, tmp_path):
        """get_pending_commands가 미처리 명령을 반환하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))
        db.insert_command('stop_session', 'session-1')
        db.insert_command('cleanup_zombies')

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            pending = manager.get_pending_commands()

        assert len(pending) == 2

    def test_get_pending_commands_empty(self, tmp_path):
        """미처리 명령이 없으면 빈 리스트 반환"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        with patch('dashboard.scheduler_manager.TradingDatabase', return_value=db):
            from dashboard.scheduler_manager import SchedulerManager
            manager = SchedulerManager()
            pending = manager.get_pending_commands()

        assert pending == []

    def test_get_scheduler_health_exists(self, tmp_path):
        """상태 파일이 있으면 딕셔너리 반환"""
        health = SchedulerHealth(status_file=str(tmp_path / "status.json"))
        health.update('trading', {'active_sessions': ['s1']})

        from dashboard.scheduler_manager import SchedulerManager
        manager = SchedulerManager()

        with patch('trading_bot.health.SchedulerHealth', return_value=health):
            result = manager.get_scheduler_health()

        assert result is not None
        assert result['state'] == 'trading'

    def test_get_scheduler_health_no_file(self, tmp_path):
        """상태 파일이 없으면 None 반환"""
        health = SchedulerHealth(status_file=str(tmp_path / "nonexistent.json"))

        from dashboard.scheduler_manager import SchedulerManager
        manager = SchedulerManager()

        with patch.object(manager, 'get_scheduler_health', return_value=None):
            result = manager.get_scheduler_health()

        assert result is None


class TestSessionManagerStopCommand:
    """session_manager의 DB 명령 전송 테스트"""

    def test_insert_stop_command_directly(self, tmp_path):
        """DB에 직접 stop_session 명령 삽입 테스트"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))
        db.create_session("strategy_1", 10000.0, display_name="Test Session")

        cmd_id = db.insert_command('stop_session', 'Test Session')

        commands = db.get_pending_commands()
        assert len(commands) == 1
        assert commands[0]['command'] == 'stop_session'
        assert commands[0]['target_label'] == 'Test Session'
        assert commands[0]['id'] == cmd_id

    def test_command_lifecycle(self, tmp_path):
        """명령 삽입 → 조회 → 처리 완료 전체 흐름"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        # 삽입
        cmd_id = db.insert_command('stop_session', 'session-1')
        assert db.get_pending_commands()

        # 처리 완료
        db.mark_command_processed(cmd_id)
        assert len(db.get_pending_commands()) == 0
