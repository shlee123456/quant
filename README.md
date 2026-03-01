# Multi-Asset Trading Bot

A multi-asset trading bot supporting cryptocurrencies and stocks (domestic & international) with backtesting, strategy optimization, and simulation capabilities.

## Features

- **Multi-Asset Broker Support**
  - **Cryptocurrencies**: 100+ exchanges via CCXT (Binance, Upbit, Coinbase, etc.)
  - **Domestic Stocks**: Korea Investment Securities (KOSPI, KOSDAQ)
  - **International Stocks**: Korea Investment Securities (US, Hong Kong, Japan, China)
  - Unified interface across all brokers

- **Multiple Trading Strategies**
  - Moving Average Crossover (MA)
  - Relative Strength Index (RSI)
  - Moving Average Convergence Divergence (MACD)

- **Backtesting Engine**
  - Test strategies on historical data
  - Performance metrics (return, Sharpe ratio, max drawdown, win rate)
  - Trade history and equity curve tracking

- **Simulation Data Generator**
  - Generate realistic OHLCV data without exchange connection
  - Multiple market scenarios (bullish, bearish, sideways, volatile, cyclical)
  - Reproducible with seed support

- **Strategy Optimizer**
  - Grid search for optimal parameters
  - Compare multiple strategies
  - Parameter sensitivity analysis

- **Paper Trading** (Phase 1 Complete)
  - Real-time simulation with live market data
  - Multi-symbol portfolio tracking (up to 7 US stocks simultaneously)
  - SQLite database for session history and performance metrics
  - Automated trade execution based on strategy signals
  - Portfolio snapshots with P&L tracking
  - Interactive dashboard with Streamlit
  - Session comparison and equity curve visualization

- **Automated Scheduler** (Phase 2 Complete)
  - APScheduler integration for cron-based execution
  - Automatic trading during US market hours (23:30-06:00 KST)
  - Post-market reporting and analysis
  - Slack and Email notifications
  - Trade alerts, daily reports, and error notifications
  - Graceful shutdown handling

## Installation

### Option 1: Docker (Recommended)

```bash
# 1. Clone repository
git clone <repository-url>
cd crypto-trading-bot

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env and add your API keys

# 3. Build and run
./scripts/docker-build.sh
./scripts/docker-run.sh

# 4. Access dashboard
open http://localhost:8501
```

See [Docker Deployment Guide](docs/DOCKER_DEPLOYMENT.md) for detailed instructions.

### Option 2: Local Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd crypto-trading-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Install broker-specific libraries:
```bash
# For cryptocurrency trading
pip install ccxt

# For Korea Investment Securities (stocks)
pip install python-kis
```

## API Setup

### Korea Investment Securities API Setup (한국투자증권)

To use real-time quotes and trading for domestic and international stocks, you need to set up Korea Investment Securities API credentials.

#### 1. Sign up and get API credentials

