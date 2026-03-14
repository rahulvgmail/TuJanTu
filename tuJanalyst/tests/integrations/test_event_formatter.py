"""Tests for format_technical_event — human-readable formatting of StockPulse events."""

from __future__ import annotations

from src.integrations.event_formatter import format_technical_event


# ---------------------------------------------------------------------------
# 1. test_format_52w_closing_high
# ---------------------------------------------------------------------------


def test_format_52w_closing_high():
    result = format_technical_event(
        "52W_CLOSING_HIGH",
        {"symbol": "INFY", "price": 1800.0, "prev": 1790.0},
    )
    assert "INFY" in result
    assert "1800" in result


# ---------------------------------------------------------------------------
# 2. test_format_volume_breakout
# ---------------------------------------------------------------------------


def test_format_volume_breakout():
    result = format_technical_event(
        "VOLUME_BREAKOUT",
        {"symbol": "RELIANCE", "volume": 5_000_000, "max_vol_21d": 3_000_000},
    )
    assert "RELIANCE" in result
    assert "5000000" in result
    assert "3000000" in result


# ---------------------------------------------------------------------------
# 3. test_format_dma_crossover
# ---------------------------------------------------------------------------


def test_format_dma_crossover():
    result = format_technical_event(
        "DMA_CROSSOVER",
        {"symbol": "TCS", "period": 50, "signal": "bullish", "price": 3500.0, "dma_value": 3450.0},
    )
    assert "TCS" in result
    assert "50" in result
    assert "bullish" in result


# ---------------------------------------------------------------------------
# 4. test_format_gap_up
# ---------------------------------------------------------------------------


def test_format_gap_up():
    result = format_technical_event(
        "GAP_UP",
        {"symbol": "HDFC", "gap_pct": 3.2, "open": 1550.0, "prev_close": 1502.0},
    )
    assert "HDFC" in result
    assert "3.2" in result


# ---------------------------------------------------------------------------
# 5. test_format_unknown_event
# ---------------------------------------------------------------------------


def test_format_unknown_event():
    result = format_technical_event(
        "SOME_FUTURE_EVENT",
        {"symbol": "WIPRO", "foo": "bar"},
    )
    assert "WIPRO" in result
    assert "SOME_FUTURE_EVENT" in result


# ---------------------------------------------------------------------------
# 6. test_format_missing_payload_keys
# ---------------------------------------------------------------------------


def test_format_missing_payload_keys():
    """Incomplete payload should fall back to the default format."""
    result = format_technical_event(
        "52W_CLOSING_HIGH",
        {"symbol": "INFY"},  # missing 'price' and 'prev'
    )
    # Should not raise — falls through to the default format.
    assert "INFY" in result
    assert "52W_CLOSING_HIGH" in result
