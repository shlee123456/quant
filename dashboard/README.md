# Enhanced Trading Dashboard

A comprehensive Streamlit-based dashboard for backtesting, comparing, and monitoring cryptocurrency trading strategies.

## Features

### 1. Multi-Strategy Support
The dashboard supports multiple trading strategies with automatic parameter configuration:

- **Moving Average Crossover**: Fast and slow moving average crossover signals
- **RSI Strategy**: Relative Strength Index with overbought/oversold levels
- **MACD Strategy**: Moving Average Convergence Divergence with signal line
- **Bollinger Bands**: Price bands based on standard deviation
- **Stochastic Oscillator**: (Coming soon) Momentum indicator with %K and %D lines

### 2. Dynamic Parameter Tuning
Each strategy has customizable parameters through an intuitive slider interface:

**Moving Average Crossover**
- Fast MA Period (5-50, default: 10)
- Slow MA Period (10-200, default: 30)

**RSI Strategy**
- RSI Period (5-30, default: 14)
- Overbought Level (60-90, default: 70)
- Oversold Level (10-40, default: 30)

**MACD Strategy**
- Fast EMA Period (5-20, default: 12)
- Slow EMA Period (20-40, default: 26)
- Signal Period (5-15, default: 9)

**Bollinger Bands**
- Period (10-50, default: 20)
- Standard Deviations (1.0-3.0, default: 2.0)

### 3. Strategy Comparison
Compare multiple strategies side-by-side on the same dataset:

- Multi-select interface for choosing strategies
- Independent parameter configuration for each strategy
- Performance metrics comparison table with highlighting
- Visual comparison charts (returns, Sharpe ratio)
- All strategies tested on identical data for fair comparison

### 4. Enhanced Visualizations

#### Strategy-Specific Charts
Each strategy has customized visualizations showing relevant indicators:

**Moving Average Crossover**
- Candlestick price chart
- Fast and Slow MA lines
- Buy/Sell signal markers
- Volume subplot

**RSI Strategy**
- Candlestick price chart
- RSI indicator subplot (0-100 scale)
- Overbought (70) and Oversold (30) threshold lines
- Buy/Sell signal markers
- Volume subplot

**MACD Strategy**
- Candlestick price chart
- MACD line and Signal line
- MACD histogram (colored by direction)
- Buy/Sell signal markers
- Volume subplot

**Bollinger Bands**
- Candlestick price chart
- Upper, Middle, and Lower Bollinger Bands
- Shaded band area
- Buy/Sell signal markers
- Volume subplot

All charts are interactive with:
- Zoom and pan capabilities
- Hover tooltips showing exact values
- Toggle visibility of individual indicators
- Export to PNG functionality

### 5. Performance Metrics

Comprehensive performance analysis including:

- **Total Return**: Percentage and dollar value
- **Sharpe Ratio**: Risk-adjusted return metric
- **Max Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Total Trades**: Number of trades executed
- **Initial/Final Capital**: Starting and ending portfolio values

### 6. Data Sources

Choose between:
- **Simulation Data**: Generated using Geometric Brownian Motion for testing
- **Real Market Data**: Historical data from exchanges via CCXT (requires exchange connection)

### 7. Four Main Tabs

**📊 Backtesting**
- Run backtests on historical or simulated data
- View detailed performance metrics
- Analyze equity curves
- Review trade history

**🔍 Strategy Comparison**
- Compare 2+ strategies simultaneously
- Configure parameters independently
- View side-by-side metrics
- Visual performance comparison

**📄 Paper Trading** (requires real data)
- Live paper trading with virtual capital
- Real-time portfolio tracking
- Automatic strategy execution
- Trade history logging

**📡 Live Monitor** (requires real data)
- Real-time market monitoring
- Current signal display
- Strategy indicator values
- Auto-refresh capability

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Verify installation:
```bash
python examples/test_dashboard.py
```

## Usage

### Starting the Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

### Basic Workflow

1. **Configure in Sidebar**
   - Choose data source (simulation or real)
   - Select trading strategy
   - Adjust strategy parameters
   - Set initial capital
   - Click "Initialize System"

