"""Simple in-memory circuit breaker for transient upstream outages."""

from __future__ import annotations

import time
from typing import Callable


class CircuitBreaker:
    """Track consecutive failures and temporarily open after threshold breaches."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 120.0,
        time_fn: Callable[[], float] | None = None,
    ):
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be > 0")
        if recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be > 0")

        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._time_fn = time_fn or time.monotonic
        self._consecutive_failures = 0
        self._opened_until: float | None = None

    def is_open(self) -> bool:
        """Return True when the breaker is currently open."""
        opened_until = self._opened_until
        if opened_until is None:
            return False

        now = self._time_fn()
        if now >= opened_until:
            self._opened_until = None
            self._consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        """Reset breaker state after a successful upstream call."""
        self._consecutive_failures = 0
        self._opened_until = None

    def record_failure(self) -> None:
        """Record failed upstream call and open breaker if threshold is reached."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_until = self._time_fn() + self.recovery_seconds

    def seconds_until_close(self) -> float:
        """Return seconds remaining before the breaker closes."""
        if self._opened_until is None:
            return 0.0
        remaining = self._opened_until - self._time_fn()
        return remaining if remaining > 0 else 0.0
