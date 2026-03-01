# 운영 안정성 개선 계획

## Context

스케줄러(`scheduler.py`)가 24/7 Docker 환경에서 운영되는데, 크래시 후 수동 복구 필요, 상태 파악 어려움, 이상 알림 부족, **세션 제어 수단 부재**가 주요 불편 사항. 기존 코드에 `recover_zombie_sessions()`, `CircuitBreaker` 등 미사용 인프라가 이미 존재하므로 이를 활성화하고, 부족한 부분만 추가 구현한다.

**환경**: Docker + 직접 실행 모두 지원 / **알림**: Slack 기반 / **제어**: SQLite 기반 관리 CLI

---

## Phase 1: 크래시 복구 + 상태 파일 + 관리 CLI (기반 인프라)

### 1-1. `trading_bot/health.py` 신규 생성
- `SchedulerHealth` 클래스: JSON 상태 파일(`data/scheduler_status.json`) 관리
- `update(state, details)`: 상태 원자적 기록 (tmp+rename)
- `read()`: 현재 상태 조회
- `is_healthy(max_stale_seconds)`: 상태 파일 신선도 기반 헬스체크
- 상태값: `starting`, `idle`, `optimizing`, `trading`, `stopping`, `error`
- 세션 정보 포함: 각 trader 라벨, alive 여부, 시작 시간

### 1-2. `scheduler.py` 수정 - 시작 시 복구
- `main()` 시작부에 `db.recover_zombie_sessions()` 호출 (database.py:477에 이미 구현됨)
- 복구된 세션 수 로깅 + Slack 알림
- `SchedulerHealth` 초기화 + `starting` 상태 기록
- 시작 완료 시 Slack 알림 (PID, 프리셋 수, 복구 세션 수)

### 1-3. `scheduler.py` 수정 - 하트비트 잡
- 60초 interval APScheduler 잡 추가 (`_heartbeat`)
- 상태 파일에 현재 시각 + 활성 세션 정보 기록
- 각 주요 함수에서도 상태 업데이트 (optimize→`optimizing`, start→`trading`, stop→`stopping`)

### 1-4. `trading_bot/database.py` 수정 - 제어 명령 테이블
- `scheduler_commands` 테이블 추가 (id, command, target_label, created_at, processed_at)
- 명령 종류: `stop_session`, `cleanup_zombies`, `status_dump`
- `insert_command(command, target_label)`: 명령 삽입
- `get_pending_commands()`: 미처리 명령 조회
- `mark_command_processed(command_id)`: 처리 완료 마킹

### 1-5. `scheduler.py` 수정 - 관리 CLI 모드
별도 프로세스로 실행되어 DB에 명령을 기록하거나, 상태를 즉시 조회:

```bash
# 활성 세션 + 스케줄러 상태 한눈에 확인
python scheduler.py --status

# 특정 세션 중지 명령 전송 (스케줄러가 다음 하트비트에서 처리)
python scheduler.py --stop "0221 AAPL - RSI Strategy"

# 좀비 세션 정리 (즉시 DB 업데이트)
python scheduler.py --cleanup

# 전체 세션 중지 명령
python scheduler.py --stop-all
```

- `--status`: 상태 파일 + DB 세션 테이블 직접 조회 → 테이블 형태 출력 (즉시 반환, 스케줄러 프로세스와 무관)
- `--stop <label>`: DB에 `stop_session` 명령 삽입 → 스케줄러 하트비트(60초)에서 수신 후 해당 세션 중지
- `--cleanup`: `recover_zombie_sessions()` 직접 호출 (즉시 실행)
- `--stop-all`: DB에 전체 세션에 대한 stop 명령 삽입

### 1-6. `scheduler.py` 수정 - 하트비트에서 제어 명령 폴링
- `_heartbeat()` 함수에서 `get_pending_commands()` 호출
- 명령별 처리: stop_session → `_stop_single_session(label)` 호출, cleanup → `recover_zombie_sessions()`
- 처리 후 `mark_command_processed()` 호출
- 최대 세션 수 제한: `--max-sessions N` 옵션 추가, 초과 시 세션 시작 거부

**수정 파일**: `scheduler.py`, `trading_bot/database.py`
**신규 파일**: `trading_bot/health.py`

---

## Phase 2: 워치독 + 스레드 감시

### 2-1. `scheduler.py` 수정 - 워치독 잡
- 2분 interval APScheduler 잡 (`_watchdog`)
- `trader_threads`에서 죽은 스레드 감지 → `active_traders`에서 제거
- DB 세션 상태를 `interrupted`로 업데이트
- Slack 에러 알림 전송
- 상태 파일 갱신

### 2-2. `trading_bot/paper_trader.py` 수정 - CircuitBreaker 통합
- `__init__`에 `CircuitBreaker(failure_threshold=5, timeout=120.0)` 인스턴스 추가
- `_fetch_ticker_with_retry`, `_fetch_ohlcv_with_retry` 메서드에 CircuitBreaker 래핑
- 5회 연속 실패 시 120초간 해당 API 호출 차단 → 불필요한 재시도 방지
- 기존 `retry_with_backoff` 데코레이터와 조합 (CircuitBreaker가 outer)

### 2-3. `trading_bot/paper_trader.py` 수정 - 메모리 캡
- `equity_history` 리스트에 최대 길이 제한 (5000개, ~83시간분)
- `_realtime_iteration()` 에서 append 후 초과분 trim

