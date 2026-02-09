# Crypto Trading Bot - Developer Documentation

이 문서는 암호화폐 트레이딩 봇 개발자를 위한 기술 문서입니다.

---

## ⚠️ 필수 실행 규칙 (모든 작업 전 확인)

> **이 규칙은 모든 작업에서 반드시 준수해야 합니다.**

### 1. 터미널 로그 기록
모든 Bash 명령어(빌드, 테스트, 설치, 실행) 실행 시 `.context/terminal/`에 로그 저장:
```bash
# 테스트 실행
pytest 2>&1 | tee .context/terminal/test_$(date +%s).log

# 의존성 설치
pip install -r requirements.txt 2>&1 | tee .context/terminal/install_$(date +%s).log

# 대시보드 실행
streamlit run dashboard/app.py 2>&1 | tee .context/terminal/dashboard_$(date +%s).log

# 백테스트 실행
python examples/run_backtest_example.py 2>&1 | tee .context/terminal/backtest_$(date +%s).log
```

### 2. 서브 CLAUDE.md 관리
- 새 디렉토리/모듈 생성 시 → 해당 디렉토리에 서브 CLAUDE.md 생성
- 기존 구조 변경 시 → 관련 서브 CLAUDE.md 업데이트
- 서브 CLAUDE.md는 반드시 루트 CLAUDE.md 참조

### 3. Git 커밋 규칙
- 커밋 메시지는 **한글**로 작성
- `Co-Authored-By` 태그 **사용 금지** (Claude 공동 작성자 표기 안 함)
- 커밋 메시지 형식:
```
<type>: <한글 설명>

<본문 (선택)>
```
- type: feat, fix, docs, refactor, test, chore 등

### 4. 작업 완료 체크리스트
- [ ] 터미널 로그 저장했는가?
- [ ] 서브 CLAUDE.md 업데이트 필요한가?
- [ ] Git 커밋 시 한글 메시지 사용했는가?

---

## 프로젝트 개요

Python 기반 멀티-마켓 트레이딩 봇
- **암호화폐 트레이딩**: 비트코인, 이더리움 등 암호화폐 자동매매
- **해외주식 트레이딩**: 미국, 유럽 등 해외 주식 자동매매
- **핵심 기능**: 백테스팅, 전략 최적화, 시뮬레이션, 페이퍼 트레이딩

## 기술 스택

- **Language**: Python 3.11+
- **Data Analysis**: pandas 2.0+, numpy 1.24+
- **Brokers**:
  - ccxt 4.0+ (암호화폐 거래소)
  - python-kis (한국투자증권 - 국내/해외주식)
- **Dashboard**: Streamlit 1.28+, Plotly 5.17+
- **Visualization**: matplotlib 3.7+, seaborn 0.12+
- **Testing**: pytest 7.4+, pytest-cov 4.1+

## 전역 코딩 컨벤션

- **네이밍**: 
  - snake_case (함수, 변수)
  - PascalCase (클래스)
  - UPPER_CASE (상수)
- **Type Hints**: 모든 함수에 타입 힌트 권장
- **Docstrings**: 공개 API에 필수
- **Import Order**: standard library → third-party → local

## 서브 CLAUDE.md 목록

| 경로 | 설명 | 마켓 |
|------|------|------|
| [trading_bot/CLAUDE.md](trading_bot/CLAUDE.md) | 트레이딩 봇 핵심 모듈 (전략, 백테스터, 최적화) | 암호화폐 + 해외주식 |
| [trading_bot/brokers/CLAUDE.md](trading_bot/brokers/CLAUDE.md) | 브로커 통합 인터페이스 (CCXT, 한국투자증권) | 암호화폐 + 주식 |
| [trading_bot/strategies/CLAUDE.md](trading_bot/strategies/CLAUDE.md) | 전략 구현 가이드 (RSI, MACD, MA 등) | 암호화폐 + 해외주식 |
| [dashboard/CLAUDE.md](dashboard/CLAUDE.md) | Streamlit 대시보드 규칙 | 공통 |
| [tests/CLAUDE.md](tests/CLAUDE.md) | 테스트 작성 가이드 | 공통 |
| [examples/CLAUDE.md](examples/CLAUDE.md) | 예제 스크립트 사용법 | 공통 |

## 자주 사용하는 명령어

