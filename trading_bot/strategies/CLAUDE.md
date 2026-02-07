# trading_bot/strategies/ - 트레이딩 전략 구현

> **상위 문서**: [루트 CLAUDE.md](../../CLAUDE.md) 및 [trading_bot/CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 상위 규칙을 따르며, 전략 구현에 특화된 규칙만 정의합니다.

---

## 목적

기술적 분석 기반 트레이딩 전략 구현:
- **지표 계산**: RSI, MACD, Bollinger Bands, Stochastic 등
- **시그널 생성**: BUY/SELL/HOLD 시그널
- **마켓 중립**: 암호화폐와 해외주식 모두에서 동작

---

## 디렉토리 구조

```
strategies/
├── __init__.py
├── rsi_strategy.py              # RSI (Relative Strength Index)
├── macd_strategy.py             # MACD (Moving Average Convergence Divergence)
├── bollinger_bands_strategy.py  # Bollinger Bands
└── stochastic_strategy.py       # Stochastic Oscillator
```

---

## 구현된 전략

### 1. RSI Strategy (`rsi_strategy.py`)

**원리**:
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss (over period)
```

**시그널**:
- RSI < oversold (기본 30) → **BUY**
- RSI > overbought (기본 70) → **SELL**

**파라미터**:
- `period`: RSI 계산 기간 (기본 14)
- `oversold`: 과매도 임계값 (기본 30)
- `overbought`: 과매수 임계값 (기본 70)

**마켓 적용**:
- **암호화폐**: 변동성이 높아 overbought=80, oversold=20 조정 권장
- **해외주식**: 기본값 사용 적합

---

### 2. MACD Strategy (`macd_strategy.py`)

**원리**:
```
MACD Line = EMA(12) - EMA(26)
Signal Line = EMA(9) of MACD Line
Histogram = MACD Line - Signal Line
```

**시그널**:
- MACD Line이 Signal Line을 상향 돌파 → **BUY**
- MACD Line이 Signal Line을 하향 돌파 → **SELL**

**파라미터**:
- `fast_period`: 빠른 EMA (기본 12)
- `slow_period`: 느린 EMA (기본 26)
- `signal_period`: 시그널 라인 EMA (기본 9)

**마켓 적용**:
- **암호화폐**: fast_period=8, slow_period=17 (더 민감하게)
- **해외주식**: 기본값 사용 적합

---

### 3. Bollinger Bands Strategy (`bollinger_bands_strategy.py`)

**원리**:
```
Middle Band = SMA(20)
Upper Band = Middle Band + (2 * std)
Lower Band = Middle Band - (2 * std)
```

**시그널**:
- 가격이 Lower Band 터치 → **BUY**
- 가격이 Upper Band 터치 → **SELL**

**파라미터**:
- `period`: SMA 기간 (기본 20)
- `std_dev`: 표준편차 배수 (기본 2.0)

---

### 4. Stochastic Oscillator (`stochastic_strategy.py`)

**원리**:
```
%K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
%D = SMA(%K, smooth_d)
```

**시그널**:
- %K가 oversold 아래에서 %D를 상향 돌파 → **BUY**
- %K가 overbought 위에서 %D를 하향 돌파 → **SELL**

**파라미터**:
- `k_period`: %K 계산 기간 (기본 14)
- `d_period`: %D 평활화 기간 (기본 3)
- `overbought`: 과매수 임계값 (기본 80)
- `oversold`: 과매도 임계값 (기본 20)

---

## 전략 구현 템플릿

새로운 전략을 추가할 때 사용할 템플릿:

```python
"""
[전략명] Trading Strategy

원리: [전략의 수학적 원리]
시그널: [BUY/SELL 조건]
"""
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


class MyStrategy:
    """
    [전략명] 전략
    
    Parameters:
        param1 (int): [설명]
        param2 (float): [설명]
    """
    
    def __init__(self, param1: int = 10, param2: float = 2.0):
        self.param1 = param1
        self.param2 = param2
        self.name = f"MyStrategy_{param1}_{param2}"
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        지표 계산 및 시그널 생성
        
        Args:
            df: OHLCV 데이터 (columns: open, high, low, close, volume)
        
        Returns:
            DataFrame with indicators, signal, position
        """
        data = df.copy()
        
        # 1. 지표 계산
        data['indicator1'] = self._calculate_indicator1(data)
        data['indicator2'] = self._calculate_indicator2(data)
        
        # 2. 시그널 생성
        data['signal'] = 0  # 0 = HOLD, 1 = BUY, -1 = SELL
        
        # BUY 조건
        buy_condition = (data['indicator1'] > data['indicator2'])
        data.loc[buy_condition, 'signal'] = 1
        
        # SELL 조건
        sell_condition = (data['indicator1'] < data['indicator2'])
        data.loc[sell_condition, 'signal'] = -1
        
        # 3. 포지션 계산 (시그널을 forward fill)
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)
        
        return data
    
    def _calculate_indicator1(self, data: pd.DataFrame) -> pd.Series:
        """지표 1 계산 (private 메서드)"""
        return data['close'].rolling(window=self.param1).mean()
    
    def _calculate_indicator2(self, data: pd.DataFrame) -> pd.Series:
        """지표 2 계산 (private 메서드)"""
        return data['close'].rolling(window=self.param1).std()
    
    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """
        현재 시그널 반환
        
        Returns:
            (signal, info_dict)
        """
        data = self.calculate_indicators(df)
        last_row = data.iloc[-1]
        
        info = {
            'indicator1': last_row['indicator1'],
            'indicator2': last_row['indicator2'],
            'close': last_row['close']
        }
        
        return int(last_row['signal']), info
    
    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        모든 시그널 이벤트 반환
        
        Returns:
            List of signal events
        """
        data = self.calculate_indicators(df)
        signals_df = data[data['signal'] != 0].copy()
        
        return signals_df.to_dict('records')
```

---

## 전략 개발 체크리스트

### 지표 계산
- [ ] 원본 데이터를 `.copy()`로 보호
- [ ] pandas 벡터화 연산 사용 (루프 금지)
- [ ] NaN 처리 (초기 warm-up 기간)
- [ ] Look-ahead bias 방지

### 시그널 생성
- [ ] 명확한 BUY/SELL 조건 정의
- [ ] `signal` 컬럼: 1 (BUY), -1 (SELL), 0 (HOLD)
- [ ] `position` 컬럼: forward fill 적용
- [ ] 과거 데이터만 사용

### 테스트
- [ ] 단위 테스트 작성 (`tests/test_my_strategy.py`)
- [ ] 여러 시장 상황에서 백테스트 (상승/하락/횡보/변동성)
- [ ] 엣지 케이스 확인 (데이터 부족, 모든 값 동일 등)

### 문서화
- [ ] Docstring 작성 (클래스, 메서드)
- [ ] 전략 원리 설명
- [ ] 파라미터 의미 명시

---

## 파라미터 최적화 가이드

### 최적화 대상 파라미터

전략별 주요 파라미터:
- **RSI**: period, overbought, oversold
- **MACD**: fast_period, slow_period, signal_period
- **Bollinger Bands**: period, std_dev
- **Stochastic**: k_period, d_period, overbought, oversold

### 최적화 범위 설정

```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy

# 암호화폐용 파라미터 그리드
crypto_param_grid = {
    'period': [7, 10, 14, 21],
    'overbought': [75, 80, 85],
    'oversold': [15, 20, 25]
}

# 해외주식용 파라미터 그리드
stock_param_grid = {
    'period': [10, 14, 20, 28],
    'overbought': [65, 70, 75],
    'oversold': [25, 30, 35]
}

optimizer = StrategyOptimizer(initial_capital=10000)
best_result = optimizer.optimize(RSIStrategy, df, crypto_param_grid)
```

### 과적합 방지

1. **In-Sample / Out-Sample 분리**:
   ```python
   train_df = df[:int(len(df) * 0.7)]  # 70% 학습
   test_df = df[int(len(df) * 0.7):]   # 30% 검증
   ```

2. **다양한 시장 상황 테스트**:
   - 상승장 (bullish)
   - 하락장 (bearish)
   - 횡보장 (sideways)
   - 고변동성 (volatile)

3. **강건한 파라미터 선택**:
   - 단일 최적값보다 안정적 범위 선택
   - Sharpe ratio, Drawdown 등 복합 지표 고려

---

## 마켓별 파라미터 추천

### 암호화폐 (높은 변동성)
- **RSI**: period=10~14, overbought=75~85, oversold=15~25
- **MACD**: fast=8, slow=17, signal=9
- **Bollinger Bands**: period=20, std_dev=2.5~3.0

### 해외주식 (낮은 변동성)
- **RSI**: period=14~20, overbought=65~70, oversold=30~35
- **MACD**: fast=12, slow=26, signal=9 (기본값)
- **Bollinger Bands**: period=20, std_dev=2.0

---

## 성능 메트릭

전략 평가 시 고려할 지표:
- **Total Return**: 총 수익률
- **Sharpe Ratio**: 위험 대비 수익 (높을수록 좋음)
- **Max Drawdown**: 최대 손실폭 (낮을수록 좋음)
- **Win Rate**: 승률
- **Profit Factor**: 총 이익 / 총 손실

---

## 관련 문서

- [../CLAUDE.md](../CLAUDE.md): trading_bot 모듈 전체 가이드
- [../../tests/CLAUDE.md](../../tests/CLAUDE.md): 테스트 작성 가이드
- [../../examples/CLAUDE.md](../../examples/CLAUDE.md): 전략 사용 예제
