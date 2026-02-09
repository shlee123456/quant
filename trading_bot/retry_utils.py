"""
Retry Utilities for API Calls

API 호출 실패 시 자동 재시도 로직을 제공합니다.

Usage:
    from trading_bot.retry_utils import retry_with_backoff

    @retry_with_backoff(max_retries=3, backoff_factor=2)
    def fetch_data():
        # API call here
        pass
"""

import time
import logging
from functools import wraps
from typing import Callable, Optional, Tuple, Type


logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    API 호출 재시도 데코레이터 (Exponential Backoff)

    Args:
        max_retries: 최대 재시도 횟수
        backoff_factor: 백오프 배수 (지수 증가)
        initial_delay: 초기 대기 시간 (초)
        max_delay: 최대 대기 시간 (초)
        exceptions: 재시도할 예외 타입들
        on_retry: 재시도 시 호출할 콜백 함수 (retry_count, exception)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(max_retries=3, backoff_factor=2)
        def fetch_ticker(symbol):
            return broker.fetch_ticker(symbol)

        # Retry sequence:
        # 1st failure → wait 1s → retry
        # 2nd failure → wait 2s → retry
        # 3rd failure → wait 4s → retry
        # 4th failure → raise exception
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    # 마지막 시도면 예외 발생
                    if attempt == max_retries:
                        logger.error(
                            f"✗ {func.__name__} 실패 (최대 재시도 {max_retries}회 초과): {e}"
                        )
                        raise

                    # 재시도 로그
                    logger.warning(
                        f"⚠ {func.__name__} 실패 (시도 {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    logger.info(f"  {delay:.1f}초 후 재시도...")

                    # 콜백 실행
                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception as callback_error:
                            logger.error(f"재시도 콜백 에러: {callback_error}")

                    # 대기
                    time.sleep(delay)

                    # 다음 대기 시간 계산 (exponential backoff)
                    delay = min(delay * backoff_factor, max_delay)

            # 이론적으로 도달 불가 (방어 코드)
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_on_rate_limit(
    max_retries: int = 5,
    initial_delay: float = 60.0,
    backoff_factor: float = 1.5
):
    """
    Rate Limit 전용 재시도 데코레이터

    API rate limit 에러 시 더 긴 대기 시간으로 재시도합니다.

    Args:
        max_retries: 최대 재시도 횟수
        initial_delay: 초기 대기 시간 (초, 기본 60초)
        backoff_factor: 백오프 배수

    Example:
        @retry_on_rate_limit(max_retries=3, initial_delay=60)
        def fetch_ohlcv(symbol):
            return broker.fetch_ohlcv(symbol)

        # Retry sequence:
        # 1st rate limit → wait 60s → retry
        # 2nd rate limit → wait 90s → retry
        # 3rd rate limit → wait 135s → retry
    """
    def is_rate_limit_error(exception):
        """Rate limit 에러 판별"""
        error_msg = str(exception).lower()
        return any(
            keyword in error_msg
            for keyword in ['rate limit', 'too many requests', '429', 'quota']
        )

    def on_retry_callback(retry_count, exception):
        """Rate limit 재시도 시 로그"""
        logger.warning(
            f"⏱ Rate Limit 감지 - {initial_delay * (backoff_factor ** (retry_count - 1)):.0f}초 대기 중..."
        )

    # Rate limit 관련 예외만 재시도
    return retry_with_backoff(
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        initial_delay=initial_delay,
        max_delay=300.0,  # 최대 5분
        exceptions=(Exception,),  # 모든 예외를 잡아서 rate limit 여부 확인
        on_retry=on_retry_callback
    )


class CircuitBreaker:
    """
    Circuit Breaker 패턴 구현

    연속된 실패 발생 시 일정 시간 동안 요청 차단

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)

        @breaker
        def fetch_data():
            # API call
            pass
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: 회로 차단 실패 횟수 임계값
            timeout: 회로 차단 시간 (초)
            expected_exception: 감지할 예외 타입
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func):
        """Decorator 구현"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            # OPEN 상태: 타임아웃 확인
            if self.state == 'OPEN':
                if time.time() - self.last_failure_time >= self.timeout:
                    logger.info(f"🔄 Circuit Breaker HALF_OPEN: {func.__name__}")
                    self.state = 'HALF_OPEN'
                else:
                    remaining = self.timeout - (time.time() - self.last_failure_time)
                    logger.warning(
                        f"⛔ Circuit Breaker OPEN: {func.__name__} "
                        f"(재개까지 {remaining:.0f}초)"
                    )
                    raise Exception(
                        f"Circuit breaker is OPEN. Retry in {remaining:.0f}s"
                    )

            # 함수 실행
            try:
                result = func(*args, **kwargs)

                # 성공 시 카운터 리셋
                if self.state == 'HALF_OPEN':
                    logger.info(f"✓ Circuit Breaker CLOSED: {func.__name__}")
                    self.state = 'CLOSED'
                    self.failure_count = 0

                return result

            except self.expected_exception as e:
                # 실패 카운트 증가
                self.failure_count += 1
                self.last_failure_time = time.time()

                logger.warning(
                    f"⚠ Circuit Breaker 실패 카운트: {self.failure_count}/{self.failure_threshold}"
                )

                # 임계값 도달 시 회로 차단
                if self.failure_count >= self.failure_threshold:
                    self.state = 'OPEN'
                    logger.error(
                        f"⛔ Circuit Breaker OPEN: {func.__name__} "
                        f"({self.timeout}초 동안 차단)"
                    )

                raise

        return wrapper


# 사전 정의된 재시도 전략
def retry_broker_call(func):
    """
    브로커 API 호출 전용 재시도 데코레이터

    기본 설정:
    - 최대 3회 재시도
    - 2초 → 4초 → 8초 백오프
    """
    return retry_with_backoff(
        max_retries=3,
        backoff_factor=2.0,
        initial_delay=2.0
    )(func)


def retry_database_operation(func):
    """
    데이터베이스 작업 전용 재시도 데코레이터

    기본 설정:
    - 최대 2회 재시도
    - 0.5초 → 1초 백오프
    """
    return retry_with_backoff(
        max_retries=2,
        backoff_factor=2.0,
        initial_delay=0.5
    )(func)
