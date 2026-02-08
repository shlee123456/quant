# PRD: Dashboard Live Quotes Integration

## Introduction

한국투자증권 브로커를 대시보드에 통합하여 미국 주식(NASDAQ, NYSE)의 실시간 시세를 조회하고 차트로 시각화하는 기능을 추가합니다. 사용자는 실시간 시세 데이터를 확인하면서 백테스팅 결과와 비교할 수 있으며, Auto-refresh 기능으로 자동 업데이트를 제어할 수 있습니다.

## Goals

- 한국투자증권 KoreaInvestmentBroker를 Streamlit 대시보드에 통합
- 미국 주식(NASDAQ, NYSE)의 실시간 시세 조회 기능 제공
- 현재가, OHLC, 차트를 시각화하여 표시
- Auto-refresh 토글로 사용자가 자동 업데이트를 제어
- 백테스팅 결과와 실시간 데이터를 함께 표시하여 비교 가능
- 새로운 "Real-time Quotes" 탭 추가로 전용 시세 조회 UI 제공

## User Stories

### US-001: 환경 변수 설정 가이드 추가
**Description:** As a user, I want clear instructions on setting up KIS API credentials so I can start using live quotes.

**Acceptance Criteria:**
- [ ] README.md에 한국투자증권 API 설정 섹션 추가
- [ ] .env.example 파일에 KIS_* 환경 변수 예시 추가
- [ ] 모의투자 vs 실전 계정 차이 설명 추가
- [ ] Typecheck passes

### US-002: KoreaInvestmentBroker 초기화 함수 추가
**Description:** As a developer, I need a helper function to initialize the KIS broker from environment variables.

**Acceptance Criteria:**
- [ ] `dashboard/kis_broker.py` 파일 생성
- [ ] `get_kis_broker()` 함수 구현 (환경 변수에서 인증 정보 로드)
- [ ] 환경 변수 누락 시 명확한 에러 메시지 표시
- [ ] 초기화 실패 시 None 반환 (graceful degradation)
- [ ] Docstring 작성
- [ ] Typecheck passes

### US-003: Real-time Quotes 탭 추가
**Description:** As a user, I want a dedicated tab for viewing real-time stock quotes.

**Acceptance Criteria:**
- [ ] `dashboard/app.py`에 "📊 Real-time Quotes" 탭 추가
- [ ] 탭 순서: Strategy → Backtesting → Live Monitor → **Real-time Quotes**
- [ ] 탭 선택 시 해당 페이지 렌더링
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-004: 종목 선택 UI 구현
**Description:** As a user, I want to search and select US stocks to view their quotes.

**Acceptance Criteria:**
- [ ] `dashboard/stock_symbols.py`의 미국 주식 리스트 재사용
- [ ] Streamlit selectbox로 종목 선택 UI 구성
- [ ] 종목 검색 가능 (심볼 또는 회사명)
- [ ] 선택된 종목은 session_state에 저장
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-005: 실시간 시세 조회 및 표시
**Description:** As a user, I want to see the current price and basic quote information for the selected stock.

**Acceptance Criteria:**
- [ ] KIS 브로커의 `fetch_ticker()` 메서드 호출
- [ ] 현재가, 시가, 고가, 저가, 거래량 표시
- [ ] 등락률을 색상으로 구분 (상승: 빨강, 하락: 파랑)
- [ ] Streamlit metrics로 깔끔하게 표시
- [ ] API 에러 시 사용자 친화적 에러 메시지 표시
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-006: OHLCV 차트 시각화
**Description:** As a user, I want to see a candlestick chart of historical prices for the selected stock.

**Acceptance Criteria:**
- [ ] KIS 브로커의 `fetch_ohlcv()` 메서드로 일봉 데이터 조회
- [ ] Plotly candlestick 차트로 시각화
- [ ] 차트에 거래량 표시 (서브플롯)
- [ ] 기간 선택 가능 (30일, 90일, 180일)
- [ ] 차트 로딩 시 spinner 표시
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-007: Auto-refresh 토글 기능
**Description:** As a user, I want to enable/disable automatic quote updates so I can control when data refreshes.

**Acceptance Criteria:**
- [ ] Streamlit checkbox로 Auto-refresh 토글 추가
- [ ] 토글 ON: 60초마다 자동 새로고침 (`st.rerun()` 사용)
- [ ] 토글 OFF: 수동 "Refresh" 버튼만 동작
- [ ] 토글 상태는 session_state에 저장
- [ ] 남은 시간 표시 (예: "Next refresh in 45s")
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-008: Live Monitor 탭 통합
**Description:** As a user, I want to see real-time quotes alongside backtesting results in the Live Monitor tab.

**Acceptance Criteria:**
- [ ] Live Monitor 탭에 "Current Market Price" 섹션 추가
- [ ] KIS 브로커로 현재가 조회 및 표시
- [ ] 백테스팅 결과와 동일한 종목의 실시간 시세 표시
- [ ] 시뮬레이션 모드 vs 실시간 모드 구분 UI
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-009: 에러 처리 및 fallback
**Description:** As a user, I want graceful error handling when API calls fail or credentials are missing.

**Acceptance Criteria:**
- [ ] KIS 브로커 초기화 실패 시 명확한 안내 메시지 표시
- [ ] API Rate Limit 에러 시 재시도 안내 표시
- [ ] 네트워크 에러 시 사용자 친화적 메시지 표시
- [ ] 환경 변수 누락 시 설정 가이드 링크 제공
- [ ] Typecheck passes
- [ ] Verify in browser using dev-browser skill

