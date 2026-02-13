"""
Paper trading simulator for live trading without real money
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from .strategies.base_strategy import BaseStrategy
from .data_handler import DataHandler
from .brokers.base_broker import BaseBroker
from .database import TradingDatabase
from .signal_validator import SignalValidator
from .execution_verifier import OrderExecutionVerifier
from .retry_utils import retry_with_backoff
import time
import json
import threading
import numpy as np
import logging


logger = logging.getLogger(__name__)


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
        strategy: BaseStrategy,
        symbols: Union[str, List[str]],
        data_handler: Optional[DataHandler] = None,
        broker: Optional[BaseBroker] = None,
        initial_capital: float = 10000.0,
        position_size: float = 0.95,
        commission: float = 0.001,
        log_file: Optional[str] = None,
        db: Optional[TradingDatabase] = None,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True,
        enable_verification: bool = False,
        display_name: Optional[str] = None
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
            stop_loss_pct: Stop loss percentage (default: 0.05 = 5%)
            take_profit_pct: Take profit percentage (default: 0.10 = 10%)
            enable_stop_loss: Enable stop loss feature (default: True)
            enable_take_profit: Enable take profit feature (default: True)
            enable_verification: Enable signal/execution verification (default: False)
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

        # Risk management
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.enable_stop_loss = enable_stop_loss
        self.enable_take_profit = enable_take_profit

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

        # Thread synchronization for graceful shutdown
        self._stop_event = threading.Event()
        self._loop_exited = threading.Event()
        self._stopped = False

        # Session tracking
        self.session_id: Optional[str] = None
        self.display_name: Optional[str] = display_name

        # Verification
        self.enable_verification = enable_verification
        self._signal_validator = SignalValidator()
        self._execution_verifier = OrderExecutionVerifier()

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
        Sets is_running flag to True
        """
        self.is_running = True

        if self.db and not self.session_id:
            if not self.display_name:
                from trading_bot.database import generate_display_name
                self.display_name = generate_display_name(self.strategy.name, self.symbols)
            self.session_id = self.db.create_session(
                strategy_name=self.strategy.name,
                initial_capital=self.initial_capital,
                display_name=self.display_name
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

        prev_position = self.positions[symbol]
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

        # Verify execution
        if self.enable_verification:
            is_valid, msg = self._execution_verifier.verify_execution(
                expected_signal=1, executed_trade=trade, current_position=prev_position
            )
            if not is_valid:
                logger.warning(f"실행 검증 실패 [{symbol}]: {msg}")

        # Log to database
        if self.db and self.session_id:
            self.db.log_trade(self.session_id, trade)

        print(f"\n[BUY] {symbol} {timestamp}")
        print(f"Price: ${price:.2f}")
        print(f"Size: {self.positions[symbol]:.6f}")
        print(f"Capital remaining: ${self.capital:.2f}")

    def execute_sell(self, symbol: str, price: float, timestamp: datetime, reason: str = 'signal'):
        """
        Execute a sell order

        Args:
            symbol: Trading symbol
            price: Sell price
            timestamp: Trade timestamp
            reason: Reason for sell ('signal', 'stop_loss', 'take_profit')
        """
        if self.positions[symbol] == 0:
            print(f"No position to sell for {symbol}, skipping SELL signal")
            return

        prev_position = self.positions[symbol]
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
            'commission': self.positions[symbol] * price * self.commission,
            'reason': reason
        }

        self.trades.append(trade)
        self._log_trade(trade)

        # Verify execution
        if self.enable_verification:
            is_valid, msg = self._execution_verifier.verify_execution(
                expected_signal=-1, executed_trade=trade, current_position=prev_position
            )
            if not is_valid:
                logger.warning(f"실행 검증 실패 [{symbol}]: {msg}")

        # Log to database
        if self.db and self.session_id:
            self.db.log_trade(self.session_id, trade)

        # Print with emoji based on reason
        reason_emoji = {
            'signal': '📊',
            'stop_loss': '🛑',
            'take_profit': '💰'
        }
        emoji = reason_emoji.get(reason, '📊')

        reason_text = {
            'signal': '전략 시그널',
            'stop_loss': '손절매',
            'take_profit': '익절매'
        }
        reason_kr = reason_text.get(reason, '매도')

        print(f"\n{emoji} [매도 - {reason_kr}] {symbol} {timestamp}")
        print(f"가격: ${price:.2f}")
        print(f"수량: {self.positions[symbol]:.6f}")
        print(f"손익: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"자본: ${self.capital:.2f}")

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

    def run_realtime(self, interval_seconds: int = 60, timeframe: str = '1d'):
        """
        Run paper trading in real-time with live data fetching

        Args:
            interval_seconds: Seconds between iterations (default: 60)
            timeframe: OHLCV timeframe for indicator calculation (default: '1d')
        """
        if not self.broker:
            raise ValueError("Broker is required for real-time trading. Please provide broker parameter.")

        # Start session
        self.start()

        print(f"\n{'='*60}")
        print(f"REAL-TIME PAPER TRADING STARTED")
        print(f"{'='*60}")
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Timeframe: {timeframe}")
        print(f"Strategy: {self.strategy.name}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Update Interval: {interval_seconds}s")
        if self.session_id:
            print(f"Session ID: {self.session_id}")
        print(f"{'='*60}\n")

        self.is_running = True
        self._stop_event.clear()
        self._loop_exited.clear()
        self._stopped = False

        try:
            while self.is_running:
                self._realtime_iteration(timeframe)
                # Use event wait instead of sleep for responsive shutdown
                if self._stop_event.wait(timeout=interval_seconds):
                    break

        except KeyboardInterrupt:
            print("\n\nPaper trading stopped by user")
            self.stop()
        except Exception as e:
            print(f"\n\nError during paper trading: {e}")
            import traceback
            traceback.print_exc()
            self.stop()
        finally:
            self._loop_exited.set()

    def _check_stop_loss_take_profit(self, symbol: str, current_price: float, timestamp: datetime) -> bool:
        """
        Check and execute stop loss or take profit if triggered

        Args:
            symbol: Trading symbol
            current_price: Current market price
            timestamp: Current timestamp

        Returns:
            True if stop loss or take profit was triggered, False otherwise
        """
        # Skip if no position
        if self.positions[symbol] == 0:
            return False

        entry_price = self.entry_prices[symbol]
        pnl_pct = (current_price - entry_price) / entry_price

        # Check stop loss
        if self.enable_stop_loss and pnl_pct <= -self.stop_loss_pct:
            print(f"\n🛑 손절매 발동! {symbol}: {pnl_pct*100:.2f}% (기준: -{self.stop_loss_pct*100:.0f}%)")
            self.execute_sell(symbol, current_price, timestamp, reason='stop_loss')

            # Send notification
            if hasattr(self, 'notifier') and self.notifier:
                self.notifier.notify_trade({
                    'type': 'SELL',
                    'symbol': symbol,
                    'price': current_price,
                    'size': self.positions.get(symbol, 0),
                    'timestamp': timestamp,
                    'reason': f'손절매 ({pnl_pct*100:.2f}%)'
                })

            return True

        # Check take profit
        if self.enable_take_profit and pnl_pct >= self.take_profit_pct:
            print(f"\n💰 익절매 발동! {symbol}: {pnl_pct*100:.2f}% (기준: +{self.take_profit_pct*100:.0f}%)")
            self.execute_sell(symbol, current_price, timestamp, reason='take_profit')

            # Send notification
            if hasattr(self, 'notifier') and self.notifier:
                self.notifier.notify_trade({
                    'type': 'SELL',
                    'symbol': symbol,
                    'price': current_price,
                    'size': self.positions.get(symbol, 0),
                    'timestamp': timestamp,
                    'reason': f'익절매 ({pnl_pct*100:.2f}%)'
                })

            return True

        return False

    def _fetch_ticker_with_retry(self, symbol: str, overseas: bool = False):
        """
        Fetch ticker with retry logic

        Args:
            symbol: Trading symbol
            overseas: Whether to use overseas parameter (for KIS broker)

        Returns:
            Ticker dict with 'last' price
        """
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch():
            if overseas:
                return self.broker.fetch_ticker(symbol, overseas=True)
            else:
                return self.broker.fetch_ticker(symbol)

        return _fetch()

    def _fetch_ohlcv_with_retry(self, symbol: str, timeframe: str, limit: int = 100):
        """
        Fetch OHLCV with retry logic

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '1d', '1h')
            limit: Number of bars to fetch

        Returns:
            DataFrame with OHLCV data
        """
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch():
            # Check if broker supports overseas parameter (KIS broker)
            from .brokers.korea_investment_broker import KoreaInvestmentBroker
            if isinstance(self.broker, KoreaInvestmentBroker):
                return self.broker.fetch_ohlcv(symbol, timeframe, limit=limit, overseas=True)
            else:
                return self.broker.fetch_ohlcv(symbol, timeframe, limit=limit)

        return _fetch()

    def _realtime_iteration(self, timeframe: str):
        """
        Execute one iteration of real-time paper trading

        Args:
            timeframe: OHLCV timeframe for indicator calculation
        """
        if not self.broker:
            raise ValueError("Broker is required for real-time trading")

        try:
            # Collect current prices for all symbols
            current_prices: Dict[str, float] = {}

            # Process each symbol
            for symbol in self.symbols:
                try:
                    # Fetch current ticker (with retry)
                    # Check if broker supports overseas parameter (KoreaInvestmentBroker)
                    from .brokers.korea_investment_broker import KoreaInvestmentBroker
                    if isinstance(self.broker, KoreaInvestmentBroker):
                        ticker = self._fetch_ticker_with_retry(symbol, overseas=True)
                    else:
                        ticker = self._fetch_ticker_with_retry(symbol)

                    current_price = ticker['last']
                    current_prices[symbol] = current_price

                    timestamp = datetime.now()

                    # ⭐ 손절매/익절매 먼저 체크 (우선순위 높음)
                    if self._check_stop_loss_take_profit(symbol, current_price, timestamp):
                        # 손절/익절 발생 시 전략 시그널 무시하고 다음 종목으로
                        print(f"[{timestamp}] {symbol}: 손절/익절 실행됨, 전략 시그널 무시")
                        continue

                    # Fetch historical OHLCV data for strategy indicator calculation (with retry)
                    df = self._fetch_ohlcv_with_retry(symbol, timeframe, limit=100)

                    if df.empty:
                        print(f"[WARNING] No OHLCV data for {symbol}, skipping")
                        continue

                    # Get current signal from strategy
                    signal, info = self.strategy.get_current_signal(df)

                    # Validate signal
                    if self.enable_verification:
                        if not self._signal_validator.validate_signal_value(signal):
                            logger.warning(f"유효하지 않은 시그널 값 [{symbol}]: {signal}")

                    # Log signal to database
                    if self.db and self.session_id:
                        signal_data = {
                            'symbol': symbol,
                            'timestamp': timestamp,
                            'signal': signal,
                            'indicator_values': info,
                            'market_price': current_price,
                            'executed': False
                        }
                        self.db.log_signal(self.session_id, signal_data)

                    # Execute trades based on signals
                    executed = False
                    if signal == 1 and self.last_signals.get(symbol, 0) != 1:  # New BUY signal
                        self.execute_buy(symbol, current_price, timestamp)
                        executed = True
                    elif signal == -1 and self.last_signals.get(symbol, 0) != -1:  # New SELL signal
                        self.execute_sell(symbol, current_price, timestamp, reason='signal')
                        executed = True

                    # Update last signal
                    self.last_signals[symbol] = signal

                    # Print status for this symbol
                    status_emoji = '📊' if signal == 0 else ('🟢' if signal == 1 else '🔴')
                    print(f"[{timestamp}] {status_emoji} {symbol}: 가격=${current_price:.2f}, 시그널={signal}")

                except Exception as e:
                    print(f"[ERROR] Failed to process {symbol}: {e}")
                    continue

            # Take portfolio snapshot after all symbols processed
            portfolio_value = self.get_portfolio_value(current_prices)
            timestamp = datetime.now()

            self.equity_history.append({
                'timestamp': timestamp,
                'equity': portfolio_value,
                'prices': current_prices.copy(),
                'positions': self.positions.copy()
            })

            self._take_portfolio_snapshot(timestamp, portfolio_value, current_prices)

            # Print portfolio summary
            print(f"\n--- Portfolio Value: ${portfolio_value:.2f} | Return: {((portfolio_value - self.initial_capital) / self.initial_capital * 100):+.2f}% ---\n")

        except Exception as e:
            print(f"[ERROR] Iteration failed: {e}")
            import traceback
            traceback.print_exc()

    def run(self, symbol: str, timeframe: str, update_interval: int = 60):
        """
        Run paper trading in a loop (backward compatibility)

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
        if self._stopped:
            return
        self._stopped = True
        self.is_running = False
        self._stop_event.set()
        self._print_summary()

        # Generate verification report
        if self.enable_verification:
            # Verify capital consistency
            is_consistent, msg = self._execution_verifier.verify_capital_consistency(
                initial_capital=self.initial_capital,
                trades=self.trades,
                current_capital=self.capital,
            )
            if not is_consistent:
                logger.warning(f"자본금 정합성 검증 실패: {msg}")

            # Verify position consistency
            inconsistencies = self._execution_verifier.verify_position_consistency(
                positions=self.positions,
                trades=self.trades,
            )
            for inc in inconsistencies:
                logger.warning(f"포지션 불일치: {inc}")

            report = self._execution_verifier.generate_verification_report()
            logger.info(
                f"검증 리포트: 총 {report['total_checks']}건 "
                f"(통과={report['passed']}, 경고={report['warnings']}, 오류={report['errors']})"
            )

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
