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
