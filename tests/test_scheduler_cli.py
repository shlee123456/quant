"""
Tests for scheduler.py management CLI (--status, --stop, --cleanup, --stop-all)
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.database import TradingDatabase
from trading_bot.health import SchedulerHealth


class TestSchedulerCLIStatus:
    """--status 명령 테스트"""

    def test_status_no_status_file(self, tmp_path, capsys):
        """상태 파일이 없을 때 --status 출력 확인"""
        from scheduler import _handle_status, scheduler_health, global_db

        # 임시 상태 파일로 교체
        original_file = scheduler_health.status_file
        scheduler_health.status_file = str(tmp_path / "nonexistent.json")

        try:
            _handle_status()
            captured = capsys.readouterr()
            assert "상태 파일 없음" in captured.out
        finally:
            scheduler_health.status_file = original_file

    def test_status_with_status_file(self, tmp_path, capsys):
        """상태 파일이 있을 때 --status 출력 확인"""
        from scheduler import _handle_status, scheduler_health

        original_file = scheduler_health.status_file
        scheduler_health.status_file = str(tmp_path / "status.json")

        try:
            scheduler_health.update('idle', {'active_sessions': []})
            _handle_status()
            captured = capsys.readouterr()
            assert "idle" in captured.out
        finally:
            scheduler_health.status_file = original_file


class TestSchedulerCLIStop:
    """--stop 명령 테스트"""

    def test_stop_inserts_command(self, tmp_path):
        """--stop이 DB에 명령을 삽입하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        with patch('trading_bot.scheduler.scheduler_state.global_db', db):
            from scheduler import _handle_stop
            _handle_stop("test-session")

        commands = db.get_pending_commands()
        assert len(commands) == 1
        assert commands[0]['command'] == 'stop_session'
        assert commands[0]['target_label'] == 'test-session'


class TestSchedulerCLICleanup:
    """--cleanup 명령 테스트"""

    def test_cleanup_recovers_zombies(self, tmp_path, capsys):
        """--cleanup이 좀비 세션을 정리하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        # 활성 세션 생성 (좀비)
        db.create_session("test_strategy", 10000.0)

        with patch('trading_bot.scheduler.scheduler_state.global_db', db):
            from scheduler import _handle_cleanup
            _handle_cleanup()

        captured = capsys.readouterr()
        assert "1개" in captured.out

        # 활성 세션이 없어야 함
        active = db.get_all_sessions(status_filter='active')
        assert len(active) == 0


class TestSchedulerCLIStopAll:
    """--stop-all 명령 테스트"""

    def test_stop_all_inserts_commands_for_all_active(self, tmp_path, capsys):
        """--stop-all이 모든 활성 세션에 명령을 삽입하는지 확인"""
        db = TradingDatabase(db_path=str(tmp_path / "test.db"))

        # 활성 세션 2개 생성
        db.create_session("strategy_1", 10000.0, display_name="Session 1")
        db.create_session("strategy_2", 10000.0, display_name="Session 2")

        with patch('trading_bot.scheduler.scheduler_state.global_db', db):
            from scheduler import _handle_stop_all
            _handle_stop_all()

        captured = capsys.readouterr()
        assert "2개" in captured.out

        commands = db.get_pending_commands()
        assert len(commands) == 2


class TestHealthcheck:
    """scripts/healthcheck.py 테스트"""

    def test_healthy(self, tmp_path):
        """정상 상태 파일이 있으면 exit 0"""
        health = SchedulerHealth(status_file=str(tmp_path / "status.json"))
        health.update('idle')

        with patch('scripts.healthcheck.SchedulerHealth', return_value=health):
            # 직접 함수 호출 대신 로직만 테스트
            assert health.is_healthy(max_stale_seconds=180)

    def test_unhealthy_no_file(self, tmp_path):
        """상태 파일이 없으면 unhealthy"""
        health = SchedulerHealth(status_file=str(tmp_path / "nonexistent.json"))
        assert not health.is_healthy(max_stale_seconds=180)

    def test_unhealthy_error_state(self, tmp_path):
        """에러 상태면 unhealthy"""
        health = SchedulerHealth(status_file=str(tmp_path / "status.json"))
        health.update('error')
        assert not health.is_healthy(max_stale_seconds=180)
