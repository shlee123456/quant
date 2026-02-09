# dashboard/ - Streamlit 대시보드

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, Streamlit 대시보드에 특화된 규칙만 정의합니다.

---

## 목적

실시간 트레이딩 모니터링 및 분석을 위한 웹 대시보드:
- **백테스팅 결과 시각화**: 수익 곡선, 거래 내역
- **전략 비교**: 여러 전략 성능 비교
- **실시간 모니터링**: 페이퍼 트레이딩 현황
- **다국어 지원**: 한국어/영어

---

## 디렉토리 구조

```
dashboard/
├── __init__.py
├── app.py              # Streamlit 메인 앱
├── charts.py           # Plotly 차트 생성
├── translations.py     # 다국어 지원
└── README.md           # 대시보드 사용 설명서
```

---

## 주요 파일

### `app.py` - 메인 애플리케이션

**역할**:
- Streamlit 앱 진입점
- 페이지 레이아웃 구성
- 사이드바: 전략 선택, 파라미터 입력
- 메인: 백테스팅 결과, 차트 표시

**실행 명령어**:
```bash
streamlit run dashboard/app.py 2>&1 | tee .context/terminal/dashboard_$(date +%s).log
```

**환경 설정**:
- 포트: 8501 (기본)
- 브라우저 자동 실행: 활성화

---

### `charts.py` - 차트 생성

**역할**:
- Plotly를 사용한 인터랙티브 차트 생성
- 수익 곡선, 드로우다운, 거래 내역 시각화

**주요 함수**:
```python
def create_equity_curve_chart(data: pd.DataFrame) -> go.Figure:
    """수익 곡선 차트 생성"""
    pass

def create_drawdown_chart(data: pd.DataFrame) -> go.Figure:
    """드로우다운 차트 생성"""
    pass

def create_trades_chart(data: pd.DataFrame) -> go.Figure:
    """거래 내역 차트 (캔들스틱 + 매매 지점)"""
    pass
```

---

### `translations.py` - 다국어 지원

**역할**:
- 한국어/영어 UI 문구 관리
- 세션 상태 기반 언어 전환

**사용 예시**:
```python
from dashboard.translations import get_text

lang = st.session_state.get('language', 'ko')
st.title(get_text('dashboard_title', lang))
```

---

## 로컬 코딩 컨벤션

### Streamlit 세션 상태 관리

```python
# 세션 상태 초기화
if 'backtest_results' not in st.session_state:
    st.session_state.backtest_results = None

# 세션 상태 업데이트
st.session_state.backtest_results = results
```

### 차트 스타일 가이드

**통일된 색상 팔레트**:
- Primary: `#1f77b4` (파란색)
- Success: `#2ca02c` (초록색)
- Error: `#d62728` (빨간색)
- Warning: `#ff7f0e` (주황색)

**차트 레이아웃**:
```python
layout = go.Layout(
    template='plotly_white',
    hovermode='x unified',
    showlegend=True,
    height=500
)
```

### 성능 최적화

**캐싱 사용**:
```python
@st.cache_data
def load_simulation_data(periods: int, trend: str) -> pd.DataFrame:
    """시뮬레이션 데이터 캐싱"""
    data_gen = SimulationDataGenerator(seed=42)
    return data_gen.generate_trend_data(periods=periods, trend=trend)
```

**대용량 데이터 처리**:
- 1000개 이상 데이터 포인트는 샘플링
- 차트 렌더링 시간 1초 이하 유지

---

## 페이지 구성

### 1. 사이드바 (Sidebar)

**구성 요소**:
- 언어 선택 (한국어/English)
- 마켓 선택 (암호화폐/해외주식)
- 전략 선택 (RSI, MACD, MA, Bollinger Bands, Stochastic)
- 파라미터 입력 (전략별)
- 백테스팅 실행 버튼

**예시 코드**:
```python
with st.sidebar:
    st.header(get_text('settings', lang))
    
    # 마켓 선택
    market = st.selectbox(
        get_text('select_market', lang),
        ['Cryptocurrency', 'Foreign Stocks']
    )
    
    # 전략 선택
    strategy_name = st.selectbox(
        get_text('select_strategy', lang),
        ['RSI', 'MACD', 'MA Crossover']
    )
    
    # 파라미터 입력 (전략별 동적 생성)
    if strategy_name == 'RSI':
        period = st.slider('RSI Period', 7, 28, 14)
        overbought = st.slider('Overbought', 60, 90, 70)
        oversold = st.slider('Oversold', 10, 40, 30)
```

---

### 2. 메인 영역 (Main)