```bash
# 테스트 실행
pytest 2>&1 | tee .context/terminal/test_$(date +%s).log

# 커버리지 포함 테스트
pytest --cov=trading_bot 2>&1 | tee .context/terminal/test_cov_$(date +%s).log

# 특정 테스트 파일 실행
pytest tests/test_rsi_strategy.py -v 2>&1 | tee .context/terminal/test_rsi_$(date +%s).log

# 대시보드 실행
streamlit run dashboard/app.py 2>&1 | tee .context/terminal/dashboard_$(date +%s).log

# 의존성 설치
pip install -r requirements.txt 2>&1 | tee .context/terminal/install_$(date +%s).log

# 백테스트 예제 실행
python examples/run_backtest_example.py 2>&1 | tee .context/terminal/backtest_$(date +%s).log
```

## 터미널 로그 정리

최근 10개 로그만 유지:
```bash
ls -t .context/terminal/*.log | tail -n +11 | xargs rm -f
```

---

This document provides technical details for developers working on or extending the crypto trading bot.

## Architecture Overview

The bot follows a modular architecture with clear separation of concerns:

1. **Broker Layer**: Unified interface for exchanges and brokerages (CCXT, Korea Investment)
2. **Data Layer**: Data acquisition (real or simulated)
3. **Strategy Layer**: Trading logic and signal generation
4. **Execution Layer**: Backtesting and paper trading
5. **Analysis Layer**: Performance metrics and optimization

## Core Components

### 1. Data Sources

#### SimulationDataGenerator (`trading_bot/simulation_data.py`)

Generates synthetic OHLCV data for backtesting without exchange connection.

**Key Methods:**
- `generate_ohlcv()`: Base method using Geometric Brownian Motion
- `generate_trend_data()`: Pre-configured trending markets
- `generate_volatile_data()`: High volatility scenarios
- `generate_cyclical_data()`: Sine wave patterns
- `add_market_shock()`: Inject sudden price movements

**Geometric Brownian Motion Formula:**
```
dS = μ * S * dt + σ * S * dW
```
- S: asset price
- μ: drift (trend direction)
- σ: volatility
- dW: Wiener process (random shock)

#### DataHandler (`trading_bot/data_handler.py`)

Fetches real historical data from exchanges via CCXT.

**Note**: Not required for simulation-only backtesting.

### 2. Trading Strategies

All strategies implement a common interface for consistency.

#### Strategy Interface

```python
class Strategy:
    def __init__(self, **params):
        self.name = "Strategy_Name"

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns DataFrame with:
        - Original OHLCV columns
        - Indicator columns (strategy-specific)
        - 'signal': 1 (BUY), -1 (SELL), 0 (HOLD)
        - 'position': 1 (long), 0 (flat)
        """
        pass

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """Returns: (signal, info_dict)"""
        pass

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """Returns list of all signal events"""
        pass
```

#### Implemented Strategies

**Moving Average Crossover** (`trading_bot/strategy.py`)
- Fast MA crosses above Slow MA → BUY
- Fast MA crosses below Slow MA → SELL
- Parameters: `fast_period`, `slow_period`

**RSI Strategy** (`trading_bot/strategies/rsi_strategy.py`)
- RSI formula: `RSI = 100 - (100 / (1 + RS))`
- RS = Average Gain / Average Loss over period
- RSI < oversold (30) → BUY
- RSI > overbought (70) → SELL
- Parameters: `period`, `overbought`, `oversold`

**MACD Strategy** (`trading_bot/strategies/macd_strategy.py`)
- MACD Line = EMA(12) - EMA(26)
- Signal Line = EMA(9) of MACD Line
- Histogram = MACD Line - Signal Line
- MACD crosses above Signal → BUY
- MACD crosses below Signal → SELL
- Parameters: `fast_period`, `slow_period`, `signal_period`

### 3. Backtesting Engine

#### Backtester (`trading_bot/backtester.py`)

Simulates trading on historical data.

**Key Features:**
- Position sizing based on capital percentage
- Commission/fee simulation
- Equity curve tracking
- Performance metrics calculation

**Performance Metrics:**
- **Total Return**: `(final_capital - initial_capital) / initial_capital * 100`
- **Sharpe Ratio**: `(mean_returns / std_returns) * sqrt(252)` (annualized)
- **Max Drawdown**: `min((equity - peak_equity) / peak_equity * 100)`
- **Win Rate**: `winning_trades / total_trades * 100`

**Execution Logic:**
1. Iterate through historical data
2. Calculate strategy signals
3. Execute trades on signal changes
4. Track equity and positions
5. Calculate final metrics

### 4. Strategy Optimizer

#### StrategyOptimizer (`trading_bot/optimizer.py`)

Finds optimal parameters and compares strategies.

**Key Methods:**

**`optimize(strategy_class, df, param_grid)`**
- Grid search over parameter space
- Tests all combinations
- Returns best parameters by specified metric

