"""
Tests for retry_utils module

retry_with_backoff, retry_on_rate_limit, CircuitBreaker, retry_broker_call, retry_database_operation
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from trading_bot.retry_utils import (
    retry_with_backoff,
    retry_on_rate_limit,
    CircuitBreaker,
    retry_broker_call,
    retry_database_operation,
)


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------

class TestRetryWithBackoff:

    @patch("trading_bot.retry_utils.time.sleep")
    def test_success_on_first_attempt(self, mock_sleep):
        """첫 번째 시도에 성공하면 재시도 없이 반환"""
        @retry_with_backoff(max_retries=3, initial_delay=1.0)
        def succeed():
            return "ok"

        assert succeed() == "ok"
        mock_sleep.assert_not_called()

    @patch("trading_bot.retry_utils.time.sleep")
    def test_success_after_retries(self, mock_sleep):
        """실패 후 재시도하여 성공"""
        call_count = {"n": 0}

        @retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("fail")
            return "recovered"

        assert flaky() == "recovered"
        assert call_count["n"] == 3
        assert mock_sleep.call_count == 2

    @patch("trading_bot.retry_utils.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        """최대 재시도 초과 시 예외 발생"""
        @retry_with_backoff(max_retries=2, initial_delay=0.1)
        def always_fail():
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError, match="permanent"):
            always_fail()

    @patch("trading_bot.retry_utils.time.sleep")
    def test_only_catches_specified_exceptions(self, mock_sleep):
        """지정한 예외만 재시도"""
        @retry_with_backoff(max_retries=3, exceptions=(ValueError,))
        def wrong_error():
            raise TypeError("not retried")

        with pytest.raises(TypeError):
            wrong_error()
        mock_sleep.assert_not_called()

    @patch("trading_bot.retry_utils.time.sleep")
    def test_on_retry_callback(self, mock_sleep):
        """재시도 콜백 호출 확인"""
        cb = MagicMock()
        call_count = {"n": 0}

        @retry_with_backoff(max_retries=2, initial_delay=0.1, on_retry=cb)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("retry me")
            return "done"

        flaky()
        cb.assert_called_once()
        args = cb.call_args[0]
        assert args[0] == 1  # retry_count
        assert isinstance(args[1], ValueError)

    @patch("trading_bot.retry_utils.time.sleep")
    def test_max_delay_cap(self, mock_sleep):
        """max_delay 초과 방지"""
        @retry_with_backoff(
            max_retries=5, initial_delay=10.0, backoff_factor=10.0, max_delay=30.0
        )
        def always_fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            always_fail()

        # All sleep calls should be <= 30.0
        for call in mock_sleep.call_args_list:
            assert call[0][0] <= 30.0

    @patch("trading_bot.retry_utils.time.sleep")
    def test_callback_error_does_not_break_retry(self, mock_sleep):
        """콜백 에러가 재시도 흐름을 방해하지 않음"""
        def bad_callback(count, exc):
            raise RuntimeError("callback crash")

        call_count = {"n": 0}

        @retry_with_backoff(max_retries=2, initial_delay=0.1, on_retry=bad_callback)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("retry")
            return "ok"

        assert flaky() == "ok"


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_closed_state_success(self):
        """CLOSED 상태에서 성공하면 결과 반환"""
        breaker = CircuitBreaker(failure_threshold=3, timeout=1.0)

        @breaker
        def ok():
            return "result"

        assert ok() == "result"
        assert breaker.state == "CLOSED"

    def test_opens_after_threshold(self):
        """실패가 임계값에 도달하면 OPEN"""
        breaker = CircuitBreaker(failure_threshold=2, timeout=60.0)

        @breaker
        def fail():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                fail()

        assert breaker.state == "OPEN"

    def test_open_state_blocks_calls(self):
        """OPEN 상태에서는 호출 차단"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=60.0)

        @breaker
        def fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            fail()

        assert breaker.state == "OPEN"

        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            fail()

    def test_half_open_after_timeout(self):
        """타임아웃 후 HALF_OPEN 전이"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.1)

        @breaker
        def fail_then_succeed():
            if breaker.state == "HALF_OPEN":
                return "recovered"
            raise ValueError("fail")

        with pytest.raises(ValueError):
            fail_then_succeed()

        assert breaker.state == "OPEN"
        time.sleep(0.15)

        result = fail_then_succeed()
        assert result == "recovered"
        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0

    def test_half_open_failure_reopens(self):
        """HALF_OPEN 상태에서 실패하면 다시 OPEN"""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.1)

        @breaker
        def always_fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            always_fail()
        assert breaker.state == "OPEN"

        time.sleep(0.15)

        with pytest.raises(ValueError):
            always_fail()
        assert breaker.state == "OPEN"


# ---------------------------------------------------------------------------
# Predefined decorators
# ---------------------------------------------------------------------------

class TestPredefinedDecorators:

    @patch("trading_bot.retry_utils.time.sleep")
    def test_retry_broker_call(self, mock_sleep):
        """retry_broker_call은 max_retries=3으로 동작"""
        call_count = {"n": 0}

        @retry_broker_call
        def broker_op():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("network")
            return "done"

        assert broker_op() == "done"
        assert call_count["n"] == 3

    @patch("trading_bot.retry_utils.time.sleep")
    def test_retry_database_operation(self, mock_sleep):
        """retry_database_operation은 max_retries=2로 동작"""
        call_count = {"n": 0}

        @retry_database_operation
        def db_op():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise IOError("locked")
            return "committed"

        assert db_op() == "committed"
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# retry_on_rate_limit
# ---------------------------------------------------------------------------

class TestRetryOnRateLimit:

    @patch("trading_bot.retry_utils.time.sleep")
    def test_rate_limit_decorator_succeeds_on_first_try(self, mock_sleep):
        """rate limit 데코레이터 첫 시도 성공"""
        @retry_on_rate_limit(max_retries=3, initial_delay=1.0)
        def api_call():
            return "ok"

        assert api_call() == "ok"
        mock_sleep.assert_not_called()

    @patch("trading_bot.retry_utils.time.sleep")
    def test_rate_limit_retries_on_error(self, mock_sleep):
        """rate limit 에러 시 재시도"""
        call_count = {"n": 0}

        @retry_on_rate_limit(max_retries=3, initial_delay=1.0)
        def api_call():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise Exception("429 Too Many Requests")
            return "ok"

        assert api_call() == "ok"
        assert call_count["n"] == 2
