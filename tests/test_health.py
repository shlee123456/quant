"""Tests for SchedulerHealth"""

import json
import os
import time
from datetime import datetime, timedelta

import pytest

from trading_bot.health import SchedulerHealth, VALID_STATES


class TestSchedulerHealth:
    """SchedulerHealth unit tests"""

    @pytest.fixture
    def health(self, tmp_path):
        """SchedulerHealth with a temporary status file."""
        return SchedulerHealth(status_file=str(tmp_path / "scheduler_status.json"))

    # ------------------------------------------------------------------
    # update()
    # ------------------------------------------------------------------

    def test_update_writes_file(self, health):
        """update() creates the status file with correct content."""
        health.update("trading", details={"preset_count": 3})

        assert os.path.exists(health.status_file)

        with open(health.status_file) as f:
            data = json.load(f)

        assert data["state"] == "trading"
        assert data["pid"] == os.getpid()
        assert data["details"]["preset_count"] == 3
        assert "timestamp" in data

    def test_update_all_valid_states(self, health):
        """update() accepts every valid state string."""
        for state in VALID_STATES:
            health.update(state)
            status = health.read()
            assert status["state"] == state

    def test_update_invalid_state_raises(self, health):
        """update() raises ValueError for an unknown state."""
        with pytest.raises(ValueError, match="Invalid state"):
            health.update("unknown_state")

    def test_update_creates_parent_directory(self, tmp_path):
        """update() creates missing parent directories."""
        nested = tmp_path / "sub" / "dir" / "status.json"
        h = SchedulerHealth(status_file=str(nested))
        h.update("idle")

        assert os.path.exists(str(nested))

    def test_update_overwrites_previous(self, health):
        """Successive update() calls overwrite the file."""
        health.update("starting")
        health.update("trading")

        status = health.read()
        assert status["state"] == "trading"

    def test_update_without_details(self, health):
        """update() works when details is omitted."""
        health.update("idle")
        status = health.read()
        assert status["details"] == {}

    def test_update_with_session_details(self, health):
        """update() correctly stores session-level details."""
        details = {
            "active_sessions": [
                {"label": "preset1", "alive": True, "started_at": "2026-02-22T10:00:00"}
            ],
            "preset_count": 1,
            "recovered_sessions": 0,
        }
        health.update("trading", details=details)

        status = health.read()
        assert len(status["details"]["active_sessions"]) == 1
        assert status["details"]["active_sessions"][0]["label"] == "preset1"

    # ------------------------------------------------------------------
    # read()
    # ------------------------------------------------------------------

    def test_read_existing_file(self, health):
        """read() returns parsed dict for a valid status file."""
        health.update("idle")
        status = health.read()

        assert isinstance(status, dict)
        assert status["state"] == "idle"

    def test_read_missing_file(self, health):
        """read() returns None when the file does not exist."""
        assert health.read() is None

    def test_read_corrupted_file(self, health):
        """read() returns None for a corrupted (non-JSON) file."""
        os.makedirs(os.path.dirname(health.status_file), exist_ok=True)
        with open(health.status_file, "w") as f:
            f.write("NOT VALID JSON {{{")

        assert health.read() is None

    # ------------------------------------------------------------------
    # is_healthy()
    # ------------------------------------------------------------------

    def test_is_healthy_fresh_file(self, health):
        """is_healthy() returns True for a freshly written non-error state."""
        health.update("trading")
        assert health.is_healthy() is True

    def test_is_healthy_error_state(self, health):
        """is_healthy() returns False when state is 'error'."""
        health.update("error")
        assert health.is_healthy() is False

    def test_is_healthy_missing_file(self, health):
        """is_healthy() returns False when the file is missing."""
        assert health.is_healthy() is False

    def test_is_healthy_stale_file(self, health):
        """is_healthy() returns False when the timestamp is too old."""
        # Write a status with a timestamp 10 minutes in the past
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        status = {
            "state": "trading",
            "timestamp": old_time,
            "pid": os.getpid(),
            "details": {},
        }
        os.makedirs(os.path.dirname(health.status_file), exist_ok=True)
        with open(health.status_file, "w") as f:
            json.dump(status, f)

        assert health.is_healthy(max_stale_seconds=180) is False

    def test_is_healthy_custom_max_stale(self, health):
        """is_healthy() respects a custom max_stale_seconds value."""
        health.update("idle")
        # Freshly written, so even 1 second threshold should pass
        assert health.is_healthy(max_stale_seconds=1) is True

    def test_is_healthy_missing_timestamp(self, health):
        """is_healthy() returns False when timestamp field is absent."""
        os.makedirs(os.path.dirname(health.status_file), exist_ok=True)
        with open(health.status_file, "w") as f:
            json.dump({"state": "idle", "pid": 1, "details": {}}, f)

        assert health.is_healthy() is False

    # ------------------------------------------------------------------
    # Atomic write (tmp + rename)
    # ------------------------------------------------------------------

    def test_atomic_write_no_leftover_tmp(self, health):
        """After update(), no .tmp files remain in the directory."""
        health.update("idle")

        parent = os.path.dirname(health.status_file)
        tmp_files = [f for f in os.listdir(parent) if f.endswith(".tmp")]
        assert tmp_files == []

    def test_atomic_write_valid_json_at_all_times(self, health):
        """The status file is always valid JSON (never partially written)."""
        for state in ["starting", "idle", "optimizing", "trading", "stopping"]:
            health.update(state)
            with open(health.status_file) as f:
                data = json.load(f)  # Should never raise
            assert data["state"] == state