**`compare_strategies(strategies, df)`**
- Backtests multiple strategies on same data
- Returns comparison DataFrame
- Useful for strategy selection

**`analyze_parameter_sensitivity(param_name, metric)`**
- Shows how changing one parameter affects performance
- Helps identify robust vs. fragile parameters

**Optimization Best Practices:**
1. Use simulation data with different market regimes
2. Avoid overfitting - test on out-of-sample data
3. Consider multiple metrics (return, Sharpe, drawdown)
4. Look for robust parameters (consistent across ranges)

### 5. Configuration

#### Config (`trading_bot/config.py`)

Centralized configuration management.

**Default Configuration:**
```python
{
    'exchange': 'binance',
    'symbol': 'BTC/USDT',
    'timeframe': '1h',
    'initial_capital': 10000.0,
    'position_size': 0.95,
    'backtesting': {...},
    'paper_trading': {...}
}
```

## Data Flow

### Backtesting Flow

```
SimulationDataGenerator
    ↓
OHLCV DataFrame
    ↓
Strategy.calculate_indicators()
    ↓
DataFrame + Signals
    ↓
Backtester.run()
    ↓
Performance Metrics
```

### Optimization Flow

```
Parameter Grid
    ↓
StrategyOptimizer.optimize()
    ↓
For each parameter combination:
    Strategy Instance
        ↓
    Backtester.run()
        ↓
    Store Results
    ↓
Rank by Metric
    ↓
Best Parameters
```

## Testing

### Unit Tests

Each component has corresponding tests in `tests/`:

- `test_rsi_strategy.py`: RSI calculation and signals
- `test_macd_strategy.py`: MACD calculation and signals
- `test_simulation_data.py`: Data generation validation
- `test_optimizer.py`: Optimization logic
- `test_backtester.py`: Backtest execution

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/test_rsi_strategy.py

# With coverage
pytest --cov=trading_bot --cov-report=html

# Verbose output
pytest -v
```

## Extending the Bot

### Adding a New Strategy

1. **Create strategy file**: `trading_bot/strategies/my_strategy.py`

2. **Implement interface**:
```python
class MyStrategy:
    def __init__(self, **params):
        self.name = "MyStrategy"

    def calculate_indicators(self, df):
        data = df.copy()
        # Your logic here
        data['signal'] = 0  # Generate signals
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)
        return data

    def get_current_signal(self, df):
        # Implementation
        pass

    def get_all_signals(self, df):
        # Implementation
        pass
```

3. **Add to `__init__.py`**:
```python
from .my_strategy import MyStrategy
__all__ = [..., 'MyStrategy']
```

4. **Write tests**: `tests/test_my_strategy.py`

5. **Test with backtester**:
```python
strategy = MyStrategy(param=value)
backtester = Backtester(strategy)
results = backtester.run(df)
```

### Adding New Metrics

Extend `Backtester._calculate_metrics()`:

```python
def _calculate_metrics(self, data):
    # Existing metrics...

    # Add new metric
    my_metric = self._calculate_my_metric()

    results['my_metric'] = my_metric
    return results
```

### Custom Data Generators

Extend `SimulationDataGenerator`:

```python
class MyDataGenerator(SimulationDataGenerator):
    def generate_custom_scenario(self, **kwargs):
        # Custom data generation logic
        return df
