# trading_bot/ - 트레이딩 봇 핵심 모듈

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, `trading_bot/` 디렉토리에 특화된 규칙만 정의합니다.

---

## 목적

트레이딩 봇의 핵심 로직을 구현하는 모듈:
- **Data Layer**: 실시간/시뮬레이션 데이터 처리
- **Strategy Layer**: 트레이딩 전략 및 시그널 생성
- **Execution Layer**: 백테스팅 및 페이퍼 트레이딩
- **Optimization Layer**: 전략 파라미터 최적화

---

## 디렉토리 구조

```
trading_bot/
├── __init__.py
├── config.py                    # 설정 관리 (암호화폐 + 해외주식)
├── data_handler.py              # 실시간 데이터 (CCXT, 증권사 API)
├── simulation_data.py           # 시뮬레이션 데이터 생성
├── strategy.py                  # 기본 MA 전략
├── backtester.py                # 백테스팅 엔진
├── optimizer.py                 # 전략 최적화
├── paper_trader.py              # 페이퍼 트레이딩
└── strategies/
    ├── __init__.py
    ├── rsi_strategy.py          # RSI 전략
    ├── macd_strategy.py         # MACD 전략
    ├── bollinger_bands_strategy.py  # 볼린저 밴드
    └── stochastic_strategy.py   # 스토캐스틱
```

---

## 마켓별 특성

### 암호화폐 트레이딩
- **거래소 연동**: CCXT 라이브러리 사용
- **24/7 거래**: 주말/공휴일 없음
- **높은 변동성**: 시뮬레이션 파라미터 조정 필요
- **거래 수수료**: 0.1% ~ 0.25% (거래소별 상이)

### 해외주식 트레이딩
- **증권사 연동**: 증권사 API (키움, 이베스트, Interactive Brokers 등)
- **거래 시간**: 장중 거래 시간 제한 (미국: 23:30~06:00 KST)
- **안정적 변동성**: 암호화폐 대비 낮은 변동성
- **거래 수수료**: 증권사별 상이

---

## 로컬 코딩 컨벤션

### 전략 인터페이스 (필수 구현)

모든 전략 클래스는 다음 메서드를 구현해야 합니다:

```python
class Strategy:
    def __init__(self, **params):
        """전략 파라미터 초기화"""
        self.name = "Strategy_Name"
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        지표 계산 및 시그널 생성
        
        Returns:
            DataFrame with:
            - 원본 OHLCV 컬럼
            - 지표 컬럼 (전략별)
            - 'signal': 1 (BUY), -1 (SELL), 0 (HOLD)
            - 'position': 1 (long), 0 (flat)
        """
        pass
    
    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """현재 시그널 반환: (signal, info_dict)"""
        pass
    
    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """모든 시그널 이벤트 반환"""
        pass
```

### Look-Ahead Bias 방지

❌ **잘못된 예시** (미래 데이터 사용):
```python
data['signal'] = (data['close'] > data['close'].shift(-1))  # 미래 데이터!
```

✅ **올바른 예시** (과거 데이터만 사용):
```python
data['signal'] = (data['close'] > data['close'].shift(1))
```

### 시그널 타이밍

- 시그널은 **현재 바의 종가** 기준으로 생성
- 실행은 **다음 바의 시가** (또는 현재 종가) 기준

### 데이터 복사 규칙

지표 계산 시 원본 데이터 보호:
```python
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()  # 원본 보호
    # 지표 계산...
    return data
```

---

## 주요 파일 설명

| 파일 | 역할 | 마켓 지원 |
|------|------|----------|
| `config.py` | 전역 설정 관리 (거래소, 증권사, 초기 자본 등) | 암호화폐 + 해외주식 |
| `data_handler.py` | CCXT, 증권사 API를 통한 실시간 데이터 | 암호화폐 + 해외주식 |
| `simulation_data.py` | GBM 기반 시뮬레이션 데이터 생성 | 공통 |
| `backtester.py` | 백테스팅 엔진 (수수료, 슬리피지 포함) | 공통 |
| `optimizer.py` | 그리드 서치 파라미터 최적화 | 공통 |
| `paper_trader.py` | 실시간 페이퍼 트레이딩 | 암호화폐 + 해외주식 |
| `database.py` | SQLite 데이터베이스 (세션 추적) | 공통 |

---

## PaperTrader - 실시간 모의투자

### 개요

`PaperTrader` 클래스는 실시간 시장 데이터를 사용한 모의투자를 지원합니다.
- **멀티 심볼**: 최대 7종목 동시 추적 가능
- **데이터베이스 연동**: SQLite로 세션, 거래, 포트폴리오 스냅샷 저장
- **실시간 실행**: `run_realtime()` 메서드로 주기적 전략 실행

### 기본 사용법

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from trading_bot.database import TradingDatabase
from dashboard.kis_broker import get_kis_broker

