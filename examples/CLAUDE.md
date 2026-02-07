# examples/ - 예제 스크립트

> **상위 문서**: [루트 CLAUDE.md](../CLAUDE.md)를 먼저 참조하세요.
> 이 문서는 루트 규칙을 따르며, 예제 스크립트 사용법에 특화된 규칙만 정의합니다.

---

## 목적

트레이딩 봇의 주요 기능을 시연하는 예제 스크립트:
- **빠른 시작**: 초보자를 위한 간단한 예제
- **백테스팅**: 전략 백테스트 실행
- **최적화**: 파라미터 최적화
- **전략 비교**: 여러 전략 성능 비교

---

## 디렉토리 구조

```
examples/
├── quickstart.py               # 빠른 시작 가이드
├── run_backtest_example.py     # 백테스팅 예제
├── strategy_optimization.py    # 전략 최적화 예제
├── strategy_comparison.py      # 전략 비교 예제
└── test_dashboard.py           # 대시보드 테스트
```

---

## 예제 스크립트

### 1. `quickstart.py` - 빠른 시작

**목적**: 5분 안에 첫 백테스트 실행

**실행 명령어**:
```bash
python examples/quickstart.py 2>&1 | tee .context/terminal/quickstart_$(date +%s).log
```

**주요 내용**:
- 시뮬레이션 데이터 생성
- RSI 전략 생성
- 백테스트 실행
- 결과 출력

**코드 구조**:
```python
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.backtester import Backtester

# 1. 데이터 생성
data_gen = SimulationDataGenerator(seed=42)
df = data_gen.generate_trend_data(periods=1000, trend='bullish')

# 2. 전략 생성
strategy = RSIStrategy(period=14, overbought=70, oversold=30)

# 3. 백테스트 실행
backtester = Backtester(strategy, initial_capital=10000)
results = backtester.run(df)

# 4. 결과 출력
backtester.print_results(results)
```

**예상 출력**:
```
=== Backtest Results ===
Strategy: RSI_14_70_30
Total Return: 15.23%
Sharpe Ratio: 1.45
Max Drawdown: -8.67%
Win Rate: 58.33%
Total Trades: 24
```

---

### 2. `run_backtest_example.py` - 백테스팅 예제

**목적**: 다양한 시장 상황에서 전략 테스트

**실행 명령어**:
```bash
python examples/run_backtest_example.py 2>&1 | tee .context/terminal/backtest_$(date +%s).log
```

**주요 내용**:
- 여러 시장 상황 (상승/하락/횡보/변동성) 생성
- 각 상황에서 전략 백테스트
- 결과 비교 및 분석

**코드 구조**:
```python
# 여러 시장 상황 생성
market_scenarios = {
    'bullish': data_gen.generate_trend_data(periods=1000, trend='bullish'),
    'bearish': data_gen.generate_trend_data(periods=1000, trend='bearish'),
    'sideways': data_gen.generate_trend_data(periods=1000, trend='sideways'),
    'volatile': data_gen.generate_volatile_data(periods=1000)
}

# 각 상황에서 백테스트
for scenario_name, data in market_scenarios.items():
    print(f"\n=== {scenario_name.upper()} Market ===")
    results = backtester.run(data)
    backtester.print_results(results)
```

**마켓별 권장 사용**:
- **암호화폐**: volatile 시나리오 중점 테스트
- **해외주식**: bullish/bearish 시나리오 중점 테스트

---

### 3. `strategy_optimization.py` - 전략 최적화

**목적**: 그리드 서치로 최적 파라미터 찾기

**실행 명령어**:
```bash
python examples/strategy_optimization.py 2>&1 | tee .context/terminal/optimization_$(date +%s).log
```

**주요 내용**:
- 파라미터 그리드 정의
- 모든 조합 백테스트
- 최적 파라미터 찾기
- 민감도 분석

**코드 구조**:
```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy

# 파라미터 그리드 (암호화폐용)
crypto_param_grid = {
    'period': [7, 10, 14, 21, 28],
    'overbought': [70, 75, 80, 85],
    'oversold': [15, 20, 25, 30]
}

# 파라미터 그리드 (해외주식용)
stock_param_grid = {
    'period': [10, 14, 20, 28, 35],
    'overbought': [65, 70, 75, 80],
    'oversold': [20, 25, 30, 35]
}

# 최적화 실행
optimizer = StrategyOptimizer(initial_capital=10000)
best_result = optimizer.optimize(
    RSIStrategy, 
    df, 
    crypto_param_grid,  # 또는 stock_param_grid
    metric='sharpe_ratio'
)

print(f"Best parameters: {best_result['params']}")
print(f"Best Sharpe Ratio: {best_result['sharpe_ratio']:.2f}")
```

**최적화 메트릭 선택**:
- `total_return`: 수익률 최대화 (단기)
- `sharpe_ratio`: 위험 대비 수익 최대화 (권장)
- `win_rate`: 승률 최대화
- `max_drawdown`: 손실 최소화 (보수적)

---

### 4. `strategy_comparison.py` - 전략 비교

**목적**: 여러 전략의 성능 비교