```

## Performance Optimization

### Backtesting Performance

- Use vectorized operations (pandas/numpy)
- Avoid loops when possible
- Cache indicator calculations
- Use `.copy()` judiciously

### Memory Management

- For large datasets, consider chunking
- Use appropriate dtypes (float32 vs float64)
- Clear unused DataFrames

## Common Pitfalls

### 1. Look-Ahead Bias

❌ **Wrong**: Using future data in signals
```python
data['signal'] = (data['close'] > data['close'].shift(-1))  # Uses future!
```

✅ **Correct**: Only use past data
```python
data['signal'] = (data['close'] > data['close'].shift(1))
```

### 2. Signal Timing

Signals should be based on the **close** of the current bar and executed at the **next bar's open** (or current close for simplicity).

### 3. Overfitting

- Too many parameters → overfitting
- Optimize on in-sample data, validate on out-of-sample
- Test across different market regimes

### 4. Commission Impact

Small edges disappear with commissions. Always include realistic fees.

## File Locations

### Code
- `/Users/shlee/crypto-trading-bot/trading_bot/` - Main package
- `/Users/shlee/crypto-trading-bot/trading_bot/strategies/` - Strategy implementations
- `/Users/shlee/crypto-trading-bot/dashboard/` - Streamlit dashboard

### Data
- `/Users/shlee/crypto-trading-bot/data/` - Cached historical data

### Tests
- `/Users/shlee/crypto-trading-bot/tests/` - Unit tests

### Examples
- `/Users/shlee/crypto-trading-bot/examples/` - Example scripts

## Dependencies

### Core
- `pandas`: Data manipulation
- `numpy`: Numerical operations
- `ccxt`: Exchange connectivity (optional)

### Visualization
- `streamlit`: Dashboard
- `plotly`: Interactive charts
- `matplotlib`: Static plots

### Testing
- `pytest`: Test framework
- `pytest-cov`: Coverage reports

## Development Workflow

1. **Feature Development**
   - Create feature branch
   - Implement changes
   - Write/update tests
   - Ensure tests pass

2. **Testing**
   - Unit tests for new code
   - Integration tests for workflows
   - Backtest on multiple scenarios

3. **Documentation**
   - Update README.md for user-facing changes
   - Update CLAUDE.md for developer details
   - Add docstrings to new code

4. **Deployment**
   - Merge to main
   - Tag releases
   - Update changelog

## Current Development Status

### Phase 1: Paper Trading End-to-End (✅ 완료 - 2026-02-08)
- ✅ PaperTrader 구현 (멀티 심볼, 실시간 실행)
- ✅ TradingDatabase (SQLite 세션 추적)
- ✅ Dashboard Paper Trading 탭 통합
- ✅ Strategy Comparison 탭
- ✅ Strategy Preset Management (2026-02-09)
- ✅ Stop Loss & Take Profit 기능

### Phase 2: Automation Scheduler (🚧 진행중)
- 🚧 APScheduler 통합 (`scheduler.py`)
- 🚧 Slack/Email 알림 서비스 (`notifications.py`)
- ⏳ 미국 시장 시간 자동 실행 (23:30-06:00 KST)
- ⏳ 일일 리포트 자동 생성

### Phase 3: Live Trading (계획중)
- RiskManager 클래스 (일일 손실 제한, 포지션 크기 제한)
- LiveTrader (실제 주문 실행)
- 2단계 확인 UI
- 상세 로깅 및 감사 추적

### Phase 4: Advanced Features (계획중)
- LLM 통합 (신호 개선)
- 포트폴리오 최적화 (멀티 전략 배분)
- 머신러닝 전략 (LSTM, XGBoost)

## Project Root Files

### `scheduler.py` - 자동화 스케줄러 (Phase 2)

APScheduler를 사용하여 Paper Trading을 자동으로 실행합니다.

**주요 기능**:
- 미국 시장 시간에 자동 실행 (23:30-06:00 KST)
- 장 시작 전 전략 최적화 (23:00 KST)
- 장 마감 후 자동 종료 및 리포트 생성 (06:00 KST)
- Slack/Email 알림 통합

**실행 명령어**:
```bash
python scheduler.py
```

**환경 변수 요구사항**:
- KIS API 인증 정보 (`.env`)
- Slack Webhook URL (선택)
- Email SMTP 설정 (선택)

**스케줄**:
- `23:00 KST`: 전략 최적화
- `23:30 KST`: Paper Trading 시작 (미국 시장 개장)
- `06:00 KST`: Paper Trading 종료 (미국 시장 마감)

**로그 파일**:
- 경로: `logs/scheduler.log`
- 모든 스케줄 실행 기록 저장

## Future Enhancements

### Potential Features
- Portfolio management (multiple assets)
- Advanced order types (limit, stop-limit)
- Walk-forward optimization
- Monte Carlo simulation
- Machine learning strategies

### Performance Improvements
- Parallel backtesting
- Cython for critical paths
- GPU acceleration for ML strategies

## Troubleshooting

### Common Issues

**Import errors**
```bash
pip install -r requirements.txt
```

**NaN in indicators**
- Indicators need warm-up period
- First N rows will be NaN (N = indicator period)
- Filter or handle appropriately

**No trades executed**
- Check signal generation
- Verify data has sufficient rows
- Inspect indicator values

**Poor backtest performance**
- Try different parameters
- Check for look-ahead bias
- Verify commission settings
- Test on different market regimes

## Resources

### Technical Analysis
- Investopedia: Technical indicators
- "Technical Analysis of the Financial Markets" by Murphy
- QuantStart blog

### Python Trading
- Zipline documentation
- Backtrader documentation
- QuantConnect tutorials

### Backtesting Best Practices
- "Advances in Financial Machine Learning" by López de Prado
- "Evidence-Based Technical Analysis" by Aronson

## Contact

For questions or contributions, please open an issue on GitHub.
