"""
Paper trading simulator for live trading without real money
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from .strategy import MovingAverageCrossover
from .data_handler import DataHandler
import time
import json


class PaperTrader:
    """
    Paper trading simulator - trades with simulated money on real-time data
    """

    def __init__(self, strategy: MovingAverageCrossover, data_handler: DataHandler,
                 initial_capital: float = 10000.0, position_size: float = 0.95,
                 commission: float = 0.001, log_file: str = None):
        """
        Initialize paper trader

        Args:
            strategy: Trading strategy to use
            data_handler: Data handler for fetching live data
            initial_capital: Starting capital
            position_size: Fraction of capital to use per trade
            commission: Trading commission/fee
            log_file: Path to log file for trades (optional)
        """
        self.strategy = strategy
        self.data_handler = data_handler
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.log_file = log_file

        # Trading state
        self.capital = initial_capital
        self.position = 0  # Current position size
        self.entry_price = 0
        self.last_signal = 0

        # History
        self.trades = []
        self.equity_history = []

        # Running flag
        self.is_running = False

    def get_portfolio_value(self, current_price: float) -> float:
        """Calculate current portfolio value"""
        if self.position > 0:
            return self.capital + (self.position * current_price)
        return self.capital

    def execute_buy(self, price: float, timestamp: datetime):
        """Execute a buy order"""
        if self.position > 0:
            print("Already in position, skipping BUY signal")
            return

        trade_capital = self.capital * self.position_size
        self.position = trade_capital / price * (1 - self.commission)
        self.entry_price = price
        self.capital = self.capital - trade_capital

        trade = {
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'size': self.position,
            'capital': self.capital,
            'commission': trade_capital * self.commission
        }

        self.trades.append(trade)
        self._log_trade(trade)

        print(f"\n[BUY] {timestamp}")
        print(f"Price: ${price:.2f}")
        print(f"Size: {self.position:.6f}")
        print(f"Capital remaining: ${self.capital:.2f}")

    def execute_sell(self, price: float, timestamp: datetime):
        """Execute a sell order"""
        if self.position == 0:
            print("No position to sell, skipping SELL signal")
            return

        sale_proceeds = self.position * price * (1 - self.commission)
        self.capital = self.capital + sale_proceeds

        # Calculate profit/loss
        pnl = sale_proceeds - (self.position * self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price * 100

        trade = {
            'timestamp': timestamp,
            'type': 'SELL',
            'price': price,
            'size': self.position,
            'capital': self.capital,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'commission': self.position * price * self.commission
        }

        self.trades.append(trade)
        self._log_trade(trade)

        print(f"\n[SELL] {timestamp}")
        print(f"Price: ${price:.2f}")
        print(f"Size: {self.position:.6f}")
        print(f"P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"Capital: ${self.capital:.2f}")

        self.position = 0
        self.entry_price = 0

    def update(self, symbol: str, timeframe: str):
        """
        Update with latest market data and execute trades

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
        """
        # Fetch recent data
        df = self.data_handler.fetch_ohlcv(symbol, timeframe, limit=100)

        if df.empty:
            print("No data received")
            return

        # Get current signal
        signal, info = self.strategy.get_current_signal(df)

        current_price = info['close']
        timestamp = info['timestamp']

        # Track equity
        portfolio_value = self.get_portfolio_value(current_price)
        self.equity_history.append({
            'timestamp': timestamp,
            'equity': portfolio_value,
            'price': current_price,
            'position': self.position
        })

        # Execute trades based on signal
        if signal == 1 and self.last_signal != 1:  # New BUY signal
            self.execute_buy(current_price, timestamp)
        elif signal == -1 and self.last_signal != -1:  # New SELL signal
            self.execute_sell(current_price, timestamp)

        self.last_signal = signal

        # Print status
        self._print_status(info, portfolio_value)

    def run(self, symbol: str, timeframe: str, update_interval: int = 60):
        """
        Run paper trading in a loop

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            update_interval: Seconds between updates
        """
        print(f"\n{'='*60}")
        print(f"PAPER TRADING STARTED")
        print(f"{'='*60}")
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print(f"Strategy: {self.strategy}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Update Interval: {update_interval}s")
        print(f"{'='*60}\n")

        self.is_running = True

        try:
            while self.is_running:
                self.update(symbol, timeframe)
                time.sleep(update_interval)

        except KeyboardInterrupt:
            print("\n\nPaper trading stopped by user")
            self.stop()

    def stop(self):
        """Stop paper trading"""
        self.is_running = False
        self._print_summary()

    def _print_status(self, info: Dict, portfolio_value: float):
        """Print current status"""
        print(f"\n[{info['timestamp']}]")

        # Build indicator info string dynamically based on available fields
        indicator_parts = [f"Price: ${info['close']:.2f}"]

        # Add strategy-specific indicators if present
        if 'fast_ma' in info and 'slow_ma' in info:
            indicator_parts.append(f"Fast MA: ${info['fast_ma']:.2f}")
            indicator_parts.append(f"Slow MA: ${info['slow_ma']:.2f}")
        elif 'rsi' in info:
            indicator_parts.append(f"RSI: {info['rsi']:.2f}")
        elif 'macd_line' in info and 'signal_line' in info:
            indicator_parts.append(f"MACD: {info['macd_line']:.2f}")
            indicator_parts.append(f"Signal: {info['signal_line']:.2f}")

        print(" | ".join(indicator_parts))
        print(f"Position: {self.position:.6f} | Portfolio Value: ${portfolio_value:.2f}")
        print(f"Return: {((portfolio_value - self.initial_capital) / self.initial_capital * 100):+.2f}%")

    def _print_summary(self):
        """Print trading summary"""
        if not self.equity_history:
            print("No trading history")
            return

        final_value = self.equity_history[-1]['equity']
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        sell_trades = [t for t in self.trades if t['type'] == 'SELL']

        print(f"\n{'='*60}")
        print("PAPER TRADING SUMMARY")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Value: ${final_value:,.2f}")
        print(f"Total Return: {total_return:+.2f}%")
        print(f"Total Trades: {len(sell_trades)}")

        if sell_trades:
            winning = [t for t in sell_trades if t['pnl'] > 0]
            print(f"Winning Trades: {len(winning)}")
            print(f"Win Rate: {len(winning)/len(sell_trades)*100:.2f}%")

        print(f"{'='*60}\n")

    def _log_trade(self, trade: Dict):
        """Log trade to file"""
        if not self.log_file:
            return

        try:
            with open(self.log_file, 'a') as f:
                # Convert timestamp to string for JSON serialization
                trade_copy = trade.copy()
                trade_copy['timestamp'] = str(trade_copy['timestamp'])
                f.write(json.dumps(trade_copy) + '\n')
        except Exception as e:
            print(f"Error logging trade: {e}")

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        return pd.DataFrame(self.trades)

    def get_equity_df(self) -> pd.DataFrame:
        """Get equity history as DataFrame"""
        return pd.DataFrame(self.equity_history)
