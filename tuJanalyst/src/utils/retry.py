"""Retry helpers for transient upstream failures."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

T = TypeVar("T")

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def is_transient_error(error: Exception) -> bool:
    """Return True when an exception likely represents a retriable transient error."""
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return True

    status_code: int | None = None
    if httpx is not None:
        if isinstance(error, httpx.TimeoutException):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code

    if status_code in TRANSIENT_STATUS_CODES:
        return True

    message = str(error).lower()
    transient_tokens = ("timeout", "temporarily", "rate limit", "429", "503", "502", "504", "500")
    return any(token in message for token in transient_tokens)


def retry_sync(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
    should_retry: Callable[[Exception], bool] = is_transient_error,
) -> T:
    """Retry a synchronous operation with exponential backoff."""
    if attempts <= 0:
        raise ValueError("attempts must be > 0")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:  # noqa: BLE001
            if attempt >= attempts or not should_retry(error):
                raise
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError("retry_sync exhausted unexpectedly")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
    should_retry: Callable[[Exception], bool] = is_transient_error,
) -> T:
    """Retry an async operation with exponential backoff."""
    if attempts <= 0:
        raise ValueError("attempts must be > 0")

    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as error:  # noqa: BLE001
            if attempt >= attempts or not should_retry(error):
                raise
            await asyncio.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError("retry_async exhausted unexpectedly")


async def retry_in_thread(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
    should_retry: Callable[[Exception], bool] = is_transient_error,
) -> T:
    """Retry a synchronous operation in a worker thread without blocking the event loop."""
    return await retry_async(
        lambda: asyncio.to_thread(operation),
        attempts=attempts,
        base_delay_seconds=base_delay_seconds,
        should_retry=should_retry,
    )
