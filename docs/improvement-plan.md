# 프로젝트 개선 계획서

> **브랜치**: `feat/project-improvements`
> **생성일**: 2026-03-03
> **분석 기반**: 전체 코드베이스 종합 분석 (51,772줄, 179 파일)

---

## Phase 0: 치명적 버그 수정 (P0) — 예상 ~9시간

### Task 0-1: RateLimiter 스레드 안전성 확보
- **파일**: `trading_bot/brokers/korea_investment_broker.py`
- **문제**: `RateLimiter.wait()`에 Lock 없음. 멀티 프리셋 실행 시 레이스 컨디션 → API 차단
- **작업**:
  - [x] `threading.RLock` 추가
  - [x] 프리셋 간 브로커 인스턴스 공유 옵션 추가 (scheduler_state.py)
  - [x] 테스트: 멀티스레드 환경에서 rate limit 준수 확인 (5건 통과)

### Task 0-2: PaperTrader 메모리 누수 수정
- **파일**: `trading_bot/paper_trader.py`
- **문제**: `equity_history`에 매 iteration 데이터 추가되지만 MAX_SIZE 초과 시 트리밍 없음
- **작업**:
  - [x] `update()` 메서드에서 직접 append 대신 `PortfolioManager.record_equity()` 사용으로 수정 (트리밍 로직 활용)
  - [x] 테스트: 5000건 초과 시 자동 트리밍 확인 (4건 통과)

### Task 0-3: Stop Loss/Take Profit 경쟁 조건 수정
- **파일**: `trading_bot/paper_trader.py`
- **문제**: `_check_stop_loss_take_profit()`에서 포지션 확인 시 Lock 미획득
- **작업**:
  - [x] Lock 범위를 포지션 확인 시점으로 확장 (RLock reentrant 활용)
  - [x] 테스트: 동시 매도 시나리오 검증 (6건 통과)

### Task 0-4: VBTBacktester 인터페이스 호환성 수정
- **파일**: `trading_bot/vbt_backtester.py`
- **문제**: `self.trades` 항상 빈 배열, `equity_curve`가 `List[float]`만 반환
- **작업**:
  - [x] VBT trade records에서 trades 리스트 추출 (`_extract_trades()` 메서드 추가)
  - [x] equity_curve를 `List[Dict]` (timestamp, equity, price, position) 포맷으로 변환 (`_build_equity_curve()` 추가)
  - [x] 기존 Backtester와 동일한 결과 Dict 키 보장
  - [x] 테스트: VBT vs Legacy 결과 포맷 일치 검증 (15건 추가, 전체 37건 통과)

### Task 0-5: Notion Writer Worker-C 폴백 로직 수정
- **파일**: `scripts/notion_writer.py`
- **문제**: Worker-C 실패 시 플레이스홀더만 삽입, 레거시 폴백 미진입
- **작업**:
  - [x] Worker-C 실패 시 timeout/budget 2배로 재시도, 재시도 실패 시 레거시 폴백
  - [x] 알림 전송 (Slack `_notify_worker_failure()`) 추가
  - [x] 유효성 검증 항상 실행 (건너뜀 제거), worker_configs NameError 수정
  - [x] 테스트: Worker-C 타임아웃 시나리오 모킹 (6건 통과)

---

## Phase 1: 구조적 개선 (P1) — 예상 ~12시간

### Task 1-1: 전략 Divide-by-Zero 방어
- **파일들**:
  - `trading_bot/strategies/stochastic_strategy.py` — `(highest_high - lowest_low)` = 0
  - `trading_bot/strategies/bollinger_bands_strategy.py` — `(upper - lower)` = 0
  - `trading_bot/strategies/rsi_strategy.py` — `avg_losses` = 0
- **작업**:
  - [x] 각 전략에 `.replace(0, np.nan)` 방어 코드 추가 (RSI, Stochastic, Bollinger, RSI+MACD Combo)
  - [x] 테스트: 플랫 마켓(모든 가격 동일) 시나리오 (12건 통과)