**수정 파일**: `scheduler.py`, `trading_bot/paper_trader.py`

---

## Phase 3: 알림 강화

### 3-1. `trading_bot/notifications.py` 수정 - Slack 재시도
- `send_slack()`에 retry 로직 추가 (최대 3회, backoff 5s→10s→20s)
- 기존 `retry_with_backoff`를 내부 함수에 적용
- 최종 실패 시 로그 기록 (기존과 동일하게 False 반환)

### 3-2. `trading_bot/notifications.py` 수정 - 에러 에스컬레이션
- `_error_count` 카운터 추가
- 3회 연속 에러 시 메시지에 `[CRITICAL]` 접두사 추가
- `reset_error_count()` 메서드 추가 (정상 동작 복귀 시 호출)
- 스케줄러 하트비트에서 활성 세션이 정상일 때 리셋

### 3-3. `trading_bot/anomaly_detector.py` 신규 생성
- `AnomalyDetector` 클래스: 운영 이상 감지
- 검사 항목:
  - `equity_history` 크기 과다 (메모리 누수 징후)
  - DB 파일 크기 과다 (500MB 초과)
  - 오래된 마지막 거래 시간 (4시간 이상 거래 없음)
- `check_all(traders, db_path)` → 알림 메시지 리스트 반환
- 스케줄러 워치독(`_watchdog`)에서 주기적 호출

**수정 파일**: `trading_bot/notifications.py`, `scheduler.py`
**신규 파일**: `trading_bot/anomaly_detector.py`

---

## Phase 4: DB 유지보수 + Docker 헬스체크

### 4-1. `trading_bot/database.py` 수정 - 유지보수 메서드 추가
- `prune_old_data(days_to_keep=30)`: 완료/중단된 세션의 스냅샷, 시그널 삭제 (세션/거래 레코드는 유지)
- `vacuum()`: VACUUM 실행으로 파일 크기 최적화
- `backup(backup_dir='data/backups')`: WAL 체크포인트 후 파일 복사

### 4-2. `scheduler.py` 수정 - 주간 DB 유지보수 잡
- 매주 일요일 12:00 KST CronTrigger
- 순서: backup → prune → vacuum
- 완료/실패 Slack 알림

### 4-3. Docker 헬스체크 개선
- `scripts/healthcheck.py` 신규 생성: 상태 파일 기반 헬스체크 스크립트
- `docker-compose.yml` 수정: `pgrep` → `python scripts/healthcheck.py`

**수정 파일**: `trading_bot/database.py`, `scheduler.py`, `docker-compose.yml`
**신규 파일**: `scripts/healthcheck.py`

---

## 신규 파일 요약

| 파일 | 목적 | Phase |
|------|------|-------|
| `trading_bot/health.py` | 스케줄러 상태 파일 관리 | 1 |
| `trading_bot/anomaly_detector.py` | 운영 이상 감지 | 3 |
| `scripts/healthcheck.py` | Docker 헬스체크 스크립트 | 4 |
| `tests/test_health.py` | health.py 테스트 | 1 |
| `tests/test_scheduler_cli.py` | 관리 CLI (--status/--stop/--cleanup) 테스트 | 1 |
| `tests/test_anomaly_detector.py` | anomaly_detector.py 테스트 | 3 |
| `tests/test_db_maintenance.py` | DB 유지보수 테스트 | 4 |

## 수정 파일 요약

| 파일 | 변경 내용 | Phase |
|------|----------|-------|
| `scheduler.py` | 좀비 복구, 관리 CLI (--status/--stop/--cleanup/--stop-all/--max-sessions), 하트비트+명령 폴링, 워치독, DB 유지보수 잡, 시작 알림 | 1,2,3,4 |
| `trading_bot/database.py` | scheduler_commands 테이블, 제어 명령 CRUD, prune, vacuum, backup 메서드 | 1,4 |
| `trading_bot/paper_trader.py` | CircuitBreaker 통합, equity_history 캡 | 2 |
| `trading_bot/notifications.py` | Slack 재시도, 에러 에스컬레이션 | 3 |
| `docker-compose.yml` | 헬스체크 스크립트로 교체 | 4 |

## 검증 방법

1. **Phase 1**:
   - 스케줄러 시작 → `data/scheduler_status.json` 생성 확인
   - DB에 좀비 세션 삽입 후 재시작 → 복구 확인
   - `python scheduler.py --status` → 활성 세션 테이블 출력 확인
   - `python scheduler.py --stop <label>` → DB에 명령 삽입 확인 → 하트비트 후 세션 중지 확인
   - `python scheduler.py --cleanup` → 좀비 세션 즉시 정리 확인
2. **Phase 2**: mock 브로커로 5회 연속 실패 → CircuitBreaker OPEN 확인, 스레드 강제 종료 → 워치독 감지 확인
3. **Phase 3**: Slack webhook 일시 차단 → 재시도 3회 확인, 연속 에러 → CRITICAL 에스컬레이션 확인
4. **Phase 4**: 30일 이전 세션 데이터 삽입 → prune 후 삭제 확인, VACUUM 후 파일 크기 감소 확인
5. **전체 테스트**: `pytest tests/test_health.py tests/test_anomaly_detector.py tests/test_db_maintenance.py tests/test_scheduler_cli.py -v`