**구성 요소**:
1. **헤더**: 타이틀, 설명
2. **성능 메트릭**: Total Return, Sharpe Ratio, Max Drawdown, Win Rate
3. **수익 곡선 차트**: 시간별 자본 변화
4. **드로우다운 차트**: 최고점 대비 하락폭
5. **거래 내역 차트**: 캔들스틱 + 매매 지점
6. **거래 상세 테이블**: 개별 거래 내역

**예시 코드**:
```python
# 메트릭 표시
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric('Total Return', f"{results['total_return']:.2f}%")
with col2:
    st.metric('Sharpe Ratio', f"{results['sharpe_ratio']:.2f}")
with col3:
    st.metric('Max Drawdown', f"{results['max_drawdown']:.2f}%")
with col4:
    st.metric('Win Rate', f"{results['win_rate']:.2f}%")

# 차트 표시
st.plotly_chart(create_equity_curve_chart(data), use_container_width=True)
st.plotly_chart(create_drawdown_chart(data), use_container_width=True)
```

---

## 마켓별 UI 차이점

### 암호화폐 대시보드
- **시간 단위**: 1분, 5분, 15분, 1시간, 4시간, 1일
- **거래소 선택**: Binance, Upbit, Coinbase 등
- **24/7 데이터**: 주말 포함

### 해외주식 대시보드
- **시간 단위**: 1분, 5분, 15분, 1시간, 1일
- **증권사 선택**: Interactive Brokers, 키움증권 등
- **거래 시간 표시**: 장중/장외 구분

---

## 에러 핸들링

### 사용자 입력 검증

```python
# 파라미터 범위 체크
if period < 1 or period > 100:
    st.error(get_text('invalid_period', lang))
    st.stop()

# 데이터 로드 실패
try:
    df = load_data(symbol, timeframe)
except Exception as e:
    st.error(f"{get_text('data_load_error', lang)}: {str(e)}")
    st.stop()
```

### 백테스팅 에러

```python
try:
    results = backtester.run(df)
except Exception as e:
    st.error(f"{get_text('backtest_error', lang)}: {str(e)}")
    st.exception(e)  # 디버깅용 스택 트레이스
```

---

## 다국어 지원

### 번역 파일 구조

```python
# translations.py
TRANSLATIONS = {
    'ko': {
        'dashboard_title': '암호화폐 & 해외주식 트레이딩 봇 대시보드',
        'select_market': '마켓 선택',
        'select_strategy': '전략 선택',
        'run_backtest': '백테스트 실행',
        # ...
    },
    'en': {
        'dashboard_title': 'Crypto & Foreign Stock Trading Bot Dashboard',
        'select_market': 'Select Market',
        'select_strategy': 'Select Strategy',
        'run_backtest': 'Run Backtest',
        # ...
    }
}
```

### 새 번역 추가

1. `translations.py`에 한국어/영어 문구 추가
2. 키는 `snake_case` 사용
3. 문맥을 고려한 자연스러운 번역

---

## 테스트

### 수동 테스트 체크리스트

- [ ] 각 전략이 올바르게 실행되는가?
- [ ] 차트가 정확하게 표시되는가?
- [ ] 파라미터 변경 시 즉시 반영되는가?
- [ ] 언어 전환이 정상 작동하는가?
- [ ] 에러 메시지가 명확한가?

### 자동 테스트

```python
# tests/test_dashboard_integration.py
def test_dashboard_loads():
    """대시보드가 정상적으로 로드되는지 테스트"""
    pass

def test_backtest_execution():
    """백테스트가 정상 실행되는지 테스트"""
    pass
```

---

## 실행 명령어

```bash
# 로컬 개발 서버
streamlit run dashboard/app.py 2>&1 | tee .context/terminal/dashboard_$(date +%s).log

# 특정 포트 지정
streamlit run dashboard/app.py --server.port 8502 2>&1 | tee .context/terminal/dashboard_$(date +%s).log

# 브라우저 자동 실행 비활성화
streamlit run dashboard/app.py --server.headless true 2>&1 | tee .context/terminal/dashboard_$(date +%s).log
```

---

## KIS 브로커 통합 (US-001~US-010)

### 개요

한국투자증권 API를 통해 미국 주식의 실시간 시세를 조회하고 대시보드에 표시합니다.

**지원 기능**:
- 실시간 주식 시세 조회 (현재가, 시가, 고가, 저가, 거래량)
- OHLCV 차트 시각화 (캔들스틱 + 거래량)
- 자동 새로고침 (60초 간격)
- Live Monitor 탭 통합
- 에러 처리 및 사용자 친화적 메시지

---

### Real-time Quotes 탭 사용법