**For Mock Trading (모의투자) - Recommended for testing:**
1. Visit [KIS API Portal](https://apiportal.koreainvestment.com/intro)
2. Register for a mock trading account
3. Navigate to [API신청] menu and create a new app
4. You will receive:
   - APPKEY (앱키)
   - APPSECRET (앱시크릿)
   - Mock account number (모의투자 계좌번호)

**For Real Trading (실전투자) - Use with caution:**
1. Visit [KIS API Portal](https://apiportal.koreainvestment.com/intro)
2. Link your real trading account
3. Create a new app in [API신청] menu
4. You will receive different APPKEY and APPSECRET for real trading

#### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` file:
```bash
# Korea Investment Securities
KIS_APPKEY=your_actual_appkey_here
KIS_APPSECRET=your_actual_appsecret_here
KIS_ACCOUNT=12345678-01  # Your account number
KIS_MOCK=true  # Set to false for real trading
```

**⚠️ Important:**
- Mock trading (KIS_MOCK=true): Uses virtual funds, no real trades executed
- Real trading (KIS_MOCK=false): Uses real funds, actual trades will be executed!
- Mock and real trading require different APPKEY/APPSECRET
- Never commit `.env` file to Git (it's in `.gitignore`)

#### 3. Verify setup

You can verify your setup in the dashboard:
```bash
streamlit run dashboard/app.py
```

Navigate to the "📊 Real-time Quotes" tab. If credentials are set correctly, you should be able to fetch live stock quotes.

## Quick Start

### 1. Using Brokers

#### Cryptocurrency Trading (CCXT)
```python
from trading_bot.brokers import CCXTBroker

# Fetch OHLCV data from Binance
broker = CCXTBroker('binance')
df = broker.fetch_ohlcv('BTC/USDT', '1h', limit=100)

# Create order (requires API keys)
broker = CCXTBroker('binance', api_key='YOUR_KEY', secret='YOUR_SECRET')
order = broker.create_order('BTC/USDT', 'market', 'buy', 0.01)
```

#### Stock Trading (Korea Investment)
```python
from trading_bot.brokers import KoreaInvestmentBroker

# Initialize broker
broker = KoreaInvestmentBroker(
    appkey='YOUR_APPKEY',
    appsecret='YOUR_APPSECRET',
    account='12345678-01',
    mock=True  # Use mock trading
)

# Fetch domestic stock data (Samsung Electronics)
df = broker.fetch_ohlcv('005930', '1d', limit=100)

# Fetch US stock data (Apple)
df = broker.fetch_ohlcv('AAPL', '1d', limit=100, overseas=True)

# Create order
order = broker.create_order('005930', 'market', 'buy', 10)
```

### 2. Backtesting with Simulation Data

```python
from trading_bot.simulation_data import SimulationDataGenerator
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.backtester import Backtester

# Generate simulation data
data_gen = SimulationDataGenerator(seed=42)
df = data_gen.generate_trend_data(periods=1000, trend='bullish')

# Create strategy
strategy = RSIStrategy(period=14, overbought=70, oversold=30)

# Run backtest
backtester = Backtester(strategy, initial_capital=10000)
results = backtester.run(df)
backtester.print_results(results)
```

### 3. Comparing Multiple Strategies

```python
from trading_bot.strategies.rsi_strategy import RSIStrategy
from trading_bot.strategies.macd_strategy import MACDStrategy
from trading_bot.strategy import MovingAverageCrossover
from trading_bot.optimizer import StrategyOptimizer

# Create strategies
strategies = [
    MovingAverageCrossover(fast_period=10, slow_period=30),
    RSIStrategy(period=14),
    MACDStrategy()
]

# Compare strategies
optimizer = StrategyOptimizer(initial_capital=10000)
comparison = optimizer.compare_strategies(strategies, df)
print(comparison)
```

### 4. Optimizing Strategy Parameters

```python
from trading_bot.optimizer import StrategyOptimizer
from trading_bot.strategies.rsi_strategy import RSIStrategy

# Define parameter grid
param_grid = {
    'period': [7, 14, 21, 28],
    'overbought': [65, 70, 75, 80],
    'oversold': [20, 25, 30, 35]
}

# Optimize
optimizer = StrategyOptimizer(initial_capital=10000)
best_result = optimizer.optimize(RSIStrategy, df, param_grid)

print(f"Best parameters: {best_result['params']}")
print(f"Total return: {best_result['total_return']:.2f}%")
```

### 5. Generate Different Market Scenarios

```python
from trading_bot.simulation_data import SimulationDataGenerator

data_gen = SimulationDataGenerator(seed=42)

# Bullish market
bullish_data = data_gen.generate_trend_data(periods=1000, trend='bullish')

# Bearish market
bearish_data = data_gen.generate_trend_data(periods=1000, trend='bearish')

# Sideways market
sideways_data = data_gen.generate_trend_data(periods=1000, trend='sideways')

# Volatile market
volatile_data = data_gen.generate_volatile_data(periods=1000)

# Cyclical market
cyclical_data = data_gen.generate_cyclical_data(periods=1000, cycle_length=100)
```

### 6. Paper Trading - Real-time Simulation

Paper trading allows you to test strategies with real market data without risking capital. See [examples/run_paper_trading.py](examples/run_paper_trading.py) for a complete example.

```python
from trading_bot.paper_trader import PaperTrader
from trading_bot.strategies import RSIStrategy
from trading_bot.database import TradingDatabase
from dashboard.kis_broker import get_kis_broker

# Initialize components
strategy = RSIStrategy(period=14, overbought=70, oversold=30)
broker = get_kis_broker()  # Requires KIS API credentials
db = TradingDatabase()  # Stores session history

# Create paper trader for multiple symbols
trader = PaperTrader(
    strategy=strategy,
    symbols=['AAPL', 'MSFT', 'GOOGL'],  # Trade multiple stocks
    broker=broker,
    initial_capital=10000.0,
    position_size=0.3,  # Use 30% of capital per trade
    db=db
)

# Run real-time paper trading (60 second intervals)
trader.run_realtime(interval_seconds=60, timeframe='1d')

# Or use the dashboard for interactive paper trading
# streamlit run dashboard/app.py
```

#### Database Schema

Paper trading sessions are stored in SQLite (`data/paper_trading.db`) with the following schema:

**Sessions Table:**
- `session_id`: Unique session identifier (strategy_name_timestamp)
- `strategy_name`: Strategy used (e.g., "RSI_14_30_70")
- `start_time`, `end_time`: Session duration
- `initial_capital`, `final_capital`: Capital tracking
- `total_return`, `sharpe_ratio`, `max_drawdown`, `win_rate`: Performance metrics
- `status`: Session status (active/completed)

**Trades Table:**
- Records all trades with symbol, timestamp, type (BUY/SELL), price, size, commission, P&L

**Portfolio Snapshots:**
- Periodic portfolio value snapshots with cash and positions

### 7. Strategy Presets - Save and Load Configurations

Strategy presets allow you to save your favorite trading configurations and load them later without manually adjusting settings each time.

```python
from trading_bot.strategy_presets import StrategyPresetManager

# Initialize preset manager
manager = StrategyPresetManager()  # Saves to data/strategy_presets.json

# Save a preset
manager.save_preset(
    name="보수적 RSI 전략",
    strategy="RSI Strategy",
    strategy_params={"period": 14, "overbought": 70, "oversold": 30},
    initial_capital=10000.0,
    position_size=0.3,
    symbols=["AAPL", "MSFT"],
    stop_loss_pct=0.03,   # 3% stop loss
    take_profit_pct=0.06,  # 6% take profit
    enable_stop_loss=True,
    enable_take_profit=True,
    description="안정적인 수익을 추구하는 보수적 전략"
)

# Load a preset
preset = manager.load_preset("보수적 RSI 전략")
print(f"Strategy: {preset['strategy']}")
print(f"Symbols: {preset['symbols']}")
print(f"Parameters: {preset['strategy_params']}")

# List all presets
all_presets = manager.list_presets()
for p in all_presets:
    print(f"{p['name']} - {p['strategy']}")

# Delete a preset
manager.delete_preset("보수적 RSI 전략")

# Export/Import presets
manager.export_preset("보수적 RSI 전략", "my_preset.json")
manager.import_preset("my_preset.json")
```

#### Dashboard Integration

The dashboard's **Paper Trading** tab includes a built-in preset management UI:

1. **Load Presets**: Select a saved preset from the dropdown and click "불러오기" to populate all form fields
2. **Save Presets**: Configure your strategy settings, enter a preset name, and click "프리셋 저장"
3. **Delete Presets**: Select a preset and click "삭제" to remove it
4. **Preset Details**: View full configuration details in the expandable section

This feature is especially useful for:
- **Quick Testing**: Switch between different strategies without manual reconfiguration
- **Strategy Comparison**: Save multiple variations of the same strategy with different parameters
- **Risk Management**: Save conservative and aggressive versions of strategies
- **Sharing**: Export presets as JSON files to share with others

**Strategy Signals:**
- All strategy signals generated with indicator values and execution status

See the **Session Comparison** tab in the dashboard to compare performance across multiple sessions.

## Strategy Interface

All strategies follow the same interface:

```python
class Strategy:
    def __init__(self, **params):
        """Initialize with strategy-specific parameters"""
        self.name = "Strategy_Name"

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate indicators and generate signals

        Returns DataFrame with:
        - indicator columns (strategy-specific)
        - 'signal': 1 (BUY), -1 (SELL), 0 (HOLD)
        - 'position': current position
        """
        pass

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        """Get the most recent signal"""
        pass

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        """Get all signals from historical data"""
        pass
```

## Project Structure

```
crypto-trading-bot/
├── trading_bot/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── data_handler.py        # Exchange data fetching (CCXT)
│   ├── simulation_data.py     # Simulation data generator
│   ├── strategy.py            # MA crossover strategy
│   ├── brokers/               # Broker integrations
│   │   ├── __init__.py
│   │   ├── base_broker.py     # Abstract broker interface
│   │   ├── ccxt_broker.py     # CCXT cryptocurrency broker
│   │   └── korea_investment_broker.py  # Korea Investment Securities
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── rsi_strategy.py    # RSI strategy
│   │   └── macd_strategy.py   # MACD strategy
│   ├── backtester.py          # Backtesting engine
│   ├── optimizer.py           # Strategy optimizer
│   └── paper_trader.py        # Paper trading
├── dashboard/                 # Streamlit dashboard
├── tests/                     # Unit tests
├── examples/                  # Example scripts
├── data/                      # Historical data cache
├── docs/                      # Documentation
│   ├── broker_comparison.md   # Broker comparison
│   ├── kiwoom_api_research.md # Kiwoom research
│   └── korea_investment_api_research.md  # Korea Investment research
├── requirements.txt
├── README.md
└── CLAUDE.md
```

## Running Tests

```bash
# Run all tests (excluding slow tests)
pytest -m "not slow"

# Run all tests including slow tests
pytest

# Run only slow tests (API integration tests)
pytest -m slow

# Run with coverage
pytest --cov=trading_bot

# Run specific test file
pytest tests/test_rsi_strategy.py

# Verbose output
pytest -v
```

### Test Markers

- **`slow`**: Tests that make external API calls (KIS API, exchange APIs)
  - These tests may take longer to run
  - May hit rate limits if run too frequently
  - Skip with: `pytest -m "not slow"`
  - Run only slow tests: `pytest -m slow`

## Dashboard

### With Docker
```bash
./scripts/docker-run.sh dashboard
# Access: http://localhost:8501
```

### Without Docker
```bash
streamlit run dashboard/app.py
```

## Performance Metrics

The backtester calculates the following metrics:

- **Total Return**: Percentage gain/loss from initial capital
- **Sharpe Ratio**: Risk-adjusted return (annualized)
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Average Win/Loss**: Average profit/loss per trade
- **Total Trades**: Number of completed trades

## Exchange Integration (Optional)

To connect to real exchanges for historical data:

1. Get API keys from your exchange
2. Configure in `config.py` or use environment variables:

```python
from trading_bot.config import Config

config = Config()
config['api_key'] = 'your_api_key'
config['api_secret'] = 'your_api_secret'
config['exchange'] = 'binance'  # or other CCXT-supported exchange
```

**Note**: For backtesting and research, simulation data is recommended as it doesn't require exchange API access.

## Adding New Strategies

To create a new strategy:

1. Create a new file in `trading_bot/strategies/`
2. Implement the strategy interface
3. Add tests in `tests/`

Example:

```python
# trading_bot/strategies/my_strategy.py
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

class MyStrategy:
    def __init__(self, param1: int = 10):
        self.param1 = param1
        self.name = f"MyStrategy_{param1}"

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        # Calculate your indicators
        data['my_indicator'] = ...

        # Generate signals
        data['signal'] = 0  # 1 = BUY, -1 = SELL, 0 = HOLD
        data['position'] = data['signal'].replace(0, np.nan).ffill().fillna(0)

        return data

    def get_current_signal(self, df: pd.DataFrame) -> Tuple[int, Dict]:
        data = self.calculate_indicators(df)
        last_row = data.iloc[-1]
        return int(last_row['signal']), {'info': 'dict'}

    def get_all_signals(self, df: pd.DataFrame) -> List[Dict]:
        data = self.calculate_indicators(df)
        signals_df = data[data['signal'] != 0]
        return signals_df.to_dict('records')
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License

## Disclaimer

This software is for educational and research purposes only. Cryptocurrency trading carries significant risk. Do not use this bot with real money without thorough testing and understanding of the risks involved. The authors are not responsible for any financial losses.

## Support

For issues and questions:
- Open an issue on GitHub
- Check the documentation in `CLAUDE.md`
