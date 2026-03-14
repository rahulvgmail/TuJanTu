"""Tests for StockPulseDataTool — higher-level tool producing TechnicalContext."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.agents.tools.stockpulse_data import StockPulseDataTool
from src.models.technical_context import TechnicalContext


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_INDICATORS: dict = {
    "current_price": 550.25,
    "prev_close": 533.0,
    "pct_change": 3.2,
    "dma_10": 540.0,
    "dma_10_touch": True,
    "dma_10_signal": "Hold",
    "dma_20": 525.0,
    "dma_20_touch": False,
    "dma_20_signal": None,
    "is_52w_closing_high": True,
    "is_52w_high_intraday": False,
    "high_52w": 550.25,
    "is_volume_breakout": True,
    "today_volume": 2100000,
    "max_vol_21d": 1800000,
    "gap_pct": 4.5,
    "is_gap_up": True,
    "is_gap_down": False,
    "is_90d_high": True,
    "is_90d_low_touch": False,
    "days_to_result": None,
    "result_declared_10d": True,
}

SAMPLE_EVENTS: list[dict] = [
    {"event_type": "EARNINGS", "payload": {"quarter": "Q3"}, "created_at": "2026-01-15"},
    {"event_type": "BREAKOUT", "payload": {"level": 540}, "created_at": "2026-01-14"},
]

SAMPLE_STOCK: dict = {
    "id": 1,
    "symbol": "TESTCO",
    "company_name": "Test Company Ltd",
    "color": "Green",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    indicators_return=SAMPLE_INDICATORS,
    events_return=SAMPLE_EVENTS,
    stock_return=SAMPLE_STOCK,
    *,
    events_side_effect=None,
    stock_side_effect=None,
) -> StockPulseDataTool:
    """Build a StockPulseDataTool with a fully mocked client."""
    client = MagicMock()
    client.get_indicators = AsyncMock(return_value=indicators_return)

    if events_side_effect is not None:
        client.get_events = AsyncMock(side_effect=events_side_effect)
    else:
        client.get_events = AsyncMock(return_value=events_return)

    if stock_side_effect is not None:
        client.get_stock = AsyncMock(side_effect=stock_side_effect)
    else:
        client.get_stock = AsyncMock(return_value=stock_return)

    return StockPulseDataTool(client=client)


# ---------------------------------------------------------------------------
# 1. test_get_technical_context_success
# ---------------------------------------------------------------------------


async def test_get_technical_context_success():
    tool = _make_tool()
    ctx = await tool.get_technical_context("TESTCO")

    assert ctx is not None
    assert isinstance(ctx, TechnicalContext)

    # Price
    assert ctx.current_price == 550.25
    assert ctx.pct_change == 3.2

    # DMA signals — flat keys: dma_10_signal="Hold", dma_20_signal=None
    assert ctx.dma_signals["10"] == "Hold"
    assert ctx.dma_signals["20"] is None

    # 52W flags
    assert ctx.is_52w_closing_high is True
    assert ctx.is_52w_high_intraday is False
    assert ctx.high_52w == 550.25

    # Volume
    assert ctx.is_volume_breakout is True
    assert ctx.today_volume == 2100000
    assert ctx.max_vol_21d == 1800000

    # Events
    assert len(ctx.recent_events) == 2
    assert ctx.recent_events[0]["event_type"] == "EARNINGS"
    assert ctx.recent_events[1]["event_type"] == "BREAKOUT"

    # Color
    assert ctx.color == "Green"


# ---------------------------------------------------------------------------
# 2. test_get_technical_context_indicators_unavailable
# ---------------------------------------------------------------------------


async def test_get_technical_context_indicators_unavailable():
    tool = _make_tool(indicators_return=None)
    ctx = await tool.get_technical_context("MISSING")

    assert ctx is None


# ---------------------------------------------------------------------------
# 3. test_get_technical_context_partial_failure
# ---------------------------------------------------------------------------


async def test_get_technical_context_partial_failure():
    """get_events raises an exception; context should still be returned with empty events."""
    tool = _make_tool(events_side_effect=RuntimeError("events service down"))
    ctx = await tool.get_technical_context("TESTCO")

    assert ctx is not None
    assert isinstance(ctx, TechnicalContext)
    assert ctx.current_price == 550.25
    assert ctx.recent_events == []


# ---------------------------------------------------------------------------
# 4. test_get_technical_context_stock_unavailable
# ---------------------------------------------------------------------------


async def test_get_technical_context_stock_unavailable():
    """get_stock returns None; context should still be returned without color."""
    tool = _make_tool(stock_return=None)
    ctx = await tool.get_technical_context("TESTCO")

    assert ctx is not None
    assert isinstance(ctx, TechnicalContext)
    assert ctx.color is None
    assert ctx.current_price == 550.25


# ---------------------------------------------------------------------------
# 5. test_to_prompt_text_formatting
# ---------------------------------------------------------------------------


async def test_to_prompt_text_formatting():
    ctx = TechnicalContext(
        symbol="TESTCO",
        current_price=550.25,
        pct_change=3.2,
        dma_signals={"10": "Hold", "20": None, "50": "Buy"},
        is_52w_closing_high=True,
        high_52w=550.25,
        is_volume_breakout=True,
        today_volume=2100000,
        max_vol_21d=1800000,
        is_gap_up=True,
        gap_pct=4.5,
        is_90d_high=True,
        result_declared_10d=True,
        color="Green",
        screener_names=["Momentum", "Volume Leaders"],
        recent_events=[
            {"event_type": "EARNINGS", "payload": {}, "created_at": "2026-01-15"},
        ],
    )

    text = ctx.to_prompt_text()

    assert "Technical State (TESTCO):" in text
    assert "550.25" in text
    assert "+3.2%" in text
    assert "DMA-10: Hold" in text
    assert "DMA-50: Buy" in text
    assert "52W High: YES (closing high)" in text
    assert "Volume: BREAKOUT" in text
    assert "2.1M" in text
    assert "1.8M" in text
    assert "+4.5% gap-up" in text
    assert "90D: At 90-day high" in text
    assert "Result: declared within last 10 days" in text
    assert "Color: Green (Watchlist)" in text
    assert "Screeners (2): Momentum, Volume Leaders" in text
    assert "Recent Events: EARNINGS" in text


# ---------------------------------------------------------------------------
# 6. test_to_prompt_text_empty
# ---------------------------------------------------------------------------


async def test_to_prompt_text_empty():
    ctx = TechnicalContext(symbol="EMPTY")

    text = ctx.to_prompt_text()

    assert "Technical State (EMPTY):" in text
    assert "No technical data available" in text
