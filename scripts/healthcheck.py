#!/usr/bin/env python3
"""
Docker 헬스체크 스크립트

상태 파일(data/scheduler_status.json) 기반으로 스케줄러 건강 상태를 판정합니다.
docker-compose.yml의 healthcheck에서 호출됩니다.

Usage:
    python scripts/healthcheck.py

Exit codes:
    0: 정상
    1: 비정상 (상태 파일 없음, 오래됨, 에러 상태)
"""

import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.health import SchedulerHealth


def main() -> int:
    health = SchedulerHealth()

    if health.is_healthy(max_stale_seconds=180):
        return 0

    # 추가 진단 정보 출력
    status = health.read()
    if status is None:
        print("UNHEALTHY: 상태 파일 없음", file=sys.stderr)
    elif status.get("state") == "error":
        print(f"UNHEALTHY: 에러 상태 - {status.get('details', {})}", file=sys.stderr)
    else:
        print(f"UNHEALTHY: 상태 파일 오래됨 (timestamp: {status.get('timestamp')})", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
