"""
Async Operations Utilities
Task 7.5: Implement async operations for better performance
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Callable, Optional, TypeVar, Coroutine
from functools import wraps
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def gather_with_timeout(
    *coroutines: Coroutine,
    timeout: float = 30.0,
    return_exceptions: bool = True
) -> List[Any]:
    """
    Execute multiple coroutines in parallel with timeout
    
    [OK] OPTIMIZED: Parallel execution instead of sequential
    
    Args:
        *coroutines: Coroutines to execute
        timeout: Total timeout in seconds (default: 30s)
        return_exceptions: Whether to return exceptions instead of raising
        
    Returns:
        List of results (or exceptions if return_exceptions=True)
        
    Example:
        results = await gather_with_timeout(
            fetch_twitch_data(user_id),
            fetch_vk_data(user_id),
            timeout=10.0
        )
    """
    try:
        return await asyncio.wait_for(
            asyncio.gather(*coroutines, return_exceptions=return_exceptions),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"gather_with_timeout exceeded {timeout}s timeout")
        if return_exceptions:
            return [TimeoutError(f"Operation timed out after {timeout}s")] * len(coroutines)
        raise


async def fetch_multiple_urls(
    urls: List[str],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0
) -> List[Dict[str, Any]]:
    """
    Fetch multiple URLs in parallel
    
    [OK] OPTIMIZED: Parallel HTTP requests
    
    Args:
        urls: List of URLs to fetch
        headers: Optional headers for all requests
        timeout: Timeout per request in seconds
        
    Returns:
        List of response data (or error dicts)
        
    Example:
        results = await fetch_multiple_urls([
            "https://api.twitch.tv/helix/users",
            "https://api.vk.com/method/users.get"
        ])
    """
    async def fetch_one(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                return {
                    "url": url,
                    "status": response.status,
                    "data": await response.json() if response.status == 200 else None,
                    "error": None
                }
        except asyncio.TimeoutError:
            return {"url": url, "status": 408, "data": None, "error": "Request timeout"}
        except Exception as e:
            return {"url": url, "status": 500, "data": None, "error": "Internal server error"}

    session_timeout = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 10.0))
    async with aiohttp.ClientSession(timeout=session_timeout) as session:
        tasks = [fetch_one(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)


async def parallel_api_calls(
    *api_calls: Callable[[], Coroutine[Any, Any, T]],
    timeout: float = 30.0
) -> List[Optional[T]]:
    """
    Execute multiple API calls in parallel
    
    [OK] OPTIMIZED: Reduces total API call time
    
    Args:
        *api_calls: Async functions to call
        timeout: Total timeout for all calls
        
    Returns:
        List of results (None for failed calls)
        
    Example:
        twitch_data, vk_data = await parallel_api_calls(
            lambda: twitch_api.get_user(user_id),
            lambda: vk_api.get_user(user_id),
            timeout=10.0
        )
    """
    tasks = [call() for call in api_calls]
    results = await gather_with_timeout(*tasks, timeout=timeout, return_exceptions=True)

    # Convert exceptions to None
    return [
        result if not isinstance(result, Exception) else None
        for result in results
    ]


def async_timeout(seconds: float):
    """
    Decorator to add timeout to async functions
    
    [OK] OPTIMIZED: Prevents hanging operations
    
    Args:
        seconds: Timeout in seconds
        
    Example:
        @async_timeout(10.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} timed out after {seconds}s")
                raise TimeoutError(f"{func.__name__} exceeded {seconds}s timeout")
        return wrapper
    return decorator


async def retry_async(
    func: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Optional[T]:
    """
    Retry async function with exponential backoff
    
    [OK] OPTIMIZED: Handles transient failures
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Result or None if all retries failed
        
    Example:
        result = await retry_async(
            lambda: api.get_data(),
            max_retries=3,
            delay=1.0
        )
    """
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(f"All {max_retries + 1} attempts failed: {e}")

    return None


class AsyncBatchProcessor:
    """
    Process items in batches asynchronously
    
    [OK] OPTIMIZED: Batch processing for better throughput
    
    Example:
        processor = AsyncBatchProcessor(batch_size=10, max_concurrent=3)
        results = await processor.process(items, process_item_async)
    """

    def __init__(self, batch_size: int = 10, max_concurrent: int = 5):
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(
        self,
        batch: List[Any],
        processor: Callable[[Any], Coroutine[Any, Any, T]]
    ) -> List[T]:
        """Process a single batch"""
        async with self.semaphore:
            tasks = [processor(item) for item in batch]
            return await asyncio.gather(*tasks, return_exceptions=True)

    async def process(
        self,
        items: List[Any],
        processor: Callable[[Any], Coroutine[Any, Any, T]]
    ) -> List[T]:
        """Process all items in batches"""
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]

        results = []
        for batch in batches:
            batch_results = await self.process_batch(batch, processor)
            results.extend(batch_results)

        return results


# Configuration for async operations
class AsyncConfig:
    """Configuration for async operations"""

    # Timeouts
    DEFAULT_TIMEOUT = 30.0  # seconds
    CONNECT_TIMEOUT = 10.0  # seconds
    REQUEST_TIMEOUT = 30.0  # seconds

    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    RETRY_BACKOFF = 2.0

    # Batch processing
    BATCH_SIZE = 10
    MAX_CONCURRENT_BATCHES = 5

    # Connection pooling
    MAX_CONNECTIONS = 100
    MAX_CONNECTIONS_PER_HOST = 30


# Example usage patterns
"""
PARALLEL API CALLS:

# Bad (sequential - 6 seconds total):
twitch_data = await fetch_twitch_data(user_id)  # 2s
vk_data = await fetch_vk_data(user_id)          # 2s
da_data = await fetch_da_data(user_id)          # 2s

# Good (parallel - 2 seconds total):
twitch_data, vk_data, da_data = await parallel_api_calls(
    lambda: fetch_twitch_data(user_id),
    lambda: fetch_vk_data(user_id),
    lambda: fetch_da_data(user_id),
    timeout=10.0
)

BATCH PROCESSING:

# Bad (sequential):
results = []
for user in users:
    result = await process_user(user)
    results.append(result)

# Good (batched):
processor = AsyncBatchProcessor(batch_size=10, max_concurrent=3)
results = await processor.process(users, process_user)

TIMEOUT HANDLING:

# Bad (no timeout):
@app.get("/data")
async def get_data():
    return await fetch_external_api()  # Could hang forever

# Good (with timeout):
@app.get("/data")
@async_timeout(10.0)
async def get_data():
    return await fetch_external_api()  # Max 10 seconds

RETRY LOGIC:

# Bad (no retry):
data = await unreliable_api_call()

# Good (with retry):
data = await retry_async(
    lambda: unreliable_api_call(),
    max_retries=3,
    delay=1.0
)
"""
