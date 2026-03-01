# trading_bot/scheduler/ - 스케줄러 패키지

> **상위 문서**: [루트 CLAUDE.md](../../CLAUDE.md)를 먼저 참조하세요.

## 목적

모놀리식 `scheduler.py` (1402줄)를 책임별로 분리한 패키지:
- **scheduler_state.py**: 공유 전역 상태 (전략 매핑, 세션 관리, 알림 등)
- **scheduler_core.py**: APScheduler 잡 (하트비트, 워치독), CLI 핸들러, 시그널 핸들러
- **session_manager.py**: 페이퍼 트레이딩 세션 시작/중지/리포트, 시장 분석
- **db_maintenance.py**: DB 다운샘플링, 정리, VACUUM, 백업

## 디렉토리 구조

```
trading_bot/scheduler/
├── __init__.py              # 패키지 공개 API (모든 심볼 re-export)
├── scheduler_state.py       # 공유 전역 상태 및 상수
├── scheduler_core.py        # APScheduler 잡, CLI 핸들러
├── session_manager.py       # 세션 시작/중지/리포트
├── db_maintenance.py        # DB 유지보수
└── CLAUDE.md
```

## 진입점

`scheduler.py` (프로젝트 루트)가 thin entry point로 남아 있으며:
- CLI 인자 파싱 (`argparse`)
- APScheduler 잡 등록 및 시작
- 모든 심볼을 re-export하여 기존 `from scheduler import X` 호환 유지

## 테스트 패치 경로

모듈 분리 후 테스트에서 mock/patch 시 사용할 경로:
- `trading_bot.scheduler.scheduler_state.global_db` (DB 교체)
- `trading_bot.scheduler.session_manager._create_kis_broker` (브로커 모킹)
- `trading_bot.scheduler.session_manager._start_single_session` (세션 시작 모킹)