### Task 1-2: 전략 공통 코드 BaseStrategy 통합
- **파일**: `trading_bot/strategies/base_strategy.py` + 모든 전략 파일
- **문제**: signal → position 변환 로직이 5개 전략에 동일 반복
- **작업**:
  - [x] `BaseStrategy.apply_position_tracking(data)` mixin 메서드 추가
  - [x] 각 전략에서 중복 코드 제거, mixin 호출로 대체 (Stochastic `.clip(lower=0).astype(int)` 누락 버그도 수정)
  - [ ] 전략 파라미터 생성자 검증 추가 (bounds, type) — 별도 태스크로 분리

### Task 1-3: DB 트랜잭션 격리
- **파일**: `trading_bot/paper_trader.py`
- **문제**: 상태 변경(Lock 내) → DB 쓰기(Lock 외) 사이 크래시 시 불일치
- **작업**:
  - [x] `execute_buy/sell` 내 `_log_trade()` + `db.log_trade()` 호출을 Lock 내부로 이동
  - [x] 테스트: Lock 내 DB 쓰기 호출 순서 검증 (기존 테스트 전체 통과)

### Task 1-4: Sharpe Ratio 동적 주기 계산
- **파일**: `trading_bot/backtester.py:247`
- **문제**: `np.sqrt(252)` 하드코딩 → 시간봉/주봉에서 부정확
- **작업**:
  - [x] `Backtester.__init__`에 `timeframe='1d'` 파라미터 추가 (하위 호환)
  - [x] `performance_calculator.ANNUALIZATION_FACTORS` 재사용으로 동적 계수 적용
  - [x] 테스트: timeframe별 Sharpe Ratio 배율 검증 (3건 통과)

### Task 1-5: 스케줄러 전역 상태 캡슐화
- **파일**: `trading_bot/scheduler/scheduler_state.py`, `session_manager.py`, `scheduler.py`(루트), `__init__.py`
- **문제**: 모듈 레벨 mutable dict → 테스트 격리 불가, 레이스 컨디션
- **작업**:
  - [x] `SchedulerContext` 클래스 생성 (13개 전역 변수 캡슐화)
  - [x] 하위 호환 모듈 레벨 별칭 유지 (mutable 객체), 재할당 변수(`max_sessions`, `global_broker`)는 `ctx.xxx` 사용
  - [x] `scheduler.py`, `session_manager.py`에서 `state.ctx.max_sessions`, `state.ctx.global_broker` 참조로 전환
  - [x] 테스트: `SchedulerContext` 독립 인스턴스 격리 확인 (기존 테스트 통과)

### Task 1-6: 대시보드 Streamlit 캐싱 적용
- **파일**: `dashboard/yfinance_helper.py`
- **문제**: `@st.cache_data` 미사용 → 매 rerun API 호출, UI 느림
- **작업**:
  - [x] `fetch_ticker_yfinance`, `fetch_ohlcv_yfinance`에 `@st.cache_data(ttl=60, show_spinner=False)` 적용
  - [x] KIS 브로커는 기존 `st.session_state` 패턴 유지 (안정적 동작 유지)

---

## Phase 2: 기능 추가 (P2) — 예상 ~25시간

### Task 2-1: 분석 → 트레이딩 Closed-Loop 연결
- **관련 파일**: `session_manager.py`, `paper_trader.py`, `market_intelligence/`
- **현재 상태**: Market Intelligence 결과(JSON)가 PaperTrader에 전달되지 않음
- **작업**:
  - [ ] 장 시작 시 최신 `data/market_analysis/{date}.json` 로드
  - [ ] Intelligence Score에 따른 포지션 사이즈 조절 (±20%)
  - [ ] Regime 변경 시 전략 전환 또는 신규 진입 중지

### Task 2-2: 동적 포지션 사이징
- **파일**: `trading_bot/paper_trader.py`, 새 `position_sizer.py`
- **작업**:
  - [ ] ATR 기반 변동성 조절 포지션 사이징
  - [ ] Kelly Criterion 옵션
  - [ ] 전략 설정에서 sizing_method 선택 가능

### Task 2-3: paper_trading.py 탭 리팩터링
- **파일**: `dashboard/tabs/paper_trading.py` (1,350줄)
- **작업**:
  - [ ] `paper_trading_controls.py` — 설정/시작/중지 (~350줄)
  - [ ] `paper_trading_monitor.py` — 실시간 모니터링 (~350줄)
  - [ ] `paper_trading_strategies.py` — 전략 선택 UI (~300줄)
  - [ ] `paper_trading_orders.py` — SL/TP/리밋 오더 (~300줄)

