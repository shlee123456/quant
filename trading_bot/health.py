"""
Scheduler Health Check Module

Manages a JSON status file for monitoring scheduler health.
Supports atomic writes (tmp + rename) to prevent corrupted reads.
"""

import json
import os
import tempfile
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_STATES = {"starting", "idle", "optimizing", "trading", "stopping", "error"}


class SchedulerHealth:
    """Manages scheduler health status via a JSON file."""

    def __init__(self, status_file: str = "data/scheduler_status.json") -> None:
        self.status_file = status_file

    def update(self, state: str, details: Optional[Dict] = None) -> None:
        """Atomically write the current scheduler state to the status file.

        Writes to a temporary file in the same directory, then renames
        to ensure readers never see a partially-written file.

        Args:
            state: One of the valid states (starting, idle, optimizing,
                   trading, stopping, error).
            details: Optional dictionary with extra information such as
                     active session data.

        Raises:
            ValueError: If *state* is not a recognised state string.
        """
        if state not in VALID_STATES:
            raise ValueError(
                f"Invalid state '{state}'. Must be one of {sorted(VALID_STATES)}"
            )

        status = {
            "state": state,
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "details": details or {},
        }

        dir_name = os.path.dirname(self.status_file) or "."
        os.makedirs(dir_name, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
            os.rename(tmp_path, self.status_file)
        except OSError as e:
            logger.error("상태 파일 쓰기 실패: %s", e)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        logger.debug("Health status updated: state=%s", state)

    def read(self) -> Optional[Dict]:
        """Read the current status from the JSON file.

        Returns:
            The parsed status dictionary, or ``None`` if the file does
            not exist or cannot be parsed.
        """
        if not os.path.exists(self.status_file):
            return None

        try:
            with open(self.status_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read status file: %s", exc)
            return None

    def is_healthy(self, max_stale_seconds: int = 180) -> bool:
        """Check whether the scheduler is healthy.

        The scheduler is considered healthy when:
        1. The status file exists and is parseable.
        2. The recorded timestamp is no older than *max_stale_seconds*.
        3. The state is not ``error``.

        Args:
            max_stale_seconds: Maximum age of the status file in seconds
                               before it is considered stale.

        Returns:
            ``True`` if the scheduler appears healthy, ``False`` otherwise.
        """
        status = self.read()
        if status is None:
            return False

        if status.get("state") == "error":
            return False

        timestamp_str = status.get("timestamp")
        if not timestamp_str:
            return False

        try:
            file_time = datetime.fromisoformat(timestamp_str)
            age = (datetime.now() - file_time).total_seconds()
            return age <= max_stale_seconds
        except (ValueError, TypeError):
            return False
