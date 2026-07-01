"""
Utility functions for retry logic and exponential backoff
"""
import asyncio
import logging
from typing import Callable, TypeVar, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def retry_async(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retry_on: tuple = (Exception,),
    on_failure: Optional[Callable] = None,
    **kwargs
) -> Optional[T]:
    """
    Run async retry logic with exponential backoff.

    Args:
        func: Callable to execute
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Exponential backoff multiplier
        retry_on: Exception tuple that should trigger retry
        on_failure: Callback for final failure
        **kwargs: Keyword arguments passed to ``func``

    Returns:
        Function result or ``None`` on failure
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(**kwargs)
            else:
                return func(**kwargs)

        except retry_on as e:
            last_error = e

            if attempt >= max_attempts:
                logger.error(f"[ERROR] Retry failed after {max_attempts} attempts: {e}")
                if on_failure:
                    on_failure(e)
                return None

            # Exponential backoff.
            delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
            logger.warning(f"[WARN] Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)

        except Exception as e:
            # Unexpected error, do not retry.
            logger.error(f"[ERROR] Unexpected error (not retrying): {e}")
            if on_failure:
                on_failure(e)
            return None

    logger.error(f"[ERROR] All {max_attempts} attempts failed")
    if on_failure and last_error:
        on_failure(last_error)
    return None


def retry_sync(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retry_on: tuple = (Exception,),
    on_failure: Optional[Callable] = None,
    **kwargs
) -> Optional[T]:
    """
    Run sync retry logic with exponential backoff.

    Args:
        func: Callable to execute
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Exponential backoff multiplier
        retry_on: Exception tuple that should trigger retry
        on_failure: Callback for final failure
        **kwargs: Keyword arguments passed to ``func``

    Returns:
        Function result or ``None`` on failure
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func(**kwargs)

        except retry_on as e:
            last_error = e

            if attempt >= max_attempts:
                logger.error(f"[ERROR] Retry failed after {max_attempts} attempts: {e}")
                if on_failure:
                    on_failure(e)
                return None

            # Exponential backoff.
            delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
            logger.warning(f"[WARN] Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s...")
            import time
            time.sleep(delay)

        except Exception as e:
            # Unexpected error, do not retry.
            logger.error(f"[ERROR] Unexpected error (not retrying): {e}")
            if on_failure:
                on_failure(e)
            return None

    logger.error(f"[ERROR] All {max_attempts} attempts failed")
    if on_failure and last_error:
        on_failure(last_error)
    return None


def async_retry_decorator(max_attempts: int = 3, initial_delay: float = 1.0, max_delay: float = 30.0):
    """
    Decorator for retrying async functions.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                max_delay=max_delay,
                **kwargs
            )
        return wrapper
    return decorator

