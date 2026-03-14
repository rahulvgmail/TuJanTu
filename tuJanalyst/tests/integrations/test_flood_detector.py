"""Tests for FloodDetector — sliding-window rate limiter for incoming events."""

from __future__ import annotations

from src.integrations.flood_detector import FloodDetector


# ---------------------------------------------------------------------------
# 1. test_not_flooding_under_threshold
# ---------------------------------------------------------------------------


def test_not_flooding_under_threshold():
    """Recording fewer events than threshold keeps is_flooding() False."""
    detector = FloodDetector(threshold=5, window_minutes=1)
    for _ in range(4):
        detector.record_event()
    assert detector.is_flooding() is False


# ---------------------------------------------------------------------------
# 2. test_flooding_at_threshold
# ---------------------------------------------------------------------------


def test_flooding_at_threshold():
    """Recording exactly threshold events trips is_flooding() to True."""
    detector = FloodDetector(threshold=5, window_minutes=1)
    for _ in range(5):
        detector.record_event()
    assert detector.is_flooding() is True


# ---------------------------------------------------------------------------
# 3. test_events_expire_after_window
# ---------------------------------------------------------------------------


def test_events_expire_after_window():
    """Events older than the window are pruned, bringing is_flooding() back to False."""
    fake_time = 0.0

    def clock() -> float:
        return fake_time

    detector = FloodDetector(threshold=3, window_minutes=1, clock=clock)

    # Record 3 events at t=0 — should be flooding.
    for _ in range(3):
        detector.record_event()
    assert detector.is_flooding() is True

    # Advance past the 1-minute window.
    fake_time = 61.0
    assert detector.is_flooding() is False


# ---------------------------------------------------------------------------
# 4. test_event_count_in_window
# ---------------------------------------------------------------------------


def test_event_count_in_window():
    """event_count_in_window accurately reflects mixed recording and expiry."""
    fake_time = 0.0

    def clock() -> float:
        return fake_time

    detector = FloodDetector(threshold=10, window_minutes=2, clock=clock)

    # Record 3 events at t=0.
    for _ in range(3):
        detector.record_event()
    assert detector.event_count_in_window() == 3

    # Advance to t=60 and record 2 more (all 5 within the 2-min window).
    fake_time = 60.0
    for _ in range(2):
        detector.record_event()
    assert detector.event_count_in_window() == 5

    # Advance to t=121 — the first 3 events (at t=0) expire.
    fake_time = 121.0
    assert detector.event_count_in_window() == 2
