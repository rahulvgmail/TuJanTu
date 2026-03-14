"""Flood detection for high-frequency technical event webhooks."""

from __future__ import annotations

import time
from typing import Callable


class FloodDetector:
    """Simple sliding-window rate limiter for incoming events.

    Keeps a list of monotonic timestamps and checks whether the event
    count within the active window exceeds the configured threshold.

    Args:
        threshold: Maximum number of events allowed within the window
            before flooding is declared.
        window_minutes: Duration of the sliding window in minutes.
        clock: Callable returning a monotonic timestamp (defaults to
            ``time.monotonic``). Injectable for deterministic testing.
    """

    def __init__(
        self,
        threshold: int = 50,
        window_minutes: int = 5,
        clock: Callable[[], float] | None = None,
    ):
        self.threshold = threshold
        self.window_minutes = window_minutes
        self._clock = clock or time.monotonic
        self._timestamps: list[float] = []

    def _prune(self) -> None:
        """Remove timestamps that have fallen outside the active window."""
        cutoff = self._clock() - (self.window_minutes * 60)
        # Find first index that is still within the window.
        first_valid = 0
        for i, ts in enumerate(self._timestamps):
            if ts >= cutoff:
                first_valid = i
                break
        else:
            # All timestamps are expired (or list is empty).
            self._timestamps.clear()
            return
        if first_valid > 0:
            self._timestamps = self._timestamps[first_valid:]

    def record_event(self) -> None:
        """Record an incoming event timestamp."""
        self._prune()
        self._timestamps.append(self._clock())

    def is_flooding(self) -> bool:
        """Return True if event rate exceeds threshold within window."""
        self._prune()
        return len(self._timestamps) >= self.threshold

    def event_count_in_window(self) -> int:
        """Return current event count within the active window."""
        self._prune()
        return len(self._timestamps)