# 1. 브로커, 전략, 데이터베이스 초기화
broker = get_kis_broker()  # KIS API 필요
strategy = RSIStrategy(period=14, overbought=70, oversold=30)
db = TradingDatabase()  # data/paper_trading.db에 저장

# 2. PaperTrader 생성
trader = PaperTrader(
    strategy=strategy,
    symbols=['AAPL', 'MSFT', 'GOOGL'],  # 최대 7종목
    broker=broker,
    initial_capital=10000.0,
    position_size=0.3,  # 종목당 30% 투자
    db=db
)

# 3. 실시간 실행 (60초 간격)
trader.run_realtime(interval_seconds=60, timeframe='1d')
```

### 실시간 실행 루프

`run_realtime()` 메서드는 다음 작업을 반복합니다:

1. **실시간 시세 조회**: `broker.fetch_ticker(symbol, overseas=True)`
2. **OHLCV 데이터 조회**: `broker.fetch_ohlcv(symbol, timeframe, limit=100, overseas=True)`
3. **전략 신호 생성**: `strategy.get_current_signal(df)`
4. **거래 실행**: 신호에 따라 BUY/SELL
5. **포트폴리오 스냅샷**: 현재 포트폴리오 상태 저장
6. **대기**: `interval_seconds` 만큼 sleep

### 데이터베이스 연동

`TradingDatabase` 클래스는 다음 테이블을 관리합니다:

#### 1. `paper_trading_sessions`
- `session_id`: 세션 ID (strategy_name_timestamp 형식)
- `strategy_name`: 전략 이름
- `start_time`, `end_time`: 세션 시작/종료 시간
- `initial_capital`, `final_capital`: 초기/최종 자본
- `total_return`, `sharpe_ratio`, `max_drawdown`, `win_rate`: 성과 지표
- `status`: 세션 상태 (active/completed)

#### 2. `trades`
- 거래 내역 (symbol, timestamp, type, price, size, commission, pnl)

#### 3. `portfolio_snapshots`
- 포트폴리오 스냅샷 (timestamp, total_value, cash, positions JSON)

#### 4. `strategy_signals`
- 전략 신호 (symbol, timestamp, signal, indicator_values JSON, executed)

### 멀티 심볼 포트폴리오

```python
# positions는 Dict[str, float] (심볼 → 보유 주식 수)
trader.positions = {
    'AAPL': 10.0,
    'MSFT': 5.0,
    'GOOGL': 3.0
}

# 포트폴리오 가치 계산
total_value = trader.get_portfolio_value()  # 현금 + 모든 포지션 가치
```

### 세션 관리

```python
# 세션 시작 (자동으로 session_id 생성)
trader.start()

# 세션 중지 (최종 지표 업데이트)
trader.stop()

# 세션 요약 조회
summary = db.get_session_summary(trader.session_id)
print(f"Total Return: {summary['total_return']:.2f}%")
print(f"Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
```

### 주의사항

1. **브로커 필수**: `run_realtime()` 사용 시 broker 파라미터 필수
2. **API 제한**: KIS API rate limit (1분당 1회) 고려
3. **해외주식**: `overseas=True` 파라미터 필수 (미국 주식 거래 시)
4. **종목 수 제한**: 최대 7종목 (API 제한 및 성능 고려)
5. **데이터베이스**: db 파라미터 없으면 세션 추적 안 됨

---

## 새 전략 추가 방법

1. **전략 파일 생성**: `trading_bot/strategies/my_strategy.py`
2. **인터페이스 구현**: `calculate_indicators`, `get_current_signal`, `get_all_signals`
3. **테스트 작성**: `tests/test_my_strategy.py`
4. **`__init__.py`에 추가**:
   ```python
   from .my_strategy import MyStrategy
   __all__ = [..., 'MyStrategy']
   ```
5. **백테스트 검증**: 여러 시장 상황에서 테스트

---

## 성능 최적화 팁

### 벡터화 연산 사용

❌ **비효율적** (루프):
```python
for i in range(len(data)):
    data.loc[i, 'ma'] = data['close'].iloc[i-10:i].mean()
```

✅ **효율적** (벡터화):
```python
data['ma'] = data['close'].rolling(window=10).mean()
```

### 지표 계산 캐싱

```python
@lru_cache(maxsize=128)
def _calculate_expensive_indicator(self, key):
    # 비싼 계산...
    return result
```

---

## 커밋 전 체크리스트

- [ ] 모든 전략이 인터페이스를 올바르게 구현했는가?
- [ ] Look-ahead bias가 없는가?
- [ ] 원본 데이터를 `.copy()`로 보호했는가?
- [ ] 테스트가 통과하는가?
- [ ] 여러 시장 상황(상승/하락/횡보)에서 검증했는가?

---

## 관련 문서

- [strategies/CLAUDE.md](strategies/CLAUDE.md): 전략 구현 세부 가이드
- [../tests/CLAUDE.md](../tests/CLAUDE.md): 테스트 작성 가이드
- [../examples/CLAUDE.md](../examples/CLAUDE.md): 사용 예제
