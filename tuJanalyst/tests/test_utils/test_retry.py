"""Tests for retry helpers."""

from __future__ import annotations

import pytest

from src.utils.retry import is_transient_error, retry_async, retry_in_thread, retry_sync


def test_retry_sync_retries_transient_error_until_success() -> None:
    state = {"calls": 0}

    def operation() -> str:
        state["calls"] += 1
        if state["calls"] < 3:
            raise TimeoutError("temporary timeout")
        return "ok"

    result = retry_sync(operation, attempts=3, base_delay_seconds=0)

    assert result == "ok"
    assert state["calls"] == 3


def test_retry_sync_stops_on_non_transient_error() -> None:
    state = {"calls": 0}

    def operation() -> str:
        state["calls"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        retry_sync(operation, attempts=3, base_delay_seconds=0)

    assert state["calls"] == 1


@pytest.mark.asyncio
async def test_retry_async_retries_transient_error_until_success() -> None:
    state = {"calls": 0}

    async def operation() -> str:
        state["calls"] += 1
        if state["calls"] < 3:
            raise TimeoutError("temporary timeout")
        return "ok"

    result = await retry_async(operation, attempts=3, base_delay_seconds=0)

    assert result == "ok"
    assert state["calls"] == 3


@pytest.mark.asyncio
async def test_retry_in_thread_retries_transient_error_until_success() -> None:
    state = {"calls": 0}

    def operation() -> str:
        state["calls"] += 1
        if state["calls"] < 3:
            raise TimeoutError("temporary timeout")
        return "ok"

    result = await retry_in_thread(operation, attempts=3, base_delay_seconds=0)

    assert result == "ok"
    assert state["calls"] == 3


def test_is_transient_error_detects_timeout() -> None:
    assert is_transient_error(TimeoutError("timeout"))