### US-010: 문서화 및 사용 가이드
**Description:** As a user, I want clear documentation on how to use the live quotes feature.

**Acceptance Criteria:**
- [ ] `dashboard/CLAUDE.md`에 KIS 브로커 통합 섹션 추가
- [ ] Real-time Quotes 탭 사용법 설명
- [ ] Auto-refresh 기능 설명
- [ ] 트러블슈팅 가이드 (API 에러, Rate Limit 등)
- [ ] Typecheck passes

## Functional Requirements

- FR-1: `dashboard/kis_broker.py` 모듈을 생성하여 KIS 브로커 초기화 함수 제공
- FR-2: 환경 변수(.env)에서 KIS API 인증 정보를 로드하여 브로커 초기화
- FR-3: "Real-time Quotes" 탭을 추가하여 전용 시세 조회 UI 제공
- FR-4: 미국 주식(NASDAQ, NYSE) 종목 선택 UI 제공
- FR-5: 선택된 종목의 현재가, OHLC, 거래량, 등락률 표시
- FR-6: Plotly candlestick 차트로 OHLCV 데이터 시각화
- FR-7: Auto-refresh 토글로 60초마다 자동 업데이트 제어
- FR-8: Live Monitor 탭에 실시간 시세 섹션 통합
- FR-9: 백테스팅 결과와 실시간 데이터 비교 표시
- FR-10: API 에러, Rate Limit, 환경 변수 누락 등 예외 처리

## Non-Goals (Out of Scope)

- 실제 주문 실행 기능 (이번 PRD에서는 시세 조회만)
- WebSocket 실시간 스트리밍 (HTTP polling 방식 사용)
- 국내 주식 지원 (미국 주식만)
- 복수 종목 동시 모니터링 (단일 종목만)
- 알림/경고 기능 (가격 알림 등)
- 차트 기술적 지표 추가 (볼린저 밴드, 이동평균 등)

## Design Considerations

### UI/UX Requirements

1. **Real-time Quotes 탭**
   - 종목 선택 (selectbox)
   - Auto-refresh 토글 (checkbox)
   - 수동 Refresh 버튼
   - 현재가 카드 (metrics)
   - OHLCV 차트 (plotly)

2. **Live Monitor 탭 통합**
   - 기존 백테스팅 결과 섹션 유지
   - 새로운 "Current Market Price" 섹션 추가
   - 실시간 데이터와 백테스팅 결과 비교 UI

3. **색상 구분**
   - 상승: 빨강 (#FF4B4B)
   - 하락: 파랑 (#1F77B4)
   - 중립: 회색 (#808080)

### 재사용 가능한 컴포넌트

- `dashboard/stock_symbols.py`: 미국 주식 리스트
- `dashboard/market_hours.py`: 시장 시간 표시
- Plotly 차트 설정 (기존 백테스팅 차트와 일관성)

## Technical Considerations

### Dependencies

- `trading_bot.brokers.KoreaInvestmentBroker`: 이미 구현 완료
- `python-kis>=2.1.6`: requirements.txt에 이미 추가됨
- `plotly`: Streamlit 대시보드에서 이미 사용 중

### Integration Points

1. **환경 변수 (.env)**
   - `KIS_ID`, `KIS_APPKEY`, `KIS_APPSECRET`, `KIS_ACCOUNT`, `KIS_MOCK`
   - `dashboard/kis_broker.py`에서 로드

2. **KoreaInvestmentBroker**
   - `fetch_ticker()`: 현재가 조회
   - `fetch_ohlcv()`: OHLCV 데이터 조회
   - Rate Limiter 자동 관리 (1초당 15회)

3. **Streamlit Session State**
   - 선택된 종목
   - Auto-refresh 상태
   - 마지막 업데이트 시간

### Performance Requirements

- API 호출 최소화 (캐싱 고려)
- 차트 렌더링 최적화 (데이터 양 제한)
- Rate Limit 준수 (KIS API: 1초당 15회)

### Error Handling

- API 에러: 사용자 친화적 메시지 + 재시도 안내
- Rate Limit: "1분 후 다시 시도하세요" 메시지
- 환경 변수 누락: README.md 링크 제공
- 네트워크 에러: "연결 실패" 메시지

## Success Metrics

- 사용자가 2클릭 내에 실시간 시세 확인 가능
- API 에러 발생 시 명확한 안내 메시지 표시
- Auto-refresh 기능이 안정적으로 동작 (60초마다)
- 차트 로딩 시간 3초 이내
- 백테스팅 결과와 실시간 데이터 비교 가능

## Open Questions

- [ ] 차트 기간 선택 UI는 어디에 배치할까? (selectbox vs slider)
- [ ] Auto-refresh 간격을 사용자가 조정 가능하게 할까? (30초/60초/120초)
- [ ] 복수 종목 위젯리스트 기능은 나중에 추가할까?
- [ ] Rate Limit 에러 시 자동으로 재시도할까, 수동으로 할까?

## Branch Name

`feature/dashboard-live-quotes`

## Estimated Effort

- US-001 ~ US-002: 0.5시간 (환경 설정 및 헬퍼 함수)
- US-003 ~ US-004: 1시간 (탭 추가 및 종목 선택 UI)
- US-005 ~ US-006: 2시간 (시세 조회 및 차트 구현)
- US-007: 1시간 (Auto-refresh 기능)
- US-008: 1시간 (Live Monitor 통합)
- US-009 ~ US-010: 1시간 (에러 처리 및 문서화)

**Total**: ~6.5시간
