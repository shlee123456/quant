"""
Tests for SafetyGuard module (SAFE-001).
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from trading_bot.safety_guard import SafetyGuard


class TestKillSwitch:
    """Kill switch activation and deactivation tests."""

    def test_kill_switch_manual_activation(self):
        """activate -> is_active=True -> deactivate -> is_active=False"""
        guard = SafetyGuard(initial_capital=10000)

        assert guard.is_kill_switch_active() is False

        guard.activate_kill_switch('manual test')
        assert guard.is_kill_switch_active() is True

        guard.deactivate_kill_switch()
        assert guard.is_kill_switch_active() is False

    def test_daily_loss_auto_kill(self):
        """initial_capital=10000, max_daily_loss_pct=0.05, record_trade(-600) -> kill switch activated"""
        guard = SafetyGuard(initial_capital=10000, max_daily_loss_pct=0.05)

        assert guard.is_kill_switch_active() is False

        # -600 is 6% of 10000, exceeds 5% limit
        guard.record_trade(-600)

        assert guard.is_kill_switch_active() is True
        assert guard._daily_pnl == -600
        assert guard._daily_trade_count == 1

    def test_kill_switch_db_persistence(self):
        """Mock db.set_live_state called on activation."""
        mock_db = MagicMock()
        guard = SafetyGuard(initial_capital=10000, db=mock_db)

        guard.activate_kill_switch('test reason')

        mock_db.set_live_state.assert_any_call('kill_switch_active', 'true')
        mock_db.set_live_state.assert_any_call('kill_switch_reason', 'test reason')

    def test_kill_switch_db_deactivation(self):
        """DB updated on deactivation."""
        mock_db = MagicMock()
        guard = SafetyGuard(initial_capital=10000, db=mock_db)

        guard.activate_kill_switch('test')
        guard.deactivate_kill_switch()

        mock_db.set_live_state.assert_any_call('kill_switch_active', 'false')

    def test_kill_switch_notifier(self):
        """Mock notifier.notify_error called on activation."""
        mock_notifier = MagicMock()
        guard = SafetyGuard(initial_capital=10000, notifier=mock_notifier)

        guard.activate_kill_switch('test reason')

        mock_notifier.notify_error.assert_called_once_with(
            'KILL SWITCH: test reason', 'SafetyGuard'
        )

    def test_kill_switch_db_load_on_init(self):
        """Kill switch state loaded from DB on init."""
        mock_db = MagicMock()
        mock_db.get_live_state.return_value = 'true'

        guard = SafetyGuard(initial_capital=10000, db=mock_db)

        assert guard.is_kill_switch_active() is True
        mock_db.get_live_state.assert_called_with('kill_switch_active')

    def test_kill_switch_db_attribute_error_graceful(self):
        """Graceful fallback when DB doesn't have get_live_state."""
        mock_db = MagicMock(spec=[])  # No methods at all

        # Should not raise
        guard = SafetyGuard(initial_capital=10000, db=mock_db)
        assert guard.is_kill_switch_active() is False

    def test_kill_switch_blocks_orders(self):
        """Kill switch active -> pre_order_check returns False."""
        guard = SafetyGuard(initial_capital=10000)
        guard.activate_kill_switch('emergency')

        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 150.0, {}, 10000)
        assert allowed is False
        assert 'Kill switch' in reason


class TestDailyLimits:
    """Daily trade count and loss limit tests."""

    def test_trade_count_limit(self):
        """max_daily_trades=3, 3 trades ok, 4th rejected."""
        guard = SafetyGuard(initial_capital=10000, max_daily_trades=3)

        # Record 3 trades
        for _ in range(3):
            guard.record_trade(0)

        assert guard._daily_trade_count == 3

        # 4th order should be rejected
        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 150.0, {}, 10000)
        assert allowed is False
        assert 'trade count' in reason.lower()

    def test_trade_count_within_limit(self):
        """Trades within limit are allowed."""
        guard = SafetyGuard(initial_capital=10000, max_daily_trades=3)

        guard.record_trade(0)
        guard.record_trade(0)

        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 150.0, {}, 10000)
        assert allowed is True
        assert reason == 'ok'

    def test_daily_counter_reset(self):
        """Change date -> counters reset."""
        guard = SafetyGuard(initial_capital=10000, max_daily_trades=3)

        # Record 3 trades (at limit)
        for _ in range(3):
            guard.record_trade(0)

        assert guard._daily_trade_count == 3

        # Simulate date change
        guard._daily_reset_date = date(2020, 1, 1)

        # pre_order_check should trigger reset
        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 150.0, {}, 10000)
        assert allowed is True
        assert guard._daily_trade_count == 0
        assert guard._daily_pnl == 0.0


