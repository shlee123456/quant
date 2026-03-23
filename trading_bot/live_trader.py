"""
LiveTrader module for real order execution.

Mirrors PaperTrader's signal loop but executes real orders through the broker
via LiveOrderManager with SafetyGuard protection.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .brokers.base_broker import BaseBroker
from .database import TradingDatabase
from .live_order_manager import LiveOrderManager
from .performance_calculator import PerformanceCalculator
from .portfolio_manager import PortfolioManager
from .retry_utils import CircuitBreaker, retry_with_backoff
from .risk_manager import RiskManager
from .safety_guard import SafetyGuard
from .signal_pipeline import SignalPipeline
from .strategies.base_strategy import BaseStrategy


logger = logging.getLogger(__name__)


class LiveTrader:
    """
    Live trader that executes real orders through the broker.

    Mirrors PaperTrader's signal loop but submits orders via LiveOrderManager
    with SafetyGuard protection (kill switch, daily limits).

    Args:
        strategy: Trading strategy instance.
        symbols: Trading symbol(s).
        broker: Broker instance (REQUIRED).
        initial_capital: Starting capital.
        position_size: Fraction of capital to use per trade.
        commission: Trading commission/fee rate.
        stop_loss_pct: Stop loss percentage.
        take_profit_pct: Take profit percentage.
        enable_stop_loss: Enable stop loss.
        enable_take_profit: Enable take profit.
        display_name: Session display name.
        regime_detector: Optional RegimeDetector instance.
        llm_client: Optional LLMClient instance.
        notifier: Optional NotificationService instance.
        db: Optional TradingDatabase instance.
        mode: Execution mode ('dry_run' or 'live').
        max_daily_loss_pct: Maximum daily loss as fraction of capital.
        max_daily_trades: Maximum trades per day.
        max_position_count: Maximum simultaneous positions.
        order_type: Default order type ('market' or 'limit').
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        symbols: Union[str, List[str]],
        broker: BaseBroker,
        initial_capital: float = 10000.0,
        position_size: float = 0.95,
        commission: float = 0.001,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True,
        display_name: Optional[str] = None,
        regime_detector=None,
        llm_client=None,
        notifier=None,
        db: Optional[TradingDatabase] = None,
        mode: str = 'dry_run',
        max_daily_loss_pct: float = 0.05,
        max_daily_trades: int = 50,
        max_position_count: int = 10,
        order_type: str = 'market',
        adaptive_manager=None,
    ):
        self.strategy = strategy

        # Normalize symbols to list
        if isinstance(symbols, str):
            self.symbols = [symbols]
        else:
            self.symbols = list(symbols)

        self.broker = broker
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission = commission
        self.display_name = display_name
        self.db = db
        self.notifier = notifier

        # Live-specific
        self._mode = mode
        self._order_type = order_type

        # Session tracking
        self.session_id: Optional[str] = None
        self.is_running = False

        # Thread synchronization (same pattern as PaperTrader)
        self._stop_event = threading.Event()
        self._loop_exited = threading.Event()
        self._stopped = False

        # Adaptive strategy manager (optional)
        self._adaptive_manager = adaptive_manager

        # Lock for strategy swaps
        self._lock = threading.RLock()

        # Symbol-level error counts
        self._symbol_error_counts: Dict[str, int] = {}

        # Circuit breakers for API calls
        self._ticker_cb = CircuitBreaker(failure_threshold=5, timeout=120)
        self._ohlcv_cb = CircuitBreaker(failure_threshold=5, timeout=120)

        # --- Internal components ---
        self._safety_guard = SafetyGuard(
            initial_capital=initial_capital,
            max_daily_loss_pct=max_daily_loss_pct,
            max_daily_trades=max_daily_trades,
            max_position_count=max_position_count,
            db=db,
            notifier=notifier,
        )

        self._order_manager = LiveOrderManager(
            broker=broker,
            safety_guard=self._safety_guard,
            db=db,
            notifier=notifier,
        )

        self._portfolio = PortfolioManager(
            symbols=self.symbols,
            initial_capital=initial_capital,
        )

        self._signal_pipeline = SignalPipeline(
            regime_detector=regime_detector,
            llm_client=llm_client,
        )

        self._risk_manager = RiskManager(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            enable_stop_loss=enable_stop_loss,
            enable_take_profit=enable_take_profit,
        )

        self._perf_calc = PerformanceCalculator()

    def start(self):
        """Start a new live trading session."""
        self.is_running = True
        self._stop_event.clear()
        self._loop_exited.clear()
        self._stopped = False

        strategy_name_clean = self.strategy.name.replace(' ', '_')
        self.session_id = f'live_{strategy_name_clean}_{int(time.time())}'

        # Set session_id on order manager
        self._order_manager.session_id = self.session_id

        if self.db:
            self.db.create_live_session(
                session_id=self.session_id,
                strategy_name=self.strategy.name,
                display_name=self.display_name,
                mode=self._mode,
                initial_capital=self.initial_capital,
                broker_name=getattr(self.broker, 'name', None),
                market_type=getattr(self.broker, 'market_type', None),
            )

        if self.notifier:
            self.notifier.notify_session_start({
                'strategy_name': self.strategy.name,
                'symbols': self.symbols,
                'initial_capital': self.initial_capital,
                'mode': self._mode,
                'session_id': self.session_id,
            })

        logger.info(
            f"LIVE TRADING STARTED | Mode: {self._mode} | "
            f"Symbols: {', '.join(self.symbols)} | "
            f"Strategy: {self.strategy.name} | "
            f"Capital: ${self.initial_capital:,.2f} | "
            f"Session: {self.session_id}"
        )

    def stop(self):
        """Stop live trading and finalize session."""
        if self._stopped:
            return
        self._stopped = True
        self.is_running = False
        self._stop_event.set()

        # Calculate performance metrics
        metrics = self._perf_calc.get_performance_summary(
            trades=self._portfolio.trades,
            equity_history=self._portfolio.equity_history,
            initial_capital=self.initial_capital,
        )

        # Determine status
        status = 'killed' if self._safety_guard.is_kill_switch_active() else 'completed'

        if self.db and self.session_id:
            update_data = {
                'end_time': datetime.now().isoformat(),
                'final_capital': metrics.get('final_value', self.initial_capital),
                'total_return': metrics.get('total_return', 0.0),
                'sharpe_ratio': metrics.get('sharpe_ratio'),
                'max_drawdown': metrics.get('max_drawdown'),
                'win_rate': metrics.get('win_rate'),
                'status': status,
            }
            if self._safety_guard.is_kill_switch_active():
                # Attempt to get kill switch reason from db
                try:
                    reason = self.db.get_live_state('kill_switch_reason')
                    update_data['kill_switch_reason'] = reason
                except Exception:
                    pass
            self.db.update_live_session(self.session_id, update_data)

        if self.notifier:
            self.notifier.notify_session_end({
                'strategy_name': self.strategy.name,
                'session_id': self.session_id,
                'total_return': metrics.get('total_return', 0.0),
                'win_rate': metrics.get('win_rate'),
                'max_drawdown': metrics.get('max_drawdown'),
                'status': status,
            })

        self._loop_exited.set()

        logger.info(
            f"LIVE TRADING STOPPED | Session: {self.session_id} | "
            f"Status: {status} | Return: {metrics.get('total_return', 0.0):.2f}%"
        )

    def run_realtime(self, interval_seconds: int = 60, timeframe: str = '1h'):
        """
        Run live trading in real-time.

        Args:
            interval_seconds: Seconds between iterations.
            timeframe: OHLCV timeframe for indicator calculation.
        """
        self.start()

        try:
            while not self._stop_event.is_set():
                for symbol in self.symbols:
                    if self._symbol_error_counts.get(symbol, 0) >= 3:
                        continue
                    try:
                        self._realtime_iteration(symbol, timeframe)
                        self._symbol_error_counts[symbol] = 0
                    except Exception as e:
                        self._symbol_error_counts[symbol] = self._symbol_error_counts.get(symbol, 0) + 1
                        if self._symbol_error_counts[symbol] >= 3:
                            logger.error(
                                f"Symbol {symbol} reached error threshold, "
                                f"skipping in future iterations: {e}"
                            )
                        else:
                            logger.error(
                                f"Failed to process {symbol} "
                                f"(error count: {self._symbol_error_counts[symbol]}): {e}"
                            )

                if self._stop_event.wait(timeout=interval_seconds):
                    break

        except KeyboardInterrupt:
            logger.info("Live trading stopped by user")
        except Exception as e:
            logger.exception(f"Error during live trading: {e}")
        finally:
            self.stop()
            self._loop_exited.set()

    def _realtime_iteration(self, symbol: str, timeframe: str):
        """
        Execute one iteration of live trading for a symbol.

        Args:
            symbol: Trading symbol.
            timeframe: OHLCV timeframe.
        """
        # Kill switch check — skip iteration if active
        if self._safety_guard.is_kill_switch_active():
            logger.warning(f"Kill switch active, skipping iteration for {symbol}")
            return

        # 1. Fetch ticker with CircuitBreaker
        @self._ticker_cb
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch_ticker():
            return self.broker.fetch_ticker(symbol, overseas=True)

        ticker = _fetch_ticker()
        current_price = ticker['last']
        timestamp = datetime.now()

        # 2. Fetch OHLCV with CircuitBreaker
        @self._ohlcv_cb
        @retry_with_backoff(max_retries=3, backoff_factor=2.0, initial_delay=2.0)
        def _fetch_ohlcv():
            return self.broker.fetch_ohlcv(symbol, timeframe, limit=100, overseas=True)

        df = _fetch_ohlcv()
        if df.empty:
            logger.warning(f"No OHLCV data for {symbol}, skipping")
            return

        # 2.5. Adaptive strategy switching + parameter adaptation
        _pre_regime_result = None
        if self._adaptive_manager:
            new_strategy, _pre_regime_result, did_switch = self._adaptive_manager.evaluate(df)
            if did_switch:
                old_name = self.strategy.name
                with self._lock:
                    self.strategy = new_strategy
                logger.info(f"[{symbol}] 전략 전환: {old_name} -> {self.strategy.name}")
                if self.db and self.session_id:
                    self.db.log_strategy_switch(self.session_id, {
                        'timestamp': timestamp, 'symbol': symbol,
                        'from_strategy': old_name, 'to_strategy': self.strategy.name,
                        'regime': _pre_regime_result.regime.value,
                        'confidence': _pre_regime_result.confidence,
                    })
            if self._adaptive_manager._parameter_adapter and _pre_regime_result:
                adapted = self._adaptive_manager._parameter_adapter.adapt(_pre_regime_result)
                self._risk_manager.stop_loss_pct = adapted['stop_loss_pct']
                self._risk_manager.take_profit_pct = adapted['take_profit_pct']
            self._adaptive_manager.tick()

        # 3. Get current signal from strategy
        signal, info = self.strategy.get_current_signal(df)

        # 4. Process signal through pipeline
        signal, _regime_result = self._signal_pipeline.process(
            signal=signal,
            symbol=symbol,
            df=df,
            info=info,
            timestamp=timestamp,
            positions=self._portfolio.positions,
            capital=self._portfolio.capital,
            initial_capital=self.initial_capital,
            strategy_name=self.strategy.name,
            db=self.db,
            session_id=self.session_id,
            pre_detected_regime=_pre_regime_result,
        )

        # 5. Risk manager: check stop loss / take profit
        current_prices = {symbol: current_price}
        risk_actions = self._risk_manager.check_positions(
            positions=self._portfolio.positions,
            entry_prices=self._portfolio.entry_prices,
            current_prices=current_prices,
        )

        for action in risk_actions:
            if action.symbol == symbol:
                self._submit_sell_order(
                    symbol=symbol,
                    price=current_price,
                    reason=action.action,
                )
                # Record equity after risk action
                portfolio_value = self._portfolio.get_portfolio_value(current_prices)
                self._portfolio.record_equity({
                    'timestamp': timestamp,
                    'equity': portfolio_value,
                })
                return  # Skip signal processing after risk action

        # 6. Execute trades based on signal change
        last_signal = self._portfolio.last_signals.get(symbol, 0)

        if signal == 1 and last_signal != 1:
            self._submit_buy_order(symbol=symbol, price=current_price)
        elif signal == -1 and last_signal != -1:
            if self._portfolio.positions.get(symbol, 0) > 0:
                self._submit_sell_order(symbol=symbol, price=current_price, reason='signal')

        self._portfolio.last_signals[symbol] = signal

        # Record equity
        portfolio_value = self._portfolio.get_portfolio_value(current_prices)
        self._portfolio.record_equity({
            'timestamp': timestamp,
            'equity': portfolio_value,
        })

        logger.info(
            f"[{timestamp}] {symbol}: price=${current_price:.2f}, signal={signal}"
        )

    def _submit_buy_order(self, symbol: str, price: float):
        """Submit a buy order via LiveOrderManager."""
        # Calculate quantity
        trade_capital = self._portfolio.capital * self.position_size
        amount = trade_capital / price * (1 - self.commission)

        if amount <= 0:
            return

        order = self._order_manager.submit_order(
            symbol=symbol,
            side='buy',
            amount=amount,
            order_type=self._order_type,
            price=price,
            reason='signal',
            dry_run=(self._mode == 'dry_run'),
            positions=self._portfolio.positions,
            capital=self._portfolio.capital,
        )

        if order.status in ('filled', 'dry_run'):
            filled_amount = order.filled_amount if order.status == 'filled' else amount
            filled_price = order.filled_price if order.status == 'filled' else price

            self._portfolio.positions[symbol] = filled_amount
            self._portfolio.entry_prices[symbol] = filled_price
            self._portfolio.capital -= trade_capital

            self._portfolio.record_trade({
                'symbol': symbol,
                'timestamp': datetime.now(),
                'type': 'BUY',
                'price': filled_price,
                'size': filled_amount,
                'capital': self._portfolio.capital,
                'commission': trade_capital * self.commission,
            })

            logger.info(f"[BUY] {symbol} @ ${filled_price:.2f} x {filled_amount:.6f}")

    def _submit_sell_order(self, symbol: str, price: float, reason: str = 'signal'):
        """Submit a sell order via LiveOrderManager."""
        position = self._portfolio.positions.get(symbol, 0)
        if position <= 0:
            return

        entry_price = self._portfolio.entry_prices.get(symbol, 0)

        order = self._order_manager.submit_order(
            symbol=symbol,
            side='sell',
            amount=position,
            order_type=self._order_type,
            price=price,
            reason=reason,
            dry_run=(self._mode == 'dry_run'),
            positions=self._portfolio.positions,
            capital=self._portfolio.capital,
        )

        if order.status in ('filled', 'dry_run'):
            filled_price = order.filled_price if order.status == 'filled' else price
            filled_amount = order.filled_amount if order.status == 'filled' else position

            # Calculate PnL
            pnl = (filled_price - entry_price) * filled_amount

            # Record trade to safety guard
            self._safety_guard.record_trade(pnl)

            sale_proceeds = filled_amount * filled_price * (1 - self.commission)
            self._portfolio.capital += sale_proceeds
            self._portfolio.positions[symbol] = 0
            self._portfolio.entry_prices[symbol] = 0

            pnl_pct = ((filled_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            self._portfolio.record_trade({
                'symbol': symbol,
                'timestamp': datetime.now(),
                'type': 'SELL',
                'price': filled_price,
                'size': filled_amount,
                'capital': self._portfolio.capital,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'commission': filled_amount * filled_price * self.commission,
                'reason': reason,
            })

            logger.info(
                f"[SELL - {reason}] {symbol} @ ${filled_price:.2f} "
                f"PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)"
            )
