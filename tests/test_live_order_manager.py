"""
Tests for LiveOrderManager module (ORD-001).

Covers: successful market order, dry run, insufficient funds,
rate limit retry, fill polling timeout, slippage calculation,
cancel order, cancel without broker_id, dedup rejection.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from trading_bot.brokers.base_broker import (
    BaseBroker,
    BrokerError,
    InsufficientFunds,
    RateLimitExceeded,
)
from trading_bot.live_order_manager import LiveOrder, LiveOrderManager
from trading_bot.safety_guard import SafetyGuard


@pytest.fixture
def mock_broker():
    """Create a mock broker that satisfies BaseBroker interface."""
    broker = MagicMock(spec=BaseBroker)
    broker.name = 'TestBroker'
    broker.market_type = 'stock_global'
    return broker


@pytest.fixture
def safety_guard():
    """Create a SafetyGuard with generous limits for testing."""
    return SafetyGuard(
        initial_capital=100000.0,
        max_daily_loss_pct=0.10,
        max_daily_trades=100,
        max_position_count=20,
        max_capital_per_position_pct=0.50,
        slippage_tolerance_pct=0.05,
    )


@pytest.fixture
def mock_db():
    """Create a mock TradingDatabase."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_notifier():
    """Create a mock NotificationService."""
    notifier = MagicMock()
    return notifier


@pytest.fixture
def manager(mock_broker, safety_guard, mock_db, mock_notifier):
    """Create a LiveOrderManager with all dependencies mocked."""
    return LiveOrderManager(
        broker=mock_broker,
        safety_guard=safety_guard,
        db=mock_db,
        notifier=mock_notifier,
        session_id='test_session_001',
    )


class TestSuccessfulMarketOrder:
    """test_successful_market_order: mock broker returns id, fetch_order returns filled."""

    def test_market_order_filled(self, manager, mock_broker):
        # broker.create_order returns an order with 'open' status
        mock_broker.create_order.return_value = {
            'id': 'broker-order-123',
            'status': 'open',
            'amount': 10.0,
            'price': 150.0,
        }
        # broker.fetch_order returns filled status
        mock_broker.fetch_order.return_value = {
            'id': 'broker-order-123',
            'status': 'filled',
            'filled': 10.0,
            'average': 150.25,
            'fee': {'cost': 0.15},
        }

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'filled'
        assert order.broker_order_id == 'broker-order-123'
        assert order.filled_amount == 10.0
        assert order.filled_price == 150.25
        assert order.filled_at is not None
        mock_broker.create_order.assert_called_once_with(
            'AAPL', 'market', 'buy', 10.0, 150.0
        )

    def test_market_order_immediately_filled(self, manager, mock_broker):
        """Broker returns 'closed' status immediately from create_order."""
        mock_broker.create_order.return_value = {
            'id': 'broker-order-456',
            'status': 'closed',
            'filled': 5.0,
            'average': 200.0,
            'amount': 5.0,
            'fee': {'cost': 0.10},
        }

        order = manager.submit_order(
            symbol='MSFT',
            side='buy',
            amount=5.0,
            order_type='market',
            price=200.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'filled'
        assert order.filled_amount == 5.0
        assert order.filled_price == 200.0
        # fetch_order should NOT be called since already filled
        mock_broker.fetch_order.assert_not_called()


class TestDryRun:
    """test_dry_run_no_broker_call: verify broker.create_order not called."""

    def test_dry_run_skips_broker(self, manager, mock_broker):
        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            dry_run=True,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'dry_run'
        assert order.broker_order_id is None
        mock_broker.create_order.assert_not_called()

    def test_dry_run_still_checks_safety(self, manager, mock_broker):
        """Dry run should still pass safety guard checks."""
        # Activate kill switch
        manager.safety_guard.activate_kill_switch('test')

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            dry_run=True,
            positions={},
            capital=50000.0,
        )

        # Should be rejected by safety guard, not dry_run
        assert order.status == 'rejected'
        assert 'Kill switch' in order.error_message
        mock_broker.create_order.assert_not_called()

        # Cleanup
        manager.safety_guard.deactivate_kill_switch()


class TestInsufficientFunds:
    """test_insufficient_funds: mock raises InsufficientFunds, verify status='failed'."""

    def test_insufficient_funds_sets_failed(self, manager, mock_broker, mock_notifier):
        mock_broker.create_order.side_effect = InsufficientFunds(
            'Not enough funds for AAPL'
        )

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'failed'
        assert 'Not enough funds' in order.error_message
        mock_notifier.notify_error.assert_called_once()


