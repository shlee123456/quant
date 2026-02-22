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
from .retry_utils import retry_with_backoff, CircuitBreaker
from .performance_calculator import PerformanceCalculator
from .order_executor import OrderExecutor
from .risk_manager import RiskManager
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
        display_name: Optional[str] = None,
        regime_detector=None,
        llm_client=None,
        notifier=None
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

        # Risk management parameters (kept for backward compat attribute access)
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

        # Regime detection + LLM integration (optional)
        self.regime_detector = regime_detector
        self.llm_client = llm_client

        # Notifier
        self.notifier = notifier

        # Threading lock for state mutations
        self._lock = threading.RLock()

        # Symbol-level circuit breaker for iteration errors
        self._symbol_error_counts: Dict[str, int] = {}

        # Circuit breakers for API calls
        self._ticker_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)
        self._ohlcv_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)

        # Memory cap for equity history
        self.EQUITY_HISTORY_MAX_SIZE = 5000

        # --- Extracted helper classes ---
        self._performance_calculator = PerformanceCalculator(timeframe='1h')
        self._order_executor = OrderExecutor(
            commission=commission,
            position_size=position_size,
            log_file=log_file,
        )
        self._risk_manager = RiskManager(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
        )

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
            logger.info(f"Created session: {self.session_id}")

    def execute_buy(self, symbol: str, price: float, timestamp: datetime):
        """
        Execute a buy order

        Args:
            symbol: Trading symbol
            price: Buy price
            timestamp: Trade timestamp
        """
        with self._lock:
            if self.positions[symbol] > 0:
                logger.info(f"Already in position for {symbol}, skipping BUY signal")
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

        logger.info(f"[BUY] {symbol} {timestamp}")
        logger.debug(f"Price: ${price:.2f}")
        logger.debug(f"Size: {self.positions[symbol]:.6f}")
        logger.debug(f"Capital remaining: ${self.capital:.2f}")

    def execute_sell(self, symbol: str, price: float, timestamp: datetime, reason: str = 'signal'):
        """
        Execute a sell order

        Args:
            symbol: Trading symbol
            price: Sell price
            timestamp: Trade timestamp
            reason: Reason for sell ('signal', 'stop_loss', 'take_profit')
        """
        with self._lock:
            if self.positions[symbol] == 0:
                logger.info(f"No position to sell for {symbol}, skipping SELL signal")
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

            reason_text = {
                'signal': '전략 시그널',
                'stop_loss': '손절매',
                'take_profit': '익절매'
            }
            reason_kr = reason_text.get(reason, '매도')

            logger.info(f"[매도 - {reason_kr}] {symbol} {timestamp}")
            logger.debug(f"가격: ${price:.2f}")
            logger.debug(f"수량: {self.positions[symbol]:.6f}")
            logger.debug(f"손익: ${pnl:.2f} ({pnl_pct:+.2f}%)")
            logger.debug(f"자본: ${self.capital:.2f}")

            self.positions[symbol] = 0
            self.entry_prices[symbol] = 0

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
            logger.error("No data handler or broker configured")
            return

        if df.empty:
            logger.error("No data received")
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
        with self._lock:
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

        logger.info(f"REAL-TIME PAPER TRADING STARTED | Symbols: {', '.join(self.symbols)} | "
                    f"Timeframe: {timeframe} | Strategy: {self.strategy.name} | "
                    f"Initial Capital: ${self.initial_capital:,.2f} | Interval: {interval_seconds}s")
        if self.session_id:
            logger.info(f"Session ID: {self.session_id}")

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
            logger.info("Paper trading stopped by user")
            self.stop()
        except Exception as e:
            logger.exception(f"Error during paper trading: {e}")
            self.stop()
        finally:
            self._loop_exited.set()

    def _check_stop_loss_take_profit(self, symbol: str, current_price: float, timestamp: datetime) -> bool:
        """
        Check and execute stop loss or take profit if triggered.
        Delegates to RiskManager for the check logic.

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

        action = self._risk_manager.check_symbol(
            symbol=symbol,
            position=self.positions[symbol],
            entry_price=self.entry_prices[symbol],
            current_price=current_price,
        )

        if action is None:
            return False

        # Execute the sell
        self.execute_sell(symbol, current_price, timestamp, reason=action.action)

        # Send notification
        if self.notifier:
            reason_label = '손절매' if action.action == 'stop_loss' else '익절매'
            self.notifier.notify_trade({
                'type': 'SELL',
                'symbol': symbol,
                'price': current_price,
                'size': self.positions.get(symbol, 0),
                'timestamp': timestamp,
                'reason': f'{reason_label} ({action.pnl_pct*100:.2f}%)'
            })

        return True

    def _fetch_ticker_with_retry(self, symbol: str, overseas: bool = False):
        """
        Fetch ticker with retry logic

        Args:
            symbol: Trading symbol
            overseas: Whether to use overseas parameter (for KIS broker)

        Returns:
            Ticker dict with 'last' price
        """
        @self._ticker_circuit_breaker
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
        @self._ohlcv_circuit_breaker
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
                # Skip symbols that have hit the error threshold
                if self._symbol_error_counts.get(symbol, 0) >= 3:
                    continue

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

                    # 손절매/익절매 먼저 체크 (우선순위 높음)
                    if self._check_stop_loss_take_profit(symbol, current_price, timestamp):
                        # 손절/익절 발생 시 전략 시그널 무시하고 다음 종목으로
                        logger.info(f"[{timestamp}] {symbol}: 손절/익절 실행됨, 전략 시그널 무시")
                        continue

                    # Fetch historical OHLCV data for strategy indicator calculation (with retry)
                    df = self._fetch_ohlcv_with_retry(symbol, timeframe, limit=100)

                    if df.empty:
                        logger.warning(f"No OHLCV data for {symbol}, skipping")
                        continue

                    # Get current signal from strategy
                    signal, info = self.strategy.get_current_signal(df)

                    # Validate signal
                    if self.enable_verification:
                        if not self._signal_validator.validate_signal_value(signal):
                            logger.warning(f"유효하지 않은 시그널 값 [{symbol}]: {signal}")

                    # [Regime Detection] 레짐 감지
                    regime_result = None
                    if self.regime_detector:
                        try:
                            regime_result = self.regime_detector.detect(df)
                            if self.db and self.session_id:
                                from dataclasses import asdict
                                regime_dict = asdict(regime_result)
                                regime_dict['symbol'] = symbol
                                regime_dict['timestamp'] = timestamp
                                regime_dict['regime'] = regime_result.regime.value
                                self.db.log_regime(self.session_id, regime_dict)
                        except Exception as e:
                            logger.warning(f"레짐 감지 실패 [{symbol}]: {e}")

                    # [LLM Signal Filter] 시그널 필터링 (signal != 0일 때만)
                    if self.llm_client and signal != 0:
                        try:
                            from dataclasses import asdict
                            regime_info = asdict(regime_result) if regime_result else {}
                            if regime_result:
                                regime_info['regime'] = regime_result.regime.value

                            decision = self.llm_client.filter_signal({
                                'signal': signal,
                                'symbol': symbol,
                                'strategy': self.strategy.name,
                                'indicators': info,
                                'regime': regime_info,
                                'position_info': {
                                    'current_positions': sum(1 for v in self.positions.values() if v > 0),
                                    'capital_pct_used': 1.0 - (self.capital / self.initial_capital) if self.initial_capital > 0 else 0,
                                }
                            })

                            if decision:
                                # DB 기록
                                if self.db and self.session_id:
                                    self.db.log_llm_decision(self.session_id, {
                                        'symbol': symbol,
                                        'timestamp': timestamp,
                                        'decision_type': 'signal_filter',
                                        'request_context': {'signal': signal, 'regime': regime_info},
                                        'response': {'action': decision.action, 'confidence': decision.confidence, 'reasoning': decision.reasoning},
                                        'latency_ms': getattr(decision, '_latency_ms', None),
                                        'model_name': self.llm_client.config.signal_model_name if hasattr(self.llm_client, 'config') else None,
                                    })

                                if decision.action == 'reject':
                                    logger.info(f"LLM 시그널 거부 [{symbol}]: {decision.reasoning}")
                                    signal = 0
                                elif decision.action == 'hold':
                                    logger.info(f"LLM 시그널 보류 [{symbol}]: {decision.reasoning}")
                                    signal = 0
                                # 'execute' → 원래 시그널 유지
                        except Exception as e:
                            logger.warning(f"LLM 시그널 필터 실패 (fail-open) [{symbol}]: {e}")

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

                    # Log status for this symbol
                    logger.info(f"[{timestamp}] {symbol}: 가격=${current_price:.2f}, 시그널={signal}")

                    # Reset error count on success
                    self._symbol_error_counts[symbol] = 0

                except Exception as e:
                    self._symbol_error_counts[symbol] = self._symbol_error_counts.get(symbol, 0) + 1
                    if self._symbol_error_counts[symbol] >= 3:
                        logger.error(f"Symbol {symbol} reached error threshold ({self._symbol_error_counts[symbol]}), skipping in future iterations: {e}")
                    else:
                        logger.error(f"Failed to process {symbol} (error count: {self._symbol_error_counts[symbol]}): {e}")
                    continue

            # Take portfolio snapshot after all symbols processed
            portfolio_value = self.get_portfolio_value(current_prices)
            timestamp = datetime.now()

            with self._lock:
                self.equity_history.append({
                    'timestamp': timestamp,
                    'equity': portfolio_value,
                    'prices': current_prices.copy(),
                    'positions': self.positions.copy()
                })

                if len(self.equity_history) > self.EQUITY_HISTORY_MAX_SIZE:
                    self.equity_history = self.equity_history[-self.EQUITY_HISTORY_MAX_SIZE:]

            self._take_portfolio_snapshot(timestamp, portfolio_value, current_prices)

            # Log portfolio summary
            logger.info(f"Portfolio Value: ${portfolio_value:.2f} | Return: {((portfolio_value - self.initial_capital) / self.initial_capital * 100):+.2f}%")

        except Exception as e:
            logger.exception(f"Iteration failed: {e}")

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

        logger.info(f"PAPER TRADING STARTED | Symbol: {symbol} | Timeframe: {timeframe} | "
                    f"Strategy: {self.strategy} | Initial Capital: ${self.initial_capital:,.2f} | "
                    f"Interval: {update_interval}s")
        if self.session_id:
            logger.info(f"Session ID: {self.session_id}")

        self.is_running = True

        try:
            while self.is_running:
                self.update(symbol, timeframe)
                time.sleep(update_interval)

        except KeyboardInterrupt:
            logger.info("Paper trading stopped by user")
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

        # Update database session with final metrics (delegates to PerformanceCalculator)
        if self.db and self.session_id:
            final_value = self.get_portfolio_value()
            if self.equity_history:
                final_value = self.equity_history[-1]['equity']

            total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

            # Calculate performance metrics via PerformanceCalculator
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

            logger.info(f"Session {self.session_id} finalized")

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
        Calculate Sharpe ratio from equity history.
        Delegates to PerformanceCalculator.
        """
        return self._performance_calculator.calculate_sharpe_ratio(self.equity_history)

    def _calculate_max_drawdown(self) -> Optional[float]:
        """
        Calculate maximum drawdown from equity history.
        Delegates to PerformanceCalculator.
        """
        return self._performance_calculator.calculate_max_drawdown(self.equity_history)

    def _calculate_win_rate(self) -> Optional[float]:
        """
        Calculate win rate from completed trades.
        Delegates to PerformanceCalculator.
        """
        return self._performance_calculator.calculate_win_rate(self.trades)

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get a complete performance summary.
        Delegates to PerformanceCalculator.

        Returns:
            Dict with all performance metrics.
        """
        return self._performance_calculator.get_performance_summary(
            trades=self.trades,
            equity_history=self.equity_history,
            initial_capital=self.initial_capital,
        )

    def _print_status(self, info: Dict, portfolio_value: float):
        """Log current status"""
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

        total_position = sum(self.positions.values())
        logger.info(f"[{info['timestamp']}] {' | '.join(indicator_parts)} | "
                     f"Position: {total_position:.6f} | Portfolio: ${portfolio_value:.2f} | "
                     f"Return: {((portfolio_value - self.initial_capital) / self.initial_capital * 100):+.2f}%")

    def _print_summary(self):
        """Log trading summary"""
        if not self.equity_history:
            logger.info("No trading history")
            return

        final_value = self.equity_history[-1]['equity']
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        sell_trades = [t for t in self.trades if t['type'] == 'SELL']

        summary_parts = [
            "PAPER TRADING SUMMARY",
            f"Initial Capital: ${self.initial_capital:,.2f}",
            f"Final Value: ${final_value:,.2f}",
            f"Total Return: {total_return:+.2f}%",
            f"Total Trades: {len(sell_trades)}"
        ]

        if sell_trades:
            winning = [t for t in sell_trades if t['pnl'] > 0]
            summary_parts.append(f"Winning Trades: {len(winning)}")
            summary_parts.append(f"Win Rate: {len(winning)/len(sell_trades)*100:.2f}%")

        logger.info(" | ".join(summary_parts))

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
            logger.error(f"Error logging trade: {e}")

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        return pd.DataFrame(self.trades)

    def get_equity_df(self) -> pd.DataFrame:
        """Get equity history as DataFrame"""
        return pd.DataFrame(self.equity_history)
