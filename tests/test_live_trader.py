"""
Tests for LiveTrader class (LIVE-001).

Tests:
- test_init_creates_all_components
- test_dry_run_signal_to_order
- test_stop_loss_triggers_sell
- test_kill_switch_skips_iteration
- test_session_lifecycle
- test_filled_order_updates_portfolio
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from trading_bot.live_trader import LiveTrader
from trading_bot.safety_guard import SafetyGuard
from trading_bot.live_order_manager import LiveOrderManager, LiveOrder
from trading_bot.portfolio_manager import PortfolioManager
from trading_bot.signal_pipeline import SignalPipeline
from trading_bot.risk_manager import RiskManager, RiskAction
from trading_bot.performance_calculator import PerformanceCalculator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv_df(rows=100, close_price=150.0):
    """Create a minimal OHLCV DataFrame for testing."""
    data = {
        'open': [close_price] * rows,
        'high': [close_price + 1] * rows,
        'low': [close_price - 1] * rows,
        'close': [close_price] * rows,
        'volume': [1000] * rows,
    }
    return pd.DataFrame(data)


def _make_mock_broker():
    """Create a mock broker with typical attributes."""
    broker = MagicMock()
    broker.name = 'KIS'
    broker.market_type = 'stock'
    broker.fetch_ticker.return_value = {'last': 150.0}
    broker.fetch_ohlcv.return_value = _make_ohlcv_df()
    return broker


def _make_mock_strategy(signal=0):
    """Create a mock strategy that returns a fixed signal."""
    strategy = MagicMock()
    strategy.name = 'TestStrategy'
    strategy.get_current_signal.return_value = (signal, {
        'close': 150.0,
        'timestamp': datetime.now(),
    })
    return strategy


def _make_mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.create_live_session = MagicMock()
    db.update_live_session = MagicMock()
    db.get_live_state = MagicMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLiveTraderInit:
    """Test LiveTrader initialization creates all components."""

    def test_init_creates_all_components(self):
        """Verify SafetyGuard, LiveOrderManager, PortfolioManager,
        SignalPipeline, RiskManager, PerformanceCalculator are created."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()

        trader = LiveTrader(
            strategy=strategy,
            symbols=['AAPL', 'MSFT'],
            broker=broker,
            initial_capital=10000.0,
        )

        assert isinstance(trader._safety_guard, SafetyGuard)
        assert isinstance(trader._order_manager, LiveOrderManager)
        assert isinstance(trader._portfolio, PortfolioManager)
        assert isinstance(trader._signal_pipeline, SignalPipeline)
        assert isinstance(trader._risk_manager, RiskManager)
        assert isinstance(trader._perf_calc, PerformanceCalculator)

        # Verify symbols normalized to list
        assert trader.symbols == ['AAPL', 'MSFT']

        # Verify single string symbol also normalized
        trader2 = LiveTrader(
            strategy=strategy, symbols='AAPL', broker=broker,
        )
        assert trader2.symbols == ['AAPL']

    def test_init_default_mode_is_dry_run(self):
        """Default mode should be 'dry_run'."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()

        trader = LiveTrader(
            strategy=strategy, symbols='AAPL', broker=broker,
        )
        assert trader._mode == 'dry_run'

    def test_init_safety_guard_params(self):
        """SafetyGuard should receive correct params."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=50000.0,
            max_daily_loss_pct=0.03,
            max_daily_trades=20,
            max_position_count=5,
        )

        assert trader._safety_guard.initial_capital == 50000.0
        assert trader._safety_guard.max_daily_loss_pct == 0.03
        assert trader._safety_guard.max_daily_trades == 20
        assert trader._safety_guard.max_position_count == 5


