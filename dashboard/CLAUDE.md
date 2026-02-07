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

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 백테스팅 엔진
- [../tests/CLAUDE.md](../tests/CLAUDE.md): 대시보드 통합 테스트
- `README.md`: 대시보드 사용 설명서
