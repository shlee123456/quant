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
from .execution_verifier import OrderExecutionVerifier
from .retry_utils import retry_with_backoff, CircuitBreaker
from .performance_calculator import PerformanceCalculator
from .order_executor import OrderExecutor
from .risk_manager import RiskManager
from .portfolio_manager import PortfolioManager
from .signal_pipeline import SignalPipeline
from .limit_order import LimitOrderManager
import time
import json
import threading
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
        notifier=None,
        limit_orders: Optional[List[Dict]] = None,
        sentiment_sizing: bool = False,
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
        self._execution_verifier = OrderExecutionVerifier()

        # Regime detection + LLM integration (optional) -- kept for attribute access
        self.regime_detector = regime_detector
        self.llm_client = llm_client

        # Notifier
        self.notifier = notifier

        # Threading lock for state mutations (shared with portfolio manager)
        self._lock = threading.RLock()

        # Symbol-level circuit breaker for iteration errors
        self._symbol_error_counts: Dict[str, int] = {}

        # Circuit breakers for API calls
        self._ticker_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)
        self._ohlcv_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=120.0)

        # Memory cap for equity history
        from trading_bot.config import Config
        _cfg = Config()
        self.EQUITY_HISTORY_MAX_SIZE = _cfg.get('paper_trading.equity_history_max_size', 5000)

        # --- Extracted helper classes ---
        self._portfolio = PortfolioManager(
            symbols=self.symbols,
            initial_capital=initial_capital,
            db=db,
            max_equity_history=self.EQUITY_HISTORY_MAX_SIZE,
        )
        # Share the same lock
        self._portfolio._lock = self._lock

        self._signal_pipeline = SignalPipeline(
            regime_detector=regime_detector,
            llm_client=llm_client,
            enable_verification=enable_verification,
        )

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

        # Sentiment-based position sizing
        self._sentiment_sizing = sentiment_sizing
        self._intelligence_report: Optional[Dict] = None

        # Limit order manager
        self._limit_order_manager = LimitOrderManager(db=db, lock=self._lock) if db else None
        self._initial_limit_orders = limit_orders or []

    # ---- Backward-compatible property accessors delegating to PortfolioManager ----

    @property
    def capital(self) -> float:
        return self._portfolio.capital

    @capital.setter
    def capital(self, value: float):
        self._portfolio.capital = value

    @property
    def positions(self) -> Dict[str, float]:
        return self._portfolio.positions

    @positions.setter
    def positions(self, value: Dict[str, float]):
        self._portfolio.positions = value

    @property
    def entry_prices(self) -> Dict[str, float]:
        return self._portfolio.entry_prices

    @entry_prices.setter
    def entry_prices(self, value: Dict[str, float]):
        self._portfolio.entry_prices = value

    @property
    def last_signals(self) -> Dict[str, int]:
        return self._portfolio.last_signals

    @last_signals.setter
    def last_signals(self, value: Dict[str, int]):
        self._portfolio.last_signals = value

    @property
    def trades(self) -> List[Dict[str, Any]]:
        return self._portfolio.trades

    @trades.setter
    def trades(self, value: List[Dict[str, Any]]):
        self._portfolio.trades = value

    @property
    def equity_history(self) -> List[Dict[str, Any]]:
        return self._portfolio.equity_history

    @equity_history.setter
    def equity_history(self, value: List[Dict[str, Any]]):
        self._portfolio.equity_history = value

    @property
    def limit_order_manager(self) -> Optional[LimitOrderManager]:
        """Access the limit order manager (None if no DB configured)"""
        return self._limit_order_manager

    # ---- Public API ----

    def update_intelligence_report(self, report: Dict, fear_greed_value: Optional[float] = None):
        """외부에서 5-Layer 인텔리전스 리포트 주입 (스케줄러에서 호출).

        Args:
            report: MarketIntelligence.analyze() 반환값
            fear_greed_value: Fear & Greed 지수 값 (0-100)
        """
        self._intelligence_report = report
        self._fear_greed_value = fear_greed_value

    def get_portfolio_value(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate current portfolio value

        Args:
            current_prices: Dict mapping symbol to current price.
                           If None, only returns cash value.

        Returns:
            Total portfolio value (cash + positions)
        """
        return self._portfolio.get_portfolio_value(current_prices)

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

        # Register initial limit orders from preset
        if self._limit_order_manager and self._initial_limit_orders and self.session_id:
            for lo in self._initial_limit_orders:
                self._limit_order_manager.create_limit_order(
                    session_id=self.session_id,
                    symbol=lo['symbol'],
                    side=lo['side'],
                    limit_price=lo['price'],
                    amount=lo.get('amount', self.initial_capital * self.position_size),
                    trigger_order=lo.get('trigger_order'),
                    source='preset',
                )

    def execute_buy(self, symbol: str, price: float, timestamp: datetime, amount: float = None):
        """
        Execute a buy order

        Args:
            symbol: Trading symbol
            price: Buy price
            timestamp: Trade timestamp
            amount: 투자 금액 (None이면 capital * position_size 사용)
        """
        with self._lock:
            if self.positions[symbol] > 0:
                logger.info(f"Already in position for {symbol}, skipping BUY signal")
                return

            prev_position = self.positions[symbol]
            base_capital = min(amount, self.capital) if amount else self.capital * self.position_size

            # Sentiment-based position sizing
            sentiment_multiplier = 1.0
            if self._sentiment_sizing and self._intelligence_report:
                try:
                    from trading_bot.market_intelligence import MarketIntelligence
                    fg_val = getattr(self, '_fear_greed_value', None)
                    rec = MarketIntelligence.get_position_size_recommendation(
                        self._intelligence_report, fear_greed_value=fg_val
                    )
                    sentiment_multiplier = rec.get('multiplier', 1.0)
                    logger.info(
                        f"[Sentiment Sizing] {symbol}: {sentiment_multiplier:.2f}x - {rec.get('reason', '')}"
                    )
                except Exception as e:
                    logger.debug(f"Sentiment sizing 실패 (1.0x 유지): {e}")

            trade_capital = min(base_capital * sentiment_multiplier, self.capital)
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

            self._portfolio.record_trade(trade)

            self._log_trade(trade)

            # Log to database
            if self.db and self.session_id:
                self.db.log_trade(self.session_id, trade)

        # Verify execution (read-only, outside lock)
        if self.enable_verification:
            is_valid, msg = self._execution_verifier.verify_execution(
                expected_signal=1, executed_trade=trade, current_position=prev_position
            )
            if not is_valid:
                logger.warning(f"실행 검증 실패 [{symbol}]: {msg}")

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

            self._portfolio.record_trade(trade)

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

            # Log to database
            if self.db and self.session_id:
                self.db.log_trade(self.session_id, trade)

        # Verify execution (read-only, outside lock)
        if self.enable_verification:
            is_valid, msg = self._execution_verifier.verify_execution(
                expected_signal=-1, executed_trade=trade, current_position=prev_position
            )
            if not is_valid:
                logger.warning(f"실행 검증 실패 [{symbol}]: {msg}")

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
                'executed': False
            }
            self.db.log_signal(self.session_id, signal_data)

        # Track equity (single symbol version)
        current_prices = {symbol: current_price}
        portfolio_value = self.get_portfolio_value(current_prices)
        self._portfolio.record_equity({
            'timestamp': timestamp,
            'equity': portfolio_value,
            'price': current_price,
            'position': self.positions[symbol]
        })

        # Take portfolio snapshot
        self._take_portfolio_snapshot(timestamp, portfolio_value, current_prices)

        # Execute trades based on signal
        executed = False
        if signal == 1 and self.last_signals[symbol] != 1:
            self.execute_buy(symbol, current_price, timestamp)
            executed = True
        elif signal == -1 and self.last_signals[symbol] != -1:
            self.execute_sell(symbol, current_price, timestamp)
            executed = True

        if executed and self.db and self.session_id:
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

        Holds RLock across position check + sell execution to prevent race
        condition where another thread sells the position between the check
        and execute_sell. RLock allows re-entrant acquisition in execute_sell.
        """
        with self._lock:
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

            # Capture size before sell zeroes the position
            sell_size = self.positions[symbol]
            pnl_pct = action.pnl_pct

            # Execute the sell while still holding the lock (RLock is reentrant)
            self.execute_sell(symbol, current_price, timestamp, reason=action.action)

        # Send notification (outside lock -- no shared state mutation)
        if self.notifier:
            reason_label = '손절매' if action.action == 'stop_loss' else '익절매'
            self.notifier.notify_trade({
                'type': 'SELL',
                'symbol': symbol,
                'price': current_price,
                'size': sell_size,
                'timestamp': timestamp,
                'reason': f'{reason_label} ({pnl_pct*100:.2f}%)'
            })

        return True

    def _fetch_ticker_with_retry(self, symbol: str, overseas: bool = False):
        """Fetch ticker with retry logic"""
        @self._ticker_circuit_breaker
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch():
            if overseas:
                return self.broker.fetch_ticker(symbol, overseas=True)
            else:
                return self.broker.fetch_ticker(symbol)

        return _fetch()

    def _fetch_ohlcv_with_retry(self, symbol: str, timeframe: str, limit: int = 100):
        """Fetch OHLCV with retry logic"""
        @self._ohlcv_circuit_breaker
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch():
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
            current_prices: Dict[str, float] = {}

            for symbol in self.symbols:
                if self._symbol_error_counts.get(symbol, 0) >= 3:
                    continue

                try:
                    # Fetch current ticker (with retry)
                    from .brokers.korea_investment_broker import KoreaInvestmentBroker
                    if isinstance(self.broker, KoreaInvestmentBroker):
                        ticker = self._fetch_ticker_with_retry(symbol, overseas=True)
                    else:
                        ticker = self._fetch_ticker_with_retry(symbol)

                    current_price = ticker['last']
                    current_prices[symbol] = current_price

                    timestamp = datetime.now()

                    # Stop loss / take profit check (highest priority)
                    if self._check_stop_loss_take_profit(symbol, current_price, timestamp):
                        logger.info(f"[{timestamp}] {symbol}: 손절/익절 실행됨, 전략 시그널 무시")
                        continue

                    # Limit order fill check (second priority)
                    if self._limit_order_manager:
                        filled = self._limit_order_manager.check_and_fill_paper(
                            symbol=symbol,
                            ticker=ticker,
                            timestamp=timestamp,
                            execute_buy_fn=self.execute_buy,
                            execute_sell_fn=self.execute_sell,
                        )
                        if filled:
                            for order in filled:
                                logger.info(f"[지정가 체결] {order.side.upper()} {symbol} @ ${order.fill_price:.2f}")
                            continue

                    # Fetch historical OHLCV data for strategy indicator calculation
                    df = self._fetch_ohlcv_with_retry(symbol, timeframe, limit=100)

                    if df.empty:
                        logger.warning(f"No OHLCV data for {symbol}, skipping")
                        continue

                    # Get current signal from strategy
                    signal, info = self.strategy.get_current_signal(df)

                    # Process signal through pipeline (validation, regime, LLM)
                    signal, _regime_result = self._signal_pipeline.process(
                        signal=signal,
                        symbol=symbol,
                        df=df,
                        info=info,
                        timestamp=timestamp,
                        positions=self.positions,
                        capital=self.capital,
                        initial_capital=self.initial_capital,
                        strategy_name=self.strategy.name,
                        db=self.db,
                        session_id=self.session_id,
                    )

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
                    if signal == 1 and self.last_signals.get(symbol, 0) != 1:
                        self.execute_buy(symbol, current_price, timestamp)
                    elif signal == -1 and self.last_signals.get(symbol, 0) != -1:
                        self.execute_sell(symbol, current_price, timestamp, reason='signal')

                    self.last_signals[symbol] = signal

                    logger.info(f"[{timestamp}] {symbol}: 가격=${current_price:.2f}, 시그널={signal}")

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

            self._portfolio.record_equity({
                'timestamp': timestamp,
                'equity': portfolio_value,
                'prices': current_prices.copy(),
                'positions': self.positions.copy()
            })

            self._take_portfolio_snapshot(timestamp, portfolio_value, current_prices)

            logger.info(f"Portfolio Value: ${portfolio_value:.2f} | Return: {((portfolio_value - self.initial_capital) / self.initial_capital * 100):+.2f}%")

        except Exception as e:
            logger.exception(f"Iteration failed: {e}")

    def run(self, symbol: str, timeframe: str, update_interval: int = 60):
        """
        Run paper trading in a loop (backward compatibility)
        """
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

        # Cancel all pending limit orders
        if self._limit_order_manager and self.session_id:
            self._limit_order_manager.cancel_all(self.session_id)

        self._print_summary()

        # Generate verification report
        if self.enable_verification:
            is_consistent, msg = self._execution_verifier.verify_capital_consistency(
                initial_capital=self.initial_capital,
                trades=self.trades,
                current_capital=self.capital,
            )
            if not is_consistent:
                logger.warning(f"자본금 정합성 검증 실패: {msg}")

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
        """Take a portfolio snapshot and log to database"""
        self._portfolio.take_snapshot(self.session_id, timestamp, total_value, current_prices)

    def _calculate_sharpe_ratio(self) -> Optional[float]:
        """Calculate Sharpe ratio from equity history."""
        return self._performance_calculator.calculate_sharpe_ratio(self.equity_history)

    def _calculate_max_drawdown(self) -> Optional[float]:
        """Calculate maximum drawdown from equity history."""
        return self._performance_calculator.calculate_max_drawdown(self.equity_history)

    def _calculate_win_rate(self) -> Optional[float]:
        """Calculate win rate from completed trades."""
        return self._performance_calculator.calculate_win_rate(self.trades)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a complete performance summary."""
        return self._performance_calculator.get_performance_summary(
            trades=self.trades,
            equity_history=self.equity_history,
            initial_capital=self.initial_capital,
        )

    def _print_status(self, info: Dict, portfolio_value: float):
        """Log current status"""
        indicator_parts = [f"Price: ${info['close']:.2f}"]

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
                trade_copy = trade.copy()
                trade_copy['timestamp'] = str(trade_copy['timestamp'])
                f.write(json.dumps(trade_copy) + '\n')
        except Exception as e:
            logger.error(f"Error logging trade: {e}")

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        return self._portfolio.get_trades_df()

    def get_equity_df(self) -> pd.DataFrame:
        """Get equity history as DataFrame"""
        return self._portfolio.get_equity_df()