**실행 명령어**:
```bash
python examples/strategy_comparison.py 2>&1 | tee .context/terminal/comparison_$(date +%s).log
```

**주요 내용**:
- 여러 전략 생성 (RSI, MACD, MA, Bollinger Bands, Stochastic)
- 동일한 데이터로 백테스트
- 결과 테이블로 비교

**코드 구조**:
```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from trading_bot.strategies.stochastic_strategy import StochasticStrategy
from trading_bot.strategy import MovingAverageCrossover

# 전략 리스트
strategies = [
    MovingAverageCrossover(fast_period=10, slow_period=30),
    RSIStrategy(period=14, overbought=70, oversold=30),
    MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
    BollingerBandsStrategy(period=20, std_dev=2.0),
    StochasticStrategy(k_period=14, d_period=3)
]

# 비교 실행
optimizer = StrategyOptimizer(initial_capital=10000)
comparison = optimizer.compare_strategies(strategies, df)

print("\n=== Strategy Comparison ===")
print(comparison.to_string(index=False))
```

**예상 출력**:
```
=== Strategy Comparison ===
         Strategy  Total Return  Sharpe Ratio  Max Drawdown  Win Rate  Num Trades
  MA_Crossover_10_30         8.45          1.12        -12.34     52.17          23
        RSI_14_70_30        15.23          1.45         -8.67     58.33          24
     MACD_12_26_9        11.78          1.28         -9.45     55.56          27
  BollingerBands_20_2.0        9.34          1.18        -10.23     53.33          30
    Stochastic_14_3        13.56          1.35         -9.12     56.67          33
```

**마켓별 추천 전략**:
- **암호화폐 (고변동성)**: RSI, Bollinger Bands
- **해외주식 (저변동성)**: MACD, MA Crossover

---

### 5. `test_dashboard.py` - 대시보드 테스트

**목적**: 대시보드 기능 검증

**실행 명령어**:
```bash
python examples/test_dashboard.py 2>&1 | tee .context/terminal/dashboard_test_$(date +%s).log
```

**주요 내용**:
- 대시보드 차트 생성 함수 테스트
- 다국어 번역 테스트
- 데이터 로딩 테스트

---

## 예제 작성 가이드

### 새 예제 추가 시

1. **명확한 목적**: 예제가 보여주려는 핵심 기능 1개
2. **주석 추가**: 각 단계에 설명 주석
3. **결과 출력**: 실행 결과를 명확하게 표시
4. **로그 기록**: 터미널 로그 저장

**템플릿**:
```python
"""
[예제 제목]

목적: [이 예제가 보여주는 것]
실행: python examples/[파일명].py
"""
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.backtester import Backtester


def main():
    # 1. 데이터 준비
    print("Step 1: Generating simulation data...")
    data_gen = SimulationDataGenerator(seed=42)
    df = data_gen.generate_trend_data(periods=1000, trend='bullish')
    print(f"Generated {len(df)} data points\n")
    
    # 2. 전략 생성
    print("Step 2: Creating strategy...")
    strategy = RSIStrategy(period=14)
    print(f"Strategy: {strategy.name}\n")
    
    # 3. 백테스트 실행
    print("Step 3: Running backtest...")
    backtester = Backtester(strategy, initial_capital=10000)
    results = backtester.run(df)
    
    # 4. 결과 출력
    print("\n=== Results ===")
    backtester.print_results(results)


if __name__ == "__main__":
    main()
```

---

## 실행 순서 권장

초보자를 위한 순서:
1. `quickstart.py` - 기본 개념 이해
2. `run_backtest_example.py` - 다양한 시장 상황 경험
3. `strategy_comparison.py` - 여러 전략 비교
4. `strategy_optimization.py` - 파라미터 튜닝

---

## 마켓별 예제 수정

### 암호화폐 트레이딩용

```python
# 높은 변동성, 짧은 기간
data = data_gen.generate_volatile_data(periods=500)
strategy = RSIStrategy(period=10, overbought=80, oversold=20)
```

### 해외주식 트레이딩용

```python
# 안정적 변동성, 긴 기간
data = data_gen.generate_trend_data(periods=2000, trend='bullish')
strategy = RSIStrategy(period=14, overbought=70, oversold=30)
```

---

## 트러블슈팅

### "No trades executed"

**원인**: 시그널이 전혀 발생하지 않음

**해결**:
- 파라미터 조정 (더 민감하게)
- 데이터 길이 늘리기 (periods 증가)
- 다른 시장 상황 시도

### "NaN in results"

**원인**: 데이터가 전략의 warm-up 기간보다 짧음

**해결**:
- 데이터 길이 늘리기
- 전략 파라미터 낮추기 (period 감소)

### "Low Sharpe Ratio"

**원인**: 위험 대비 수익이 낮음

**해결**:
- 전략 최적화 실행
- 다른 전략 시도
- 수수료 설정 확인

---

## 관련 문서

- [../trading_bot/CLAUDE.md](../trading_bot/CLAUDE.md): 백테스팅 엔진 상세
- [../trading_bot/strategies/CLAUDE.md](../trading_bot/strategies/CLAUDE.md): 전략 구현 가이드
- [../README.md](../README.md): 프로젝트 개요 및 설치
