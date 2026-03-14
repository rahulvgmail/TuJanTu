"""Format StockPulse technical events into human-readable trigger content."""

from __future__ import annotations

from typing import Callable


def format_technical_event(event_type: str, payload: dict, symbol: str | None = None) -> str:
    """Produce human-readable text from a StockPulse technical event.

    Args:
        event_type: The technical event type (e.g. ``52W_CLOSING_HIGH``).
        payload: Event payload dictionary with event-specific fields.
        symbol: Optional stock symbol for context.

    Returns:
        A concise, human-readable description of the event.
    """
    sym = symbol or payload.get("symbol", "Unknown")
    formatter = _FORMATTERS.get(event_type)
    if formatter is not None:
        try:
            return formatter(sym, payload)
        except (KeyError, TypeError, ValueError):
            # Fall through to default if payload is missing expected keys.
            pass
    return f"{sym} technical event: {event_type}"


# ---------------------------------------------------------------------------
# Per-event-type formatters
# ---------------------------------------------------------------------------

def _fmt_52w_closing_high(sym: str, p: dict) -> str:
    price = p["price"]
    prev = p["prev"]
    return f"{sym} hit 52-week closing high at \u20b9{price} (previous: \u20b9{prev})"


def _fmt_52w_closing_low(sym: str, p: dict) -> str:
    price = p["price"]
    prev = p["prev"]
    return f"{sym} hit 52-week closing low at \u20b9{price} (previous: \u20b9{prev})"


def _fmt_volume_breakout(sym: str, p: dict) -> str:
    volume = p["volume"]
    max_vol_21d = p["max_vol_21d"]
    return f"{sym} volume breakout: {volume} vs 21d-max {max_vol_21d}"


def _fmt_dma_crossover(sym: str, p: dict) -> str:
    period = p["period"]
    signal = p["signal"]
    price = p["price"]
    dma_value = p["dma_value"]
    return f"{sym} DMA-{period} {signal} signal at \u20b9{price} (DMA: \u20b9{dma_value})"


def _fmt_gap_up(sym: str, p: dict) -> str:
    gap_pct = p["gap_pct"]
    open_price = p["open"]
    prev_close = p["prev_close"]
    return f"{sym} gapped up {gap_pct}% (open: \u20b9{open_price}, prev close: \u20b9{prev_close})"


def _fmt_gap_down(sym: str, p: dict) -> str:
    gap_pct = p["gap_pct"]
    open_price = p["open"]
    prev_close = p["prev_close"]
    return f"{sym} gapped down {gap_pct}% (open: \u20b9{open_price}, prev close: \u20b9{prev_close})"


_FORMATTERS: dict[str, Callable[[str, dict], str]] = {
    "52W_CLOSING_HIGH": _fmt_52w_closing_high,
    "52W_CLOSING_LOW": _fmt_52w_closing_low,
    "VOLUME_BREAKOUT": _fmt_volume_breakout,
    "DMA_CROSSOVER": _fmt_dma_crossover,
    "GAP_UP": _fmt_gap_up,
    "GAP_DOWN": _fmt_gap_down,
}