class TestRateLimitRetry:
    """test_rate_limit_retry: mock raises RateLimitExceeded twice then succeeds."""

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_retry_succeeds_after_two_failures(
        self, mock_sleep, manager, mock_broker
    ):
        # First call raises RateLimitExceeded
        # Retry 1 raises RateLimitExceeded
        # Retry 2 succeeds
        mock_broker.create_order.side_effect = [
            RateLimitExceeded('Rate limit'),
            RateLimitExceeded('Rate limit'),
            {
                'id': 'broker-order-retry',
                'status': 'closed',
                'filled': 10.0,
                'average': 150.0,
                'fee': {'cost': 0.0},
            },
        ]

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'filled'
        assert order.broker_order_id == 'broker-order-retry'
        # create_order called 3 times total (1 initial + 2 retries)
        assert mock_broker.create_order.call_count == 3

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_retry_exhausted(self, mock_sleep, manager, mock_broker, mock_notifier):
        """All 3 retries fail with RateLimitExceeded."""
        mock_broker.create_order.side_effect = RateLimitExceeded('Rate limit')

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'failed'
        assert 'RateLimitExceeded after 3 retries' in order.error_message
        # 1 initial + 3 retries = 4 calls
        assert mock_broker.create_order.call_count == 4
        mock_notifier.notify_error.assert_called()


class TestFillPollingTimeout:
    """test_fill_polling_timeout: mock fetch_order always returns 'open',
    verify status='submitted' after 5 polls."""

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_polling_timeout_sets_submitted(
        self, mock_sleep, manager, mock_broker
    ):
        mock_broker.create_order.return_value = {
            'id': 'broker-order-pending',
            'status': 'open',
        }
        mock_broker.fetch_order.return_value = {
            'id': 'broker-order-pending',
            'status': 'open',
        }

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'submitted'
        assert mock_broker.fetch_order.call_count == 5

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_limit_order_skips_polling(self, mock_sleep, manager, mock_broker):
        """Limit orders should not trigger fill polling."""
        mock_broker.create_order.return_value = {
            'id': 'broker-order-limit',
            'status': 'open',
        }

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='limit',
            price=145.0,
            positions={},
            capital=50000.0,
        )

        # Limit orders skip polling, status stays as submitted
        assert order.status == 'submitted'
        mock_broker.fetch_order.assert_not_called()