### Task 2-4: E2E 대시보드 테스트
- **작업**:
  - [ ] `tests/test_dashboard_e2e.py` 생성
  - [ ] Streamlit Testing Framework 활용
  - [ ] paper_trading 워크플로우 테스트
  - [ ] error_handler 단위 테스트 추가

### Task 2-5: CI/CD 강화
- **파일**: `.github/workflows/ci.yml`
- **작업**:
  - [ ] Python 3.10 → 3.11 업그레이드
  - [ ] flake8 linting 추가
  - [ ] mypy type checking 추가
  - [ ] pytest-timeout 추가

### Task 2-6: 구조화 로깅
- **작업**:
  - [ ] JSON 포맷 로깅 설정
  - [ ] 기존 f-string 로그를 structured extra 딕셔너리로 전환
  - [ ] Prometheus metrics endpoint (선택)

---

## Phase 3: 장기 과제 (P3) — 예상 ~40시간+

### Task 3-1: 멀티 타임프레임 분석
- 일봉 추세 확인 + 시간봉 진입 시그널 결합
- 전략 인터페이스 확장 필요

### Task 3-2: 멀티 전략 동시 실행
- 같은 심볼에 RSI + MACD 동시 실행
- 시그널 합의(consensus) 기반 매매

### Task 3-3: Walk-Forward 최적화
- In-sample/Out-of-sample 분할 검증
- Overfitting 방지

### Task 3-4: 이벤트 드리븐 아키텍처
- 60초 폴링 → 웹소켓/콜백 기반
- 지연시간 단축 + 불필요한 API 호출 제거

### Task 3-5: Short 포지션 지원
- 현재 long-only (position clip(lower=0))
- position = -1 지원

### Task 3-6: 뉴스 감성 분석
- NewsCollector에 FinBERT 기반 sentiment scoring 추가
- requirements-ml.txt 활용

---

## 실행 가이드

### 다음 세션에서 이어서 작업하기

```bash
# 1. 브랜치 확인 및 전환
git checkout feat/project-improvements

# 2. Claude Code에서 계획서 기반 작업 시작
# 아래 명령어 중 하나 사용:

# Phase 0 전체 실행 (치명적 버그 수정)
"docs/improvement-plan.md의 Phase 0 태스크를 순서대로 진행해줘"

# 특정 태스크만 실행
"docs/improvement-plan.md의 Task 0-1 (RateLimiter 스레드 안전성)을 수정해줘"

# 상태 확인
"docs/improvement-plan.md의 진행 상황을 확인해줘"
```

### Phase별 실행 순서

1. **Phase 0** → 프로덕션 안정성 확보 (먼저 완료 후 main 머지 권장)
2. **Phase 1** → 코드 품질 개선 (Phase 0 완료 후)
3. **Phase 2** → 새 기능 추가 (Phase 1 완료 후, 개별 PR 가능)
4. **Phase 3** → 장기 과제 (별도 브랜치에서 진행 권장)

---

## 참고: 분석에서 발견된 파일별 이슈 매핑

| 파일 | 이슈 | Phase |
|------|------|-------|
| `brokers/korea_investment_broker.py` | RateLimiter Lock 없음 | 0-1 |
| `paper_trader.py` | 메모리 누수, 레이스 컨디션, DB 격리 | 0-2, 0-3, 1-3 |
| `vbt_backtester.py` | trades 빈 배열, equity_curve 포맷 | 0-4 |
| `scripts/notion_writer.py` | Worker-C 폴백 미작동 | 0-5 |
| `strategies/*.py` | divide-by-zero, 공통 코드 중복 | 1-1, 1-2 |
| `backtester.py` | Sharpe 하드코딩 | 1-4 |
| `scheduler/scheduler_state.py` | 전역 mutable 상태 | 1-5 |
| `dashboard/tabs/paper_trading.py` | 1,350줄 모놀리식 | 2-3 |
| `dashboard/tabs/*.py` | 캐싱 미적용 | 1-6 |
| `.github/workflows/ci.yml` | Python 3.10, lint/type 없음 | 2-5 |
