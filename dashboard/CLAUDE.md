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

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 백테스팅 엔진
- [../tests/CLAUDE.md](../tests/CLAUDE.md): 대시보드 통합 테스트
- `README.md`: 대시보드 사용 설명서
