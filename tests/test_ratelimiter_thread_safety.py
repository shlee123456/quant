"""
RateLimiter 스레드 안전성 테스트.

여러 스레드가 동시에 wait()을 호출할 때:
1. self.calls 리스트에 레이스 컨디션이 없는지 확인
2. 실제 호출 속도가 max_calls/period를 초과하지 않는지 확인
"""

import threading
import time

import pytest

from trading_bot.brokers.korea_investment_broker import RateLimiter


class TestRateLimiterThreadSafety:
    """RateLimiter의 멀티스레드 안전성 검증."""

    def test_lock_exists(self):
        """RateLimiter에 _lock 속성이 존재하는지 확인."""
        rl = RateLimiter(max_calls=10, period=1.0)
        assert hasattr(rl, '_lock')
        assert isinstance(rl._lock, type(threading.RLock()))

    def test_single_thread_rate_limit(self):
        """단일 스레드에서 rate limit이 정상 동작하는지 확인."""
        max_calls = 5
        rl = RateLimiter(max_calls=max_calls, period=1.0)

        start = time.time()
        for _ in range(max_calls + 2):
            rl.wait()
        elapsed = time.time() - start

        # max_calls를 초과하면 최소 period만큼 대기해야 함
        assert elapsed >= 0.5, f"Rate limit이 동작하지 않음: {elapsed:.3f}s"

    def test_concurrent_threads_respect_rate_limit(self):
        """여러 스레드가 동시에 호출해도 rate limit을 준수하는지 확인."""
        max_calls = 10
        period = 1.0
        rl = RateLimiter(max_calls=max_calls, period=period)

        call_timestamps = []
        lock = threading.Lock()
        num_threads = 5
        calls_per_thread = 4  # 총 20회 호출 (max_calls=10 초과)

        def worker():
            for _ in range(calls_per_thread):
                rl.wait()
                with lock:
                    call_timestamps.append(time.time())

        threads = [
            threading.Thread(target=worker, name=f"worker-{i}")
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        total_calls = num_threads * calls_per_thread
        assert len(call_timestamps) == total_calls, (
            f"일부 호출 누락: {len(call_timestamps)}/{total_calls}"
        )

        # 임의의 1초 구간(슬라이딩 윈도우) 내 호출 수가 max_calls를 크게 초과하지 않는지 확인.
        # sleep 정밀도 한계로 +2 여유를 둔다.
        call_timestamps.sort()
        for i, ts in enumerate(call_timestamps):
            window_end = ts + period
            count_in_window = sum(1 for t in call_timestamps[i:] if t <= window_end)
            assert count_in_window <= max_calls + 2, (
                f"1초 윈도우 내 {count_in_window}회 호출 (limit={max_calls})"
            )

    def test_no_race_condition_on_calls_list(self):
        """여러 스레드가 동시에 wait() 호출 시 self.calls 리스트가 손상되지 않는지 확인."""
        max_calls = 50  # 높은 limit으로 sleep 없이 빠르게 테스트
        rl = RateLimiter(max_calls=max_calls, period=0.5)

        num_threads = 10
        calls_per_thread = 10
        barrier = threading.Barrier(num_threads)

        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)  # 모든 스레드가 동시에 시작
                for _ in range(calls_per_thread):
                    rl.wait()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, name=f"racer-{i}")
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"스레드 에러 발생: {errors}"

        # calls 리스트가 유효한 상태인지 확인
        with rl._lock:
            for ts in rl.calls:
                assert isinstance(ts, float), f"잘못된 타임스탬프: {ts}"

    def test_shared_limiter_across_brokers(self):
        """동일한 RateLimiter를 여러 '브로커'가 공유할 때 rate limit 준수 확인."""
        shared_limiter = RateLimiter(max_calls=8, period=1.0)

        call_count = 0
        count_lock = threading.Lock()

        def fake_broker_call():
            nonlocal call_count
            for _ in range(6):
                shared_limiter.wait()
                with count_lock:
                    call_count += 1

        threads = [
            threading.Thread(target=fake_broker_call, name=f"broker-{i}")
            for i in range(3)
        ]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        elapsed = time.time() - start

        # 3 브로커 × 6 호출 = 18회, limit 8/s이므로 최소 ~1초 이상 소요
        assert call_count == 18
        assert elapsed >= 1.0, (
            f"공유 RateLimiter가 rate limit을 준수하지 않음: {elapsed:.3f}s"
        )