class TestSlippageCalc:
    """test_slippage_calc: requested=100, filled=102, verify slippage_pct=0.02."""

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_slippage_calculation(self, mock_sleep, manager, mock_broker):
        mock_broker.create_order.return_value = {
            'id': 'broker-slippage',
            'status': 'open',
        }
        mock_broker.fetch_order.return_value = {
            'id': 'broker-slippage',
            'status': 'filled',
            'filled': 10.0,
            'average': 102.0,
            'fee': {'cost': 0.0},
        }

        order = manager.submit_order(
            symbol='TEST',
            side='buy',
            amount=10.0,
            order_type='market',
            price=100.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'filled'
        assert abs(order.slippage_pct - 0.02) < 1e-10

    @patch('trading_bot.live_order_manager.time.sleep')
    def test_slippage_not_calculated_without_price(
        self, mock_sleep, manager, mock_broker
    ):
        """Slippage should not be calculated when requested_price is None."""
        mock_broker.create_order.return_value = {
            'id': 'broker-no-price',
            'status': 'closed',
            'filled': 10.0,
            'average': 150.0,
            'fee': {'cost': 0.0},
        }

        order = manager.submit_order(
            symbol='TEST',
            side='buy',
            amount=10.0,
            order_type='market',
            price=None,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'filled'
        assert order.slippage_pct == 0.0


class TestCancelOrder:
    """test_cancel_order_success and test_cancel_order_no_broker_id."""

    def test_cancel_order_success(self, manager, mock_broker):
        # Manually add an active order with broker_order_id
        order = LiveOrder(
            symbol='AAPL',
            side='buy',
            status='submitted',
            broker_order_id='broker-cancel-123',
        )
        manager._active_orders[order.internal_id] = order

        mock_broker.cancel_order.return_value = {'status': 'canceled'}

        result = manager.cancel_order(order.internal_id)

        assert result is True
        assert order.status == 'canceled'
        mock_broker.cancel_order.assert_called_once_with(
            'broker-cancel-123', 'AAPL'
        )

    def test_cancel_order_no_broker_id(self, manager, mock_broker):
        """Cancel should return False if broker_order_id is None."""
        order = LiveOrder(
            symbol='AAPL',
            side='buy',
            status='pending',
            broker_order_id=None,
        )
        manager._active_orders[order.internal_id] = order

        result = manager.cancel_order(order.internal_id)

        assert result is False
        mock_broker.cancel_order.assert_not_called()

    def test_cancel_order_not_found(self, manager):
        """Cancel should return False if order not in active orders."""
        result = manager.cancel_order('nonexistent-id')
        assert result is False

    def test_cancel_all_orders(self, manager, mock_broker):
        """cancel_all_orders should cancel all pending/submitted orders."""
        order1 = LiveOrder(
            symbol='AAPL', side='buy', status='submitted',
            broker_order_id='b1',
        )
        order2 = LiveOrder(
            symbol='MSFT', side='sell', status='pending',
            broker_order_id='b2',
        )
        order3 = LiveOrder(
            symbol='GOOGL', side='buy', status='filled',
            broker_order_id='b3',
        )
        manager._active_orders[order1.internal_id] = order1
        manager._active_orders[order2.internal_id] = order2
        manager._active_orders[order3.internal_id] = order3

        mock_broker.cancel_order.return_value = {'status': 'canceled'}

        count = manager.cancel_all_orders()

        assert count == 2  # order3 is filled, not canceled
        assert order1.status == 'canceled'
        assert order2.status == 'canceled'
        assert order3.status == 'filled'


class TestDedupRejection:
    """test_dedup_rejection: two orders same symbol+side within 1 second,
    second rejected."""

    def test_duplicate_order_rejected(self, manager, mock_broker):
        mock_broker.create_order.return_value = {
            'id': 'broker-first',
            'status': 'closed',
            'filled': 10.0,
            'average': 150.0,
            'fee': {'cost': 0.0},
        }

        # First order succeeds
        order1 = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )
        assert order1.status == 'filled'

        # Second order same symbol+side immediately (within 5 seconds)
        order2 = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order2.status == 'rejected'
        assert 'Duplicate order within 5 seconds' in order2.error_message
        # Broker should only be called once (for order1)
        assert mock_broker.create_order.call_count == 1

    def test_different_side_not_duplicate(self, manager, mock_broker):
        """Different side should not trigger dedup."""
        mock_broker.create_order.return_value = {
            'id': 'broker-1',
            'status': 'closed',
            'filled': 10.0,
            'average': 150.0,
            'fee': {'cost': 0.0},
        }

        order1 = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        mock_broker.create_order.return_value = {
            'id': 'broker-2',
            'status': 'closed',
            'filled': 10.0,
            'average': 151.0,
            'fee': {'cost': 0.0},
        }

        order2 = manager.submit_order(
            symbol='AAPL',
            side='sell',
            amount=10.0,
            order_type='market',
            price=151.0,
            positions={'AAPL': 10.0},
            capital=0.0,
        )

        assert order1.status == 'filled'
        assert order2.status == 'filled'
        assert mock_broker.create_order.call_count == 2


class TestDBLogging:
    """Verify DB interactions."""

    def test_order_logged_to_db(self, manager, mock_broker, mock_db):
        mock_broker.create_order.return_value = {
            'id': 'broker-db',
            'status': 'closed',
            'filled': 10.0,
            'average': 150.0,
            'fee': {'cost': 0.0},
        }

        manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        mock_db.log_live_order.assert_called_once()
        logged = mock_db.log_live_order.call_args[0][0]
        assert logged['symbol'] == 'AAPL'
        assert logged['side'] == 'buy'
        assert logged['session_id'] == 'test_session_001'


class TestGetPendingOrders:
    """Test get_pending_orders method."""

    def test_returns_pending_and_submitted(self, manager):
        order1 = LiveOrder(symbol='AAPL', side='buy', status='pending')
        order2 = LiveOrder(symbol='MSFT', side='sell', status='submitted')
        order3 = LiveOrder(symbol='GOOGL', side='buy', status='filled')
        manager._active_orders[order1.internal_id] = order1
        manager._active_orders[order2.internal_id] = order2
        manager._active_orders[order3.internal_id] = order3

        pending = manager.get_pending_orders()

        assert len(pending) == 2
        statuses = {o.status for o in pending}
        assert statuses == {'pending', 'submitted'}


class TestLiveOrderDataclass:
    """Test LiveOrder dataclass defaults."""

    def test_defaults(self):
        order = LiveOrder()
        assert order.internal_id  # should have uuid
        assert order.broker_order_id is None
        assert order.status == 'pending'
        assert order.filled_amount == 0.0
        assert order.filled_price == 0.0
        assert order.commission == 0.0
        assert order.slippage_pct == 0.0
        assert order.error_message is None
        assert order.filled_at is None
        assert isinstance(order.submitted_at, datetime)


class TestStatusNormalization:
    """Test broker status normalization."""

    def test_normalize_closed(self):
        from trading_bot.live_order_manager import _normalize_broker_status
        assert _normalize_broker_status('closed') == 'filled'
        assert _normalize_broker_status('filled') == 'filled'
        assert _normalize_broker_status('Closed') == 'filled'

    def test_normalize_open(self):
        from trading_bot.live_order_manager import _normalize_broker_status
        assert _normalize_broker_status('open') == 'pending'
        assert _normalize_broker_status('pending') == 'pending'
        assert _normalize_broker_status('submitted') == 'pending'

    def test_normalize_canceled(self):
        from trading_bot.live_order_manager import _normalize_broker_status
        assert _normalize_broker_status('canceled') == 'canceled'
        assert _normalize_broker_status('cancelled') == 'canceled'


class TestBrokerError:
    """Test generic BrokerError handling."""

    def test_broker_error_sets_failed(self, manager, mock_broker, mock_notifier):
        mock_broker.create_order.side_effect = BrokerError(
            'Something went wrong with the broker'
        )

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            order_type='market',
            price=150.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'failed'
        assert 'Something went wrong' in order.error_message
        mock_notifier.notify_error.assert_called_once()

    def test_error_message_truncated(self, manager, mock_broker):
        long_msg = 'x' * 1000
        mock_broker.create_order.side_effect = BrokerError(long_msg)

        order = manager.submit_order(
            symbol='AAPL',
            side='buy',
            amount=10.0,
            positions={},
            capital=50000.0,
        )

        assert order.status == 'failed'
        assert len(order.error_message) == 500