class TestDryRunSignalToOrder:
    """Test that in dry_run mode, orders go through LiveOrderManager
    with dry_run=True."""

    def test_dry_run_signal_to_order(self):
        """Mock strategy returns BUY, verify _order_manager.submit_order
        called with dry_run=True."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy(signal=1)

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=10000.0,
            mode='dry_run',
        )
        trader.session_id = 'test_session'

        # Mock order manager to return a dry_run order
        dry_run_order = LiveOrder(
            symbol='AAPL',
            side='buy',
            status='dry_run',
            requested_amount=63.0,
            requested_price=150.0,
        )
        trader._order_manager.submit_order = MagicMock(return_value=dry_run_order)

        # Mock signal pipeline to pass through
        trader._signal_pipeline.process = MagicMock(return_value=(1, None))

        # Run one iteration
        trader._realtime_iteration('AAPL', '1h')

        # Verify submit_order was called with dry_run=True
        trader._order_manager.submit_order.assert_called_once()
        call_kwargs = trader._order_manager.submit_order.call_args
        assert call_kwargs[1]['dry_run'] is True or call_kwargs.kwargs.get('dry_run') is True


class TestStopLossTriggersSell:
    """Test that stop loss triggers a sell order."""

    def test_stop_loss_triggers_sell(self):
        """Mock position with loss, verify sell order submitted
        with reason='stop_loss'."""
        broker = _make_mock_broker()
        # Strategy returns HOLD so only risk manager triggers action
        strategy = _make_mock_strategy(signal=0)

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=10000.0,
            stop_loss_pct=0.05,
        )
        trader.session_id = 'test_session'

        # Set up a position with a loss > stop_loss_pct
        trader._portfolio.positions['AAPL'] = 10.0
        trader._portfolio.entry_prices['AAPL'] = 160.0

        # Current price = 150.0 (6.25% loss > 5% stop loss)
        # The mock broker returns ticker with last=150.0

        # Mock signal pipeline
        trader._signal_pipeline.process = MagicMock(return_value=(0, None))

        # Mock order manager
        sell_order = LiveOrder(
            symbol='AAPL', side='sell', status='filled',
            filled_amount=10.0, filled_price=150.0,
        )
        trader._order_manager.submit_order = MagicMock(return_value=sell_order)

        trader._realtime_iteration('AAPL', '1h')

        # Verify sell order submitted with reason='stop_loss'
        trader._order_manager.submit_order.assert_called_once()
        call_kwargs = trader._order_manager.submit_order.call_args
        assert call_kwargs.kwargs.get('reason') == 'stop_loss' or \
               (len(call_kwargs.args) > 0 and 'stop_loss' in str(call_kwargs))


class TestKillSwitchSkipsIteration:
    """Test that kill switch prevents order execution."""

    def test_kill_switch_skips_iteration(self):
        """Activate kill switch, verify no orders placed."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy(signal=1)

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
        )
        trader.session_id = 'test_session'

        # Activate kill switch
        trader._safety_guard.activate_kill_switch('test reason')

        # Mock order manager
        trader._order_manager.submit_order = MagicMock()

        # Run iteration
        trader._realtime_iteration('AAPL', '1h')

        # Verify no orders placed
        trader._order_manager.submit_order.assert_not_called()

        # Also verify broker was NOT called (early return)
        broker.fetch_ticker.assert_not_called()