class TestPositionLimits:
    """Position count and capital per position tests."""

    def test_position_count_limit(self):
        """max_position_count=2, 2 positions ok, 3rd buy rejected, sell allowed."""
        guard = SafetyGuard(initial_capital=10000, max_position_count=2)

        positions = {'AAPL': 10, 'MSFT': 5}

        # 3rd buy rejected
        allowed, reason = guard.pre_order_check('GOOGL', 'buy', 5, 150.0, positions, 10000)
        assert allowed is False
        assert 'position count' in reason.lower()

        # Sell always allowed regardless of position count
        allowed, reason = guard.pre_order_check('AAPL', 'sell', 10, 150.0, positions, 10000)
        assert allowed is True
        assert reason == 'ok'

    def test_position_count_with_zero_qty(self):
        """Positions with qty=0 are not counted."""
        guard = SafetyGuard(initial_capital=10000, max_position_count=2)

        positions = {'AAPL': 10, 'MSFT': 0, 'GOOGL': 5}

        # Only 2 positions with qty > 0
        allowed, reason = guard.pre_order_check('TSLA', 'buy', 5, 150.0, positions, 10000)
        assert allowed is False

    def test_capital_per_position(self):
        """max_capital_per_position_pct=0.15, reject order exceeding 15%."""
        guard = SafetyGuard(initial_capital=10000, max_capital_per_position_pct=0.15)

        # Order value = 20 * 100 = 2000 = 20% of 10000 capital -> rejected
        allowed, reason = guard.pre_order_check('AAPL', 'buy', 20, 100.0, {}, 10000)
        assert allowed is False
        assert 'capital per position' in reason.lower()

        # Order value = 10 * 100 = 1000 = 10% of 10000 capital -> allowed
        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 100.0, {}, 10000)
        assert allowed is True


class TestSlippageCheck:
    """Post-fill slippage checks."""

    def test_slippage_check(self):
        """tolerance=0.02, 1% ok, 3% not ok."""
        guard = SafetyGuard(initial_capital=10000, slippage_tolerance_pct=0.02)

        # 1% slippage -> ok
        ok, pct = guard.post_fill_check(100.0, 101.0)
        assert ok is True
        assert abs(pct - 0.01) < 1e-9

        # 3% slippage -> not ok
        ok, pct = guard.post_fill_check(100.0, 103.0)
        assert ok is False
        assert abs(pct - 0.03) < 1e-9

    def test_slippage_negative_direction(self):
        """Slippage uses absolute difference."""
        guard = SafetyGuard(initial_capital=10000, slippage_tolerance_pct=0.02)

        # Fill below requested
        ok, pct = guard.post_fill_check(100.0, 97.0)
        assert ok is False
        assert abs(pct - 0.03) < 1e-9

    def test_slippage_zero_requested_price(self):
        """Zero requested price returns ok with 0% slippage."""
        guard = SafetyGuard(initial_capital=10000)

        ok, pct = guard.post_fill_check(0.0, 100.0)
        assert ok is True
        assert pct == 0.0


class TestPreOrderCheckOrder:
    """Verify checks run in the documented order."""

    def test_kill_switch_checked_first(self):
        """Kill switch takes priority over all other checks."""
        guard = SafetyGuard(
            initial_capital=10000,
            max_daily_trades=0,  # would also fail
            max_position_count=0,  # would also fail
        )
        guard.activate_kill_switch('test')

        allowed, reason = guard.pre_order_check('AAPL', 'buy', 10, 150.0, {'X': 1}, 10000)
        assert allowed is False
        assert 'Kill switch' in reason

    def test_all_checks_pass(self):
        """When all checks pass, returns (True, 'ok')."""
        guard = SafetyGuard(initial_capital=10000)

        allowed, reason = guard.pre_order_check('AAPL', 'buy', 1, 100.0, {}, 10000)
        assert allowed is True
        assert reason == 'ok'