#### 1. 환경 변수 설정

`.env` 파일에 한국투자증권 API 인증 정보를 설정합니다:

```bash
# Korea Investment Securities API
KIS_APPKEY=your_app_key_here
KIS_APPSECRET=your_app_secret_here
KIS_ACCOUNT=12345678-01
KIS_USER_ID=user123  # 선택, 미입력 시 KIS_ACCOUNT 사용
KIS_MOCK=true  # 모의투자: true, 실전투자: false
```

**설정 방법**:
1. [한국투자증권 홈페이지](https://securities.koreainvestment.com)에서 API 신청
2. 발급받은 APPKEY와 APPSECRET을 `.env` 파일에 입력
3. 모의투자와 실전투자의 키가 다르므로 `KIS_MOCK` 설정 확인
4. 자세한 내용은 [README.md의 API Setup 섹션](../README.md#korea-investment-securities-api-setup) 참조

#### 2. 종목 선택

**기능**:
- 33개 인기 미국 주식 지원 (AAPL, MSFT, GOOGL, TSLA 등)
- 검색 가능한 드롭다운 (심볼 또는 회사명으로 검색)
- 섹터/산업 정보 표시

**사용법**:
```python
# 종목 선택 UI (app.py 내부)
selected_option = st.selectbox(
    get_text('stock_symbol', lang),
    stock_options,  # "AAPL - Apple Inc." 형식
    help=get_text('select_stock_help', lang)
)
```

#### 3. 실시간 시세 표시

**표시 항목**:
- **현재가**: 등락률과 함께 표시 (🔴 상승, 🔵 하락)
- **시가**: 당일 첫 거래가
- **고가**: 당일 최고가
- **저가**: 당일 최저가
- **거래량**: 당일 누적 거래량

**데이터 갱신**:
- 수동: "Refresh Now" 버튼 클릭
- 자동: Auto-refresh 체크박스 활성화 (60초 간격)

#### 4. Auto-refresh 기능

**사용법**:
1. "Enable Auto-refresh" 체크박스를 활성화
2. 60초마다 자동으로 시세 갱신
3. 카운트다운 타이머 표시 ("Next refresh in 45s")
4. "Refresh Now" 버튼으로 즉시 갱신 가능
5. 체크박스 비활성화로 자동 갱신 중지

**구현 패턴**:
```python
# Auto-refresh 상태 관리
if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = False

if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = None

# 자동 갱신 로직
if st.session_state.auto_refresh_enabled:
    elapsed = time.time() - st.session_state.last_refresh_time
    if elapsed >= 60:
        st.session_state.last_refresh_time = time.time()
        st.rerun()
```

#### 5. OHLCV 차트

**기능**:
- 캔들스틱 차트 (가격)
- 거래량 차트 (서브플롯)
- 기간 선택: 30일, 90일, 180일

**차트 특징**:
- 상승일: 초록색 캔들/거래량
- 하락일: 빨간색 캔들/거래량
- 인터랙티브 줌/패닝
- 통합 호버모드

---

### Live Monitor 탭 통합

**기능**:
- 실시간 시세와 백테스팅 결과를 함께 표시
- 시뮬레이션 모드 vs 실시간 모드 UI 구분
- 데이터 소스 표시 (KIS 브로커/거래소/시뮬레이션)

**Current Market Price 섹션**:
- Live Monitor 탭 상단에 표시
- 주식 마켓 + 비시뮬레이션 모드에서만 활성화
- 현재가, 시가, 고가, 저가, 거래량 표시
- 마지막 업데이트 시간 표시

**조건부 표시**:
```python
if st.session_state.market_type == 'stock' and not st.session_state.use_simulation:
    # Current Market Price 섹션 표시
    # KIS 브로커로 실시간 시세 조회
    pass
else:
    # 시뮬레이션 모드 또는 암호화폐 마켓
    # 전략 신호만 표시
    pass
```

---

### 에러 처리 및 트러블슈팅

#### 중앙 집중식 에러 핸들러

**모듈**: `dashboard/error_handler.py`

**기능**:
- 자동 에러 타입 감지
- 사용자 친화적 메시지 생성
- 해결 방법 제시

**에러 타입**:

##### 1. Rate Limit 에러
```
⏱️ API 호출 제한 초과
API 요청을 너무 많이 했습니다. 잠시 후 다시 시도해주세요.

해결 방법:
- ⏰ 1-2분 후 재시도
- API 호출 제한 초과 (1분 대기)
```

##### 2. 네트워크 에러
```
🌐 네트워크 연결 오류
API 서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.

해결 방법:
- 네트워크 연결 문제
- VPN을 사용 중이라면 비활성화해보세요
- 방화벽 설정을 확인하세요
```

##### 3. 인증 에러
```
🔐 인증 실패
API 인증 정보가 올바르지 않습니다. API 키를 확인해주세요.

해결 방법:
- .env 파일에서 API 인증 정보를 확인하세요
- 📖 README에서 API 설정 방법 보기
- API 키가 만료되었는지 확인하세요
```

##### 4. 잘못된 종목 코드
```
❓ 잘못된 종목 코드
입력한 종목 코드가 존재하지 않거나 지원되지 않습니다.

해결 방법:
- 잘못된 종목 코드 또는 장 마감
- 지원되는 종목 코드 목록을 확인하세요
- 종목 코드 철자를 확인하세요
```

##### 5. 장 마감 에러
```
🕐 장 마감
현재 시장이 마감되었습니다. 실시간 시세를 조회할 수 없습니다.

해결 방법:
- 미국 시장 정규장: 23:30-06:00 (KST)
- 프리마켓/애프터아워 시간대에는 시세가 제한적일 수 있습니다
```

#### 에러 핸들러 사용법

```python
from dashboard.error_handler import handle_kis_broker_error

try:
    ticker = broker.fetch_ticker(symbol, overseas=True)
except Exception as e:
    handle_kis_broker_error(e, lang=lang, symbol=symbol)
```

#### 환경 변수 누락 시

KIS 브로커 초기화 실패 시 자동으로 표시:
- 누락된 환경 변수 목록
- 설정 방법 안내
- README 링크
- 한국투자증권 API 신청 링크

---

### 코딩 패턴

#### KIS 브로커 초기화

```python
from dashboard.kis_broker import get_kis_broker

# 브로커 가져오기 (환경 변수에서 자동 초기화)
broker = get_kis_broker()

if broker is None:
    # 초기화 실패 (에러 메시지는 get_kis_broker가 이미 표시)
    st.warning(get_text('kis_not_available', lang))
    return

# 브로커 사용
ticker = broker.fetch_ticker('AAPL', overseas=True, market='NASDAQ')
```

#### 미국 주식 시세 조회

```python
# 실시간 시세
ticker = broker.fetch_ticker(
    symbol='AAPL',
    overseas=True,
    market='NASDAQ'  # 또는 'NYSE', 'AMEX'
)

# ticker 구조:
# {
#     'symbol': 'AAPL',
#     'last': 150.25,
#     'open': 149.50,
#     'high': 151.00,
#     'low': 149.00,
#     'volume': 50000000,
#     'change': 0.75,
#     'rate': 0.50,
#     'timestamp': '2024-01-01 10:30:00'
# }
```

#### OHLCV 데이터 조회

```python
# 일봉 데이터
df = broker.fetch_ohlcv(
    symbol='AAPL',
    timeframe='1d',
    limit=90,  # 90일
    overseas=True,
    market='NASDAQ'
)

# DataFrame 구조:
# timestamp | open | high | low | close | volume
```

---

### 성능 및 제한 사항

#### API Rate Limit

- 한국투자증권 API는 호출 제한이 있습니다
- 제한 초과 시 자동으로 에러 핸들러가 안내 표시
- Auto-refresh는 60초 간격으로 설정 (제한 회피)

#### 캐싱 전략

현재는 캐싱 미사용 (실시간 데이터이므로):
```python
# 향후 개선: 단기 캐싱으로 중복 호출 방지
@st.cache_data(ttl=60)  # 60초 캐시
def fetch_ticker_cached(symbol):
    broker = get_kis_broker()
    return broker.fetch_ticker(symbol, overseas=True)
```

#### 지원 종목

현재 33개 미국 주식 지원:
- 테크: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA 등
- 금융: JPM, BAC, WFC, GS 등
- 소비재: KO, PEP, NKE, MCD 등
- 헬스케어: JNJ, PFE, UNH 등

목록은 `dashboard/stock_symbols.py`에서 관리

---

### 테스트

#### 수동 테스트 체크리스트

**Real-time Quotes 탭**:
- [ ] 종목 선택 UI가 정상 작동하는가?
- [ ] 실시간 시세가 정확하게 표시되는가?
- [ ] Auto-refresh가 60초마다 갱신되는가?
- [ ] OHLCV 차트가 올바르게 표시되는가?
- [ ] 기간 선택이 차트에 반영되는가?

**Live Monitor 탭**:
- [ ] Current Market Price 섹션이 표시되는가?
- [ ] 시뮬레이션 모드에서 적절히 숨겨지는가?
- [ ] 실시간 시세와 백테스팅 결과가 함께 보이는가?

**에러 처리**:
- [ ] 환경 변수 누락 시 안내 메시지가 표시되는가?
- [ ] Rate Limit 에러 시 적절한 안내가 표시되는가?
- [ ] 네트워크 에러 시 해결 방법이 제시되는가?

---

## Paper Trading 탭 (Phase 1 완료 ✅)

### 개요

실시간 시장 데이터를 사용한 모의투자 실행 및 모니터링

**지원 기능**:
- 전략 선택 (RSI, MACD, MA, Bollinger Bands, Stochastic)
- 멀티 심볼 선택 (최대 7종목 동시)
- 실시간 포트폴리오 모니터링 (10초 자동 새로고침)
- 세션 시작/중지 제어
- 데이터베이스 연동 (세션 추적)
- **전략 프리셋 관리** (저장/불러오기)
- **Stop Loss/Take Profit 설정**

---

### Strategy Preset Management (💾 전략 프리셋 관리)

#### 개요

전략 설정을 프리셋으로 저장하고 불러오는 기능으로, 매번 파라미터를 수동으로 조정할 필요가 없습니다.

**위치**: Paper Trading 탭 상단

**주요 기능**:
- 현재 설정을 프리셋으로 저장
- 저장된 프리셋 불러오기
- 프리셋 삭제
- 프리셋 상세 정보 표시

#### UI 구성

##### 1. 프리셋 불러오기

```python
# 드롭다운에서 프리셋 선택
preset_names = manager.list_presets()
selected_preset = st.selectbox(
    "Select Preset",
    ["(새 설정)"] + preset_names,
    help="저장된 전략 프리셋을 선택하세요"
)

# 불러오기 버튼
if st.button("불러오기", disabled=(selected_preset == "(새 설정)")):
    preset = manager.load_preset(selected_preset)

    # 프리셋 데이터를 세션 상태에 저장
    st.session_state.preset_strategy = preset['strategy']
    st.session_state.preset_params = preset['strategy_params']
    st.session_state.preset_symbols = preset['symbols']
    st.session_state.preset_capital = preset['initial_capital']
    st.session_state.preset_position_size = preset['position_size']
    st.session_state.preset_stop_loss = preset.get('stop_loss_pct', 0.0)
    st.session_state.preset_take_profit = preset.get('take_profit_pct', 0.0)

    st.success(f"프리셋 '{selected_preset}' 불러오기 완료")
    st.rerun()  # UI 업데이트
```

##### 2. 프리셋 저장

```python
# 프리셋 이름 입력
preset_name = st.text_input(
    "Preset Name",
    placeholder="예: 보수적 RSI 전략",
    help="저장할 프리셋 이름을 입력하세요"
)

# 프리셋 설명 (선택)
preset_description = st.text_area(
    "Description (Optional)",
    placeholder="예: 안정적 수익을 위한 보수적 RSI 설정",
    help="프리셋 설명 (선택 사항)"
)

# 저장 버튼
if st.button("프리셋 저장", disabled=(not preset_name)):
    manager.save_preset(
        name=preset_name,
        description=preset_description or "",
        strategy=st.session_state.strategy_name,
        strategy_params=st.session_state.strategy_params,
        symbols=st.session_state.selected_symbols,
        initial_capital=st.session_state.initial_capital,
        position_size=st.session_state.position_size,
        stop_loss_pct=st.session_state.stop_loss_pct,
        take_profit_pct=st.session_state.take_profit_pct,
        enable_stop_loss=st.session_state.enable_stop_loss,
        enable_take_profit=st.session_state.enable_take_profit
    )
    st.success(f"프리셋 '{preset_name}' 저장 완료")
```

##### 3. 프리셋 삭제

```python
# 삭제 버튼
if st.button("프리셋 삭제", disabled=(selected_preset == "(새 설정)")):
    # 확인 메시지
    if st.checkbox(f"정말로 '{selected_preset}' 프리셋을 삭제하시겠습니까?"):
        manager.delete_preset(selected_preset)
        st.success(f"프리셋 '{selected_preset}' 삭제 완료")
        st.rerun()
```

##### 4. 프리셋 상세 정보

```python
# 프리셋 선택 시 상세 정보 표시
if selected_preset != "(새 설정)":
    preset = manager.load_preset(selected_preset)

    with st.expander("프리셋 상세 정보", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**전략**: {preset['strategy']}")
            st.markdown(f"**종목**: {', '.join(preset['symbols'])}")
            st.markdown(f"**초기 자본**: ${preset['initial_capital']:,.2f}")
            st.markdown(f"**포지션 크기**: {preset['position_size']:.1%}")

        with col2:
            st.markdown(f"**손절**: {preset.get('stop_loss_pct', 0) * 100:.1f}%")
            st.markdown(f"**익절**: {preset.get('take_profit_pct', 0) * 100:.1f}%")
            st.markdown(f"**생성일**: {preset['created_at'][:10]}")
            st.markdown(f"**최근 사용**: {preset.get('last_used', 'N/A')[:10]}")

        # 전략 파라미터
        st.markdown("**전략 파라미터**:")
        st.json(preset['strategy_params'])

        # 설명
        if preset.get('description'):
            st.markdown(f"**설명**: {preset['description']}")
```

#### 프리셋 데이터 저장 위치

- 경로: `data/strategy_presets.json`
- 형식: JSON
- 자동 생성: 디렉토리가 없으면 자동 생성

#### 프리셋 불러오기 시 동작

1. 프리셋 선택 → "불러오기" 버튼 클릭
2. 프리셋 데이터를 `st.session_state`에 저장
3. 프리셋 심볼을 즐겨찾기에 자동 추가
4. UI의 모든 입력 필드가 프리셋 값으로 자동 업데이트
5. `last_used` 타임스탬프 자동 업데이트

#### 주의사항

- 같은 이름의 프리셋 저장 시 덮어쓰기 (확인 메시지 필요)
- 프리셋 삭제 시 확인 체크박스 필수
- 프리셋 불러오기 시 현재 입력 중인 값은 사라짐 (주의 필요)
- 프리셋 저장 버튼은 프리셋 이름이 입력되어야 활성화

---

### UI 구성

#### 1. 전략 선택

```python
strategy_name = st.selectbox(
    "Select Strategy",
    ['RSI Strategy', 'MACD Strategy', 'Moving Average Crossover',
     'Bollinger Bands', 'Stochastic Oscillator']
)
```

**전략별 파라미터**:
- **RSI**: period (14), overbought (70), oversold (30)
- **MACD**: fast_period (12), slow_period (26), signal_period (9)
- **MA Crossover**: fast_period (10), slow_period (30)
- **Bollinger Bands**: period (20), std_dev (2.0)
- **Stochastic**: k_period (14), d_period (3)

#### 2. 종목 선택

```python
symbols = st.multiselect(
    "Select US Stocks",
    ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'],
    default=['AAPL']
)
```

**제약 조건**:
- 최소 1종목, 최대 7종목
- 미국 주식만 지원

#### 3. 자본 및 포지션 설정

```python
initial_capital = st.number_input(
    "Initial Capital ($)",
    min_value=1000.0,
    value=10000.0,
    step=1000.0
)

position_size = st.slider(
    "Position Size per Trade",
    min_value=0.1,
    max_value=1.0,
    value=0.3,
    step=0.05,
    help="Percentage of capital to use per trade"
)
```

#### 4. Stop Loss & Take Profit 설정

```python
# Stop Loss 설정
col1, col2 = st.columns(2)

with col1:
    enable_stop_loss = st.checkbox(
        "Enable Stop Loss",
        value=False,
        help="활성화 시 손실이 일정 비율 도달하면 자동 매도"
    )

    if enable_stop_loss:
        stop_loss_pct = st.number_input(
            "Stop Loss (%)",
            min_value=0.5,
            max_value=20.0,
            value=3.0,
            step=0.5,
            help="손실률 (예: 3.0 = -3%)"
        ) / 100  # 비율로 변환

with col2:
    enable_take_profit = st.checkbox(
        "Enable Take Profit",
        value=False,
        help="활성화 시 수익이 일정 비율 도달하면 자동 매도"
    )

    if enable_take_profit:
        take_profit_pct = st.number_input(
            "Take Profit (%)",
            min_value=1.0,
            max_value=50.0,
            value=6.0,
            step=0.5,
            help="수익률 (예: 6.0 = +6%)"
        ) / 100  # 비율로 변환
```

**동작 설명**:
- **Stop Loss**: 진입가 대비 `-3%` 손실 시 자동 매도
- **Take Profit**: 진입가 대비 `+6%` 수익 시 자동 매도
- PaperTrader가 매 iteration마다 자동으로 손익을 체크하고 조건 충족 시 청산

#### 5. 세션 제어

```python
# 시작 버튼
if st.button("Start Paper Trading"):
    session_id = start_paper_trading(strategy_name, symbols, initial_capital, position_size)
    st.success(f"Session started: {session_id}")

# 중지 버튼
if st.button("Stop Paper Trading"):
    stop_paper_trading()
    st.success("Session stopped")
```

---

### 백그라운드 실행

#### 스레드 관리

```python
import threading

def start_paper_trading(strategy_name, symbols, initial_capital, position_size):
    # 1. 전략 생성
    strategy = create_strategy(strategy_name)

    # 2. PaperTrader 초기화
    trader = PaperTrader(
        strategy=strategy,
        symbols=symbols,
        broker=broker,
        initial_capital=initial_capital,
        position_size=position_size,
        db=TradingDatabase()
    )

    # 3. 백그라운드 스레드로 실행
    def run_trading():
        try:
            trader.run_realtime(interval_seconds=60, timeframe='1d')
        except Exception as e:
            st.session_state.paper_trading_error = str(e)

    trading_thread = threading.Thread(target=run_trading, daemon=True)
    trading_thread.start()

    # 4. 세션 상태 저장
    st.session_state.paper_trader = trader
    st.session_state.paper_trading_active = True

    return trader.session_id
```

**주의사항**:
- `daemon=True`: 메인 프로세스 종료 시 스레드도 자동 종료
- 세션 상태에 trader 저장: Streamlit rerun 시에도 유지
- 에러 핸들링: 예외 발생 시 세션 상태에 저장

---

### 실시간 포트폴리오 모니터링

#### Auto-refresh 구현

```python
# 10초마다 자동 새로고침
if st.session_state.paper_trading_active:
    time.sleep(10)
    st.rerun()
```

#### 포트폴리오 현황 표시

```python
if st.session_state.paper_trader:
    trader = st.session_state.paper_trader

    # 1. 총 포트폴리오 가치
    total_value = trader.get_portfolio_value()
    st.metric("Total Portfolio Value", f"${total_value:,.2f}")

    # 2. 현금 잔고
    st.metric("Cash Balance", f"${trader.cash:,.2f}")

    # 3. 포지션 테이블
    positions_data = []
    for symbol, shares in trader.positions.items():
        ticker = broker.fetch_ticker(symbol, overseas=True)
        current_price = ticker['last']
        market_value = shares * current_price

        # P&L 계산 (간단한 예시)
        avg_entry_price = trader.avg_entry_prices.get(symbol, current_price)
        pnl = (current_price - avg_entry_price) * shares
        pnl_pct = ((current_price - avg_entry_price) / avg_entry_price) * 100

        positions_data.append({
            'Symbol': symbol,
            'Shares': shares,
            'Current Price': f"${current_price:.2f}",
            'Market Value': f"${market_value:,.2f}",
            'P&L': f"${pnl:,.2f}",
            'P&L %': f"{pnl_pct:.2f}%"
        })

    st.dataframe(positions_data)
```

---

### 데이터베이스 연동

#### 세션 추적

```python
# 세션 시작 시 DB에 기록
db = TradingDatabase()
session_id = db.create_session(strategy.name, initial_capital)

# 거래 발생 시 DB에 기록
db.log_trade(session_id, {
    'symbol': 'AAPL',
    'timestamp': datetime.now(),
    'type': 'BUY',
    'price': 150.0,
    'size': 10.0,
    'commission': 1.5
})

# 세션 종료 시 최종 지표 업데이트
db.update_session(session_id, {
    'end_time': datetime.now().isoformat(),
    'final_capital': trader.cash + sum(positions_value),
    'total_return': ((final_capital - initial_capital) / initial_capital) * 100,
    'status': 'completed'
})
```

---

## Strategy Comparison 탭 (Phase 1 완료 ✅)

### 개요

여러 Paper Trading 세션의 성과를 비교하고 최적 전략 식별

**지원 기능**:
- 저장된 모든 세션 목록 표시
- 다중 세션 선택 및 비교
- 성과 지표 비교 테이블
- 수익 곡선 비교 차트
- 최고 승률 전략 추천

---

### UI 구성

#### 1. 세션 선택

```python
# 모든 세션 조회
db = TradingDatabase()
all_sessions = db.get_all_sessions()

# 세션 선택 UI
selected_sessions = st.multiselect(
    "Select Sessions to Compare",
    options=all_sessions,
    format_func=lambda x: f"{x['strategy_name']} ({x['start_time'][:16]})",
    default=all_sessions[:2]  # 기본값: 최근 2개
)
```

#### 2. 비교 테이블

```python
if selected_sessions:
    comparison_data = []

    for session in selected_sessions:
        summary = db.get_session_summary(session['session_id'])
        comparison_data.append({
            'Session ID': session['session_id'],
            'Strategy': session['strategy_name'],
            'Start Time': session['start_time'][:16],
            'End Time': session['end_time'][:16] if session['end_time'] else 'Running',
            'Initial Capital': f"${session['initial_capital']:,.2f}",
            'Final Capital': f"${summary['final_capital']:,.2f}",
            'Return %': f"{summary['total_return']:.2f}%",
            'Sharpe Ratio': f"{summary['sharpe_ratio']:.2f}",
            'Max Drawdown %': f"{summary['max_drawdown']:.2f}%",
            'Win Rate %': f"{summary['win_rate']:.2f}%"
        })

    st.dataframe(comparison_data)
```

#### 3. 수익 곡선 비교 차트

```python
def create_equity_comparison_chart(session_ids: List[str], db: TradingDatabase):
    """여러 세션의 수익 곡선을 한 차트에 표시"""
    fig = go.Figure()

    for session_id in session_ids:
        snapshots = db.get_session_snapshots(session_id)

        if snapshots:
            # 세션 정보 조회
            session = db.get_session_summary(session_id)
            strategy_name = session['strategy_name']

            # 수익 곡선 추가
            fig.add_trace(go.Scatter(
                x=[s['timestamp'] for s in snapshots],
                y=[s['total_value'] for s in snapshots],
                mode='lines',
                name=f"{strategy_name} ({session_id[:8]}...)"
            ))

    fig.update_layout(
        title="Equity Curve Comparison",
        xaxis_title="Time",
        yaxis_title="Portfolio Value ($)",
        template="plotly_white",
        hovermode='x unified'
    )

    return fig

# 차트 표시
fig = create_equity_comparison_chart(selected_session_ids, db)
st.plotly_chart(fig, use_container_width=True)
```

#### 4. 최고 승률 전략 추천

```python
if selected_sessions:
    # 승률 기준 최고 전략 찾기
    best_session = max(
        selected_sessions,
        key=lambda x: db.get_session_summary(x['session_id'])['win_rate']
    )

    best_summary = db.get_session_summary(best_session['session_id'])

    st.success(f"""
    🏆 Best Strategy by Win Rate:
    - Strategy: {best_session['strategy_name']}
    - Win Rate: {best_summary['win_rate']:.2f}%
    - Total Return: {best_summary['total_return']:.2f}%
    """)
```

---

### 데이터 조회 패턴

#### 세션 목록 조회

```python
# 모든 세션
all_sessions = db.get_all_sessions()

# 완료된 세션만
completed_sessions = [s for s in all_sessions if s['status'] == 'completed']

# 특정 전략 세션만
rsi_sessions = [s for s in all_sessions if 'RSI' in s['strategy_name']]
```

#### 세션 상세 정보

```python
# 세션 요약
summary = db.get_session_summary(session_id)

# 거래 내역
trades = db.get_session_trades(session_id)

# 포트폴리오 스냅샷
snapshots = db.get_session_snapshots(session_id)

# 전략 신호
signals = db.get_session_signals(session_id)
```

---

### 성능 최적화

#### 캐싱 전략

```python
@st.cache_data(ttl=60)
def load_all_sessions():
    """세션 목록 캐싱 (60초)"""
    db = TradingDatabase()
    return db.get_all_sessions()

@st.cache_data(ttl=300)
def load_session_snapshots(session_id: str):
    """스냅샷 데이터 캐싱 (5분)"""
    db = TradingDatabase()
    return db.get_session_snapshots(session_id)
```

#### 대용량 데이터 처리

```python
# 스냅샷이 1000개 이상이면 샘플링
if len(snapshots) > 1000:
    step = len(snapshots) // 1000
    snapshots = snapshots[::step]
```

---

### 테스트 체크리스트

**Paper Trading 탭**:
- [ ] 전략 선택이 정상 작동하는가?
- [ ] 종목 다중 선택이 가능한가?
- [ ] 세션 시작/중지가 정상 동작하는가?
- [ ] 백그라운드 스레드가 정상 실행되는가?
- [ ] 포트폴리오 현황이 10초마다 갱신되는가?
- [ ] 에러 발생 시 적절히 처리되는가?

**Strategy Comparison 탭**:
- [ ] 모든 세션이 목록에 표시되는가?
- [ ] 세션 다중 선택이 가능한가?
- [ ] 비교 테이블이 정확하게 표시되는가?
- [ ] 수익 곡선 차트가 올바르게 그려지는가?
- [ ] 최고 승률 전략이 정확하게 표시되는가?
- [ ] 세션이 없을 때 적절한 메시지가 표시되는가?

---

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 백테스팅 엔진
- [../tests/CLAUDE.md](../tests/CLAUDE.md): 대시보드 통합 테스트
- `README.md`: 대시보드 사용 설명서