class TestSessionLifecycle:
    """Test session start/stop with database."""

    def test_session_lifecycle(self):
        """Start creates session in DB, stop updates with metrics."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()
        db = _make_mock_db()

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=10000.0,
            db=db,
            mode='dry_run',
        )

        # Start session
        trader.start()

        # Verify session created in DB
        db.create_live_session.assert_called_once()
        call_kwargs = db.create_live_session.call_args
        assert call_kwargs.kwargs['strategy_name'] == 'TestStrategy'
        assert call_kwargs.kwargs['mode'] == 'dry_run'
        assert call_kwargs.kwargs['initial_capital'] == 10000.0

        # Verify session_id format
        assert trader.session_id.startswith('live_TestStrategy_')

        # Stop session
        trader.stop()

        # Verify session updated in DB
        db.update_live_session.assert_called_once()
        update_call = db.update_live_session.call_args
        assert update_call.args[0] == trader.session_id
        updates = update_call.args[1]
        assert 'end_time' in updates
        assert 'status' in updates
        assert updates['status'] == 'completed'
        assert 'total_return' in updates

    def test_session_id_format_with_spaces(self):
        """Strategy name with spaces should have them replaced by underscores."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()
        strategy.name = 'RSI MACD Combo'

        trader = LiveTrader(
            strategy=strategy, symbols='AAPL', broker=broker,
        )
        trader.start()

        assert 'RSI_MACD_Combo' in trader.session_id
        assert ' ' not in trader.session_id

    def test_stop_with_kill_switch_sets_killed_status(self):
        """If kill switch is active, stop should set status='killed'."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()
        db = _make_mock_db()

        trader = LiveTrader(
            strategy=strategy, symbols='AAPL', broker=broker, db=db,
        )
        trader.start()
        trader._safety_guard.activate_kill_switch('test kill')
        trader.stop()

        update_call = db.update_live_session.call_args
        updates = update_call.args[1]
        assert updates['status'] == 'killed'


class TestFilledOrderUpdatesPortfolio:
    """Test that filled orders correctly update portfolio state."""

    def test_filled_order_updates_portfolio(self):
        """Mock filled order, verify portfolio positions updated
        with fill price not signal price."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy(signal=1)

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=10000.0,
            mode='live',
        )
        trader.session_id = 'test_session'

        # Mock signal pipeline
        trader._signal_pipeline.process = MagicMock(return_value=(1, None))

        # Mock order manager to return a filled order with different fill price
        filled_order = LiveOrder(
            symbol='AAPL',
            side='buy',
            status='filled',
            requested_amount=63.0,
            requested_price=150.0,
            filled_amount=62.5,
            filled_price=151.0,  # Fill price differs from signal price
        )
        trader._order_manager.submit_order = MagicMock(return_value=filled_order)

        # Run iteration
        trader._realtime_iteration('AAPL', '1h')

        # Verify portfolio updated with fill price/amount, not signal price
        assert trader._portfolio.positions['AAPL'] == 62.5
        assert trader._portfolio.entry_prices['AAPL'] == 151.0

    def test_sell_order_records_pnl_and_clears_position(self):
        """After a filled sell, position should be cleared and PnL recorded."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy(signal=-1)

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            initial_capital=10000.0,
            mode='live',
        )
        trader.session_id = 'test_session'

        # Set up existing position
        trader._portfolio.positions['AAPL'] = 10.0
        trader._portfolio.entry_prices['AAPL'] = 140.0
        trader._portfolio.last_signals['AAPL'] = 1  # Was in BUY state

        # Mock signal pipeline
        trader._signal_pipeline.process = MagicMock(return_value=(-1, None))

        # Mock order manager
        filled_sell = LiveOrder(
            symbol='AAPL', side='sell', status='filled',
            filled_amount=10.0, filled_price=150.0,
        )
        trader._order_manager.submit_order = MagicMock(return_value=filled_sell)

        trader._realtime_iteration('AAPL', '1h')

        # Position should be cleared
        assert trader._portfolio.positions['AAPL'] == 0
        assert trader._portfolio.entry_prices['AAPL'] == 0

        # A SELL trade should be recorded
        sell_trades = [t for t in trader._portfolio.trades if t['type'] == 'SELL']
        assert len(sell_trades) == 1
        assert sell_trades[0]['pnl'] == (150.0 - 140.0) * 10.0  # $100 profit

    def test_notifier_called_on_session_start_and_stop(self):
        """Verify notifier is called for session lifecycle."""
        broker = _make_mock_broker()
        strategy = _make_mock_strategy()
        notifier = MagicMock()

        trader = LiveTrader(
            strategy=strategy,
            symbols='AAPL',
            broker=broker,
            notifier=notifier,
        )

        trader.start()
        notifier.notify_session_start.assert_called_once()

        trader.stop()
        notifier.notify_session_end.assert_called_once()