2. **Run Backtest**
   - Navigate to "Backtesting" tab
   - Choose date range (for real data) or periods (for simulation)
   - Click "Run Backtest"
   - Review performance metrics and charts

3. **Compare Strategies**
   - Navigate to "Strategy Comparison" tab
   - Select multiple strategies to compare
   - Configure parameters for each
   - Click "Run Comparison"
   - Analyze comparative performance

4. **Monitor Live** (optional, requires real data)
   - Disable "Use Simulation Data"
   - Navigate to "Live Monitor" or "Paper Trading"
   - Start monitoring or paper trading

## Testing

### Manual Testing
```bash
python examples/test_dashboard.py
```

This will:
- Test all 4 strategies
- Generate sample backtests
- Create all chart types
- Display performance summary

### Automated Tests
```bash
pytest tests/test_dashboard_integration.py -v
```

Tests include:
- Strategy backtest execution
- Chart generation
- Indicator calculations
- Signal generation
- Strategy comparison
- Data handling

## Architecture

### Key Components

**`dashboard/app.py`**
- Main Streamlit application
- UI layout and interaction logic
- Session state management
- Tab navigation

**`dashboard/charts.py`**
- Chart generation using Plotly
- Strategy-specific visualizations
- Helper methods for common chart elements

**`dashboard/README.md`**
- This file, comprehensive documentation

### Data Flow

```
User Input (Sidebar)
    ↓
Strategy Selection & Parameters
    ↓
Data Source (Simulation or Real)
    ↓
Strategy.calculate_indicators()
    ↓
Backtester.run()
    ↓
Results & Metrics
    ↓
ChartGenerator.plot_strategy_chart()
    ↓
Interactive Visualization
```

## Configuration

### Strategy Config Structure
```python
STRATEGY_CONFIGS = {
    'Strategy Name': {
        'class': StrategyClass,
        'params': {
            'param_name': {
                'min': 5,
                'max': 50,
                'default': 10,
                'label': 'Display Label',
                'step': 0.1  # Optional, for float params
            }
        },
        'description': 'Strategy description'
    }
}
```

### Adding New Strategies

1. Implement strategy class following the interface:
   - `calculate_indicators(df)` → DataFrame with indicators and signals
   - `get_current_signal(df)` → (signal, info_dict)
   - `get_all_signals(df)` → List of signal dicts

2. Add to `STRATEGY_CONFIGS` in `dashboard/app.py`

3. Add chart plotting method in `dashboard/charts.py`:
   - `_plot_[strategy_name]_strategy(data, trades_df)`

4. Test with `examples/test_dashboard.py`

## Troubleshooting

### Common Issues

**Import Errors**
```bash
pip install -r requirements.txt
```

**Dashboard Won't Start**
```bash
# Check if Streamlit is installed
streamlit --version

# Reinstall if needed
pip install --upgrade streamlit
```

**No Data in Charts**
- Ensure strategy is initialized (click "Initialize System")
- Check that backtest has been run
- Verify data has sufficient periods for indicator calculation

**Strategies Not Appearing**
- Check that strategy class is imported in `app.py`
- Verify strategy is added to `STRATEGY_CONFIGS`
- Ensure strategy follows the required interface

**Charts Not Displaying**
- Check browser console for JavaScript errors
- Try refreshing the page
- Verify Plotly is installed: `pip install plotly`

### Performance Tips

**For Large Datasets**
- Use simulation data for testing
- Limit backtest periods to reasonable ranges
- Close unused browser tabs

**For Faster Backtesting**
- Start with smaller period counts
- Use simulation data instead of API calls
- Avoid running too many strategies in comparison

## Future Enhancements

Potential additions:
- Stochastic Oscillator strategy (infrastructure ready)
- Portfolio optimization across multiple assets
- Walk-forward analysis
- Monte Carlo simulation
- Advanced risk metrics (Sortino ratio, Calmar ratio)
- Export results to CSV/Excel
- Save/load strategy configurations
- Automated parameter optimization
- Alert notifications
- Database integration for trade history

## Contributing

When adding features:
1. Follow existing code structure
2. Add corresponding tests
3. Update this README
4. Ensure all tests pass

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
- Check the troubleshooting section
- Review example scripts in `examples/`
- Run test suite to verify installation
- Check main project README
