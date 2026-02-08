"""
Paper trading simulator for live trading without real money
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from .strategy import MovingAverageCrossover
from .data_handler import DataHandler
from .brokers.base_broker import BaseBroker
from .database import TradingDatabase
import time
import json
import numpy as np


class PaperTrader:
    """
    Paper trading simulator - trades with simulated money on real-time data

    Supports:
    - Single or multiple symbols
    - Broker integration (for real-time data)
    - Database logging (optional)
    """

    def __init__(
        self,
        strategy: MovingAverageCrossover,
        symbols: Union[str, List[str]],
        data_handler: Optional[DataHandler] = None,
        broker: Optional[BaseBroker] = None,
        initial_capital: float = 10000.0,
        position_size: float = 0.95,
        commission: float = 0.001,
        log_file: Optional[str] = None,
        db: Optional[TradingDatabase] = None
    ):
        """
        Initialize paper trader

        Args:
            strategy: Trading strategy to use
            symbols: Trading symbol(s) - can be single string or list of strings
            data_handler: Data handler for fetching live data (deprecated, use broker)
            broker: Broker instance for fetching live data (recommended)
            initial_capital: Starting capital
            position_size: Fraction of capital to use per trade
            commission: Trading commission/fee
            log_file: Path to log file for trades (optional)
            db: TradingDatabase instance for persistent logging (optional)
        """
        self.strategy = strategy

        # Normalize symbols to list
        if isinstance(symbols, str):
            self.symbols = [symbols]
        else:
            self.symbols = symbols

        # Backward compatibility with data_handler
        self.data_handler = data_handler
        self.broker = broker

        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.log_file = log_file
        self.db = db

        # Trading state - track positions per symbol
        self.capital = initial_capital
        self.positions: Dict[str, float] = {symbol: 0.0 for symbol in self.symbols}
        self.entry_prices: Dict[str, float] = {symbol: 0.0 for symbol in self.symbols}
        self.last_signals: Dict[str, int] = {symbol: 0 for symbol in self.symbols}

        # History
        self.trades: List[Dict[str, Any]] = []
        self.equity_history: List[Dict[str, Any]] = []

        # Running flag
        self.is_running = False

        # Session tracking
        self.session_id: Optional[str] = None

    def get_portfolio_value(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate current portfolio value

        Args:
            current_prices: Dict mapping symbol to current price.
                           If None, only returns cash value.

        Returns:
            Total portfolio value (cash + positions)
        """
        if current_prices is None:
            current_prices = {}

        # Start with cash
        total_value = self.capital

        # Add value of all positions
        for symbol, position in self.positions.items():
            if position > 0 and symbol in current_prices:
                total_value += position * current_prices[symbol]

        return total_value

    def start(self):
        """
        Start a new paper trading session

        Creates database session if db is configured
        """
        if self.db and not self.session_id:
            self.session_id = self.db.create_session(
                strategy_name=self.strategy.name,
                initial_capital=self.initial_capital
            )
            print(f"Created session: {self.session_id}")

    def execute_buy(self, symbol: str, price: float, timestamp: datetime):
        """
        Execute a buy order

        Args:
            symbol: Trading symbol
            price: Buy price
            timestamp: Trade timestamp
        """
        if self.positions[symbol] > 0:
            print(f"Already in position for {symbol}, skipping BUY signal")
            return

        trade_capital = self.capital * self.position_size
        self.positions[symbol] = trade_capital / price * (1 - self.commission)
        self.entry_prices[symbol] = price
        self.capital = self.capital - trade_capital

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'BUY',
            'price': price,
            'size': self.positions[symbol],
            'capital': self.capital,
            'commission': trade_capital * self.commission
        }

        self.trades.append(trade)
        self._log_trade(trade)

        # Log to database
        if self.db and self.session_id:
            self.db.log_trade(self.session_id, trade)

        print(f"\n[BUY] {symbol} {timestamp}")
        print(f"Price: ${price:.2f}")
        print(f"Size: {self.positions[symbol]:.6f}")
        print(f"Capital remaining: ${self.capital:.2f}")

    def execute_sell(self, symbol: str, price: float, timestamp: datetime):
        """
        Execute a sell order

        Args:
            symbol: Trading symbol
            price: Sell price
            timestamp: Trade timestamp
        """
        if self.positions[symbol] == 0:
            print(f"No position to sell for {symbol}, skipping SELL signal")
            return

        sale_proceeds = self.positions[symbol] * price * (1 - self.commission)
        self.capital = self.capital + sale_proceeds

        # Calculate profit/loss
        pnl = sale_proceeds - (self.positions[symbol] * self.entry_prices[symbol])
        pnl_pct = (price - self.entry_prices[symbol]) / self.entry_prices[symbol] * 100

        trade = {
            'symbol': symbol,
            'timestamp': timestamp,
            'type': 'SELL',
            'price': price,
            'size': self.positions[symbol],
            'capital': self.capital,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'commission': self.positions[symbol] * price * self.commission
        }

        self.trades.append(trade)
        self._log_trade(trade)

        # Log to database
        if self.db and self.session_id:
            self.db.log_trade(self.session_id, trade)

        print(f"\n[SELL] {symbol} {timestamp}")
        print(f"Price: ${price:.2f}")
        print(f"Size: {self.positions[symbol]:.6f}")
        print(f"P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"Capital: ${self.capital:.2f}")

        self.positions[symbol] = 0
        self.entry_prices[symbol] = 0

    def update(self, symbol: str, timeframe: str):
        """
        Update with latest market data and execute trades (backward compatibility)

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
        """
        # Use data_handler if available (backward compatibility)
        if self.data_handler:
            df = self.data_handler.fetch_ohlcv(symbol, timeframe, limit=100)
        elif self.broker:
            df = self.broker.fetch_ohlcv(symbol, timeframe, limit=100)
        else:
            print("No data handler or broker configured")
            return

        if df.empty:
            print("No data received")
            return

        # Get current signal
        signal, info = self.strategy.get_current_signal(df)

        current_price = info['close']
        timestamp = info['timestamp']

        # Log signal to database
        if self.db and self.session_id:
            signal_data = {
                'symbol': symbol,
                'timestamp': timestamp,
                'signal': signal,
                'indicator_values': info,
                'market_price': current_price,
                'executed': False  # Will be updated after trade execution
            }
            self.db.log_signal(self.session_id, signal_data)

        # Track equity (single symbol version)
        current_prices = {symbol: current_price}
        portfolio_value = self.get_portfolio_value(current_prices)
        self.equity_history.append({
            'timestamp': timestamp,
            'equity': portfolio_value,
            'price': current_price,
            'position': self.positions[symbol]
        })

        # Take portfolio snapshot
        self._take_portfolio_snapshot(timestamp, portfolio_value, current_prices)

        # Execute trades based on signal
        executed = False
        if signal == 1 and self.last_signals[symbol] != 1:  # New BUY signal
            self.execute_buy(symbol, current_price, timestamp)
            executed = True
        elif signal == -1 and self.last_signals[symbol] != -1:  # New SELL signal
            self.execute_sell(symbol, current_price, timestamp)
            executed = True

        # Update signal executed status if needed
        if executed and self.db and self.session_id:
            # Note: This is simplified - in production, we'd update the specific signal record
            pass

        self.last_signals[symbol] = signal

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
        # Start session
        self.start()

        print(f"\n{'='*60}")
        print(f"PAPER TRADING STARTED")
        print(f"{'='*60}")
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print(f"Strategy: {self.strategy}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Update Interval: {update_interval}s")
        if self.session_id:
            print(f"Session ID: {self.session_id}")
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
        """Stop paper trading and finalize session"""
        self.is_running = False
        self._print_summary()

        # Update database session with final metrics
        if self.db and self.session_id:
            final_value = self.get_portfolio_value()
            if self.equity_history:
                final_value = self.equity_history[-1]['equity']

            total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

            # Calculate performance metrics
            sharpe_ratio = self._calculate_sharpe_ratio()
            max_drawdown = self._calculate_max_drawdown()
            win_rate = self._calculate_win_rate()

            self.db.update_session(self.session_id, {
                'end_time': datetime.now().isoformat(),
                'final_capital': final_value,
                'total_return': total_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'status': 'completed'
            })

            print(f"Session {self.session_id} finalized")

    def _take_portfolio_snapshot(self, timestamp: datetime, total_value: float, current_prices: Optional[Dict[str, float]] = None):
        """
        Take a portfolio snapshot and log to database

        Args:
            timestamp: Snapshot timestamp
            total_value: Total portfolio value
            current_prices: Optional dict of current prices (for debugging)
        """
        if not self.db or not self.session_id:
            return

        snapshot = {
            'timestamp': timestamp,
            'total_value': total_value,
            'cash': self.capital,
            'positions': self.positions.copy()
        }

        self.db.log_portfolio_snapshot(self.session_id, snapshot)

    def _calculate_sharpe_ratio(self) -> Optional[float]:
        """
        Calculate Sharpe ratio from equity history

        Returns:
            Sharpe ratio or None if insufficient data
        """
        if len(self.equity_history) < 2:
            return None

        equity_values = [eq['equity'] for eq in self.equity_history]
        returns = pd.Series(equity_values).pct_change().dropna()

        if len(returns) < 2:
            return None

        mean_return = returns.mean()
        std_return = returns.std()

        if std_return == 0:
            return None

        # Annualized Sharpe ratio (assuming daily data, 252 trading days)
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return float(sharpe)

    def _calculate_max_drawdown(self) -> Optional[float]:
        """
        Calculate maximum drawdown from equity history

        Returns:
            Max drawdown percentage or None if insufficient data
        """
        if not self.equity_history:
            return None

        equity_values = [eq['equity'] for eq in self.equity_history]
        peak = equity_values[0]
        max_dd = 0.0

        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return float(max_dd)

    def _calculate_win_rate(self) -> Optional[float]:
        """
        Calculate win rate from completed trades

        Returns:
            Win rate percentage or None if no trades
        """
        sell_trades = [t for t in self.trades if t['type'] == 'SELL']

        if not sell_trades:
            return None

        winning = [t for t in sell_trades if t.get('pnl', 0) > 0]
        win_rate = len(winning) / len(sell_trades) * 100

        return float(win_rate)

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

        # Show total positions
        total_position = sum(self.positions.values())
        print(f"Position: {total_position:.6f} | Portfolio Value: ${portfolio_value:.2f}")
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
