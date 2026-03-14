"""Tests for SectorPulseTool and SectorPulse model."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.tools.sector_pulse import SectorPulseTool
from src.models.sector_pulse import SectorPulse


# ---------------------------------------------------------------------------
# Fake StockPulseClient
# ---------------------------------------------------------------------------


class FakeStockPulseClient:
    """In-memory fake that replaces the real HTTP client for unit tests."""

    def __init__(
        self,
        stocks_by_sector: dict[str, list[dict[str, Any]]] | None = None,
        indicators_by_symbol: dict[str, dict[str, Any] | None] | None = None,
        indicators_error_symbols: set[str] | None = None,
    ):
        self._stocks_by_sector = stocks_by_sector or {}
        self._indicators_by_symbol = indicators_by_symbol or {}
        self._indicators_error_symbols = indicators_error_symbols or set()

    async def get_stocks_by_sector(self, sector: str) -> list[dict[str, Any]]:
        return self._stocks_by_sector.get(sector, [])

    async def get_indicators(self, symbol: str, period: str = "1d") -> dict[str, Any] | None:
        if symbol in self._indicators_error_symbols:
            raise RuntimeError(f"Simulated failure for {symbol}")
        return self._indicators_by_symbol.get(symbol)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IT_STOCKS = [
    {"symbol": "INFY", "name": "Infosys"},
    {"symbol": "TCS", "name": "Tata Consultancy"},
    {"symbol": "WIPRO", "name": "Wipro"},
]

_INDICATORS: dict[str, dict[str, Any]] = {
    "INFY": {
        "is_52w_high_intraday": True,
        "is_52w_closing_high": False,
        "is_volume_breakout": True,
        "is_gap_up": False,
        "pct_change": 3.5,
        "current_price": 1500.0,
        "dma_10_signal": "hold",
        "dma_20_signal": "reverse",
    },
    "TCS": {
        "is_52w_high_intraday": False,
        "is_52w_closing_high": True,
        "is_volume_breakout": False,
        "is_gap_up": True,
        "pct_change": -1.2,
        "current_price": 3400.0,
        "dma_10_signal": "reverse",
        "dma_20_signal": "hold",
    },
    "WIPRO": {
        "is_52w_high_intraday": False,
        "is_52w_closing_high": False,
        "is_volume_breakout": False,
        "is_gap_up": False,
        "pct_change": 0.8,
        "current_price": 450.0,
        "dma_10_signal": "hold",
        "dma_20_signal": "hold",
    },
}


def _build_tool(
    stocks_by_sector: dict[str, list[dict[str, Any]]] | None = None,
    indicators_by_symbol: dict[str, dict[str, Any] | None] | None = None,
    indicators_error_symbols: set[str] | None = None,
) -> SectorPulseTool:
    client = FakeStockPulseClient(
        stocks_by_sector=stocks_by_sector,
        indicators_by_symbol=indicators_by_symbol,
        indicators_error_symbols=indicators_error_symbols,
    )
    return SectorPulseTool(client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. get_sector_pulse — happy path
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_aggregates_correctly():
    tool = _build_tool(
        stocks_by_sector={"IT": _IT_STOCKS},
        indicators_by_symbol=_INDICATORS,
    )
    result = await tool.get_sector_pulse("IT")

    assert result is not None
    assert result.sector == "IT"
    assert result.stock_count == 3

    # 52W high: INFY (intraday) + TCS (closing) = 2
    assert result.stocks_at_52w_high == 2

    # Volume breakout: INFY only
    assert result.stocks_with_volume_breakout == 1

    # Gap up: TCS only
    assert result.stocks_with_gap_up == 1

    # Avg pct change: (3.5 + (-1.2) + 0.8) / 3 = 1.03 (rounded to 2dp)
    assert result.avg_pct_change == pytest.approx(1.03, abs=0.01)

    # DMA-10: INFY hold, TCS reverse, WIPRO hold => 2 hold, 1 reverse
    assert result.dma_10_hold_count == 2
    assert result.dma_10_reverse_count == 1

    # DMA-20: INFY reverse, TCS hold, WIPRO hold => 2 hold, 1 reverse
    assert result.dma_20_hold_count == 2
    assert result.dma_20_reverse_count == 1

    # Top gainers: sorted by pct_change desc => INFY (3.5), WIPRO (0.8), TCS (-1.2)
    assert len(result.top_gainers) == 3
    assert result.top_gainers[0]["symbol"] == "INFY"
    assert result.top_gainers[1]["symbol"] == "WIPRO"

    # Top losers: only stocks with negative pct_change => TCS (-1.2)
    assert len(result.top_losers) == 1
    assert result.top_losers[0]["symbol"] == "TCS"
    assert result.top_losers[0]["pct_change"] == -1.2

    assert result.data_timestamp is not None


# ---------------------------------------------------------------------------
# 2. get_sector_pulse — empty sector returns None
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_empty_sector_returns_none():
    tool = _build_tool(stocks_by_sector={})
    result = await tool.get_sector_pulse("NonExistent")
    assert result is None


# ---------------------------------------------------------------------------
# 3. get_sector_pulse — stocks with no indicators (None returned)
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_stocks_with_no_indicators():
    """When get_indicators returns None for every stock, counts should all be zero."""
    stocks = [{"symbol": "AAA"}, {"symbol": "BBB"}]
    tool = _build_tool(
        stocks_by_sector={"Pharma": stocks},
        indicators_by_symbol={"AAA": None, "BBB": None},
    )
    result = await tool.get_sector_pulse("Pharma")

    assert result is not None
    assert result.stock_count == 2
    assert result.stocks_at_52w_high == 0
    assert result.stocks_with_volume_breakout == 0
    assert result.stocks_with_gap_up == 0
    assert result.avg_pct_change is None
    assert result.dma_10_hold_count == 0
    assert result.dma_10_reverse_count == 0
    assert result.dma_20_hold_count == 0
    assert result.dma_20_reverse_count == 0
    assert result.top_gainers == []
    assert result.top_losers == []


# ---------------------------------------------------------------------------
# 4. get_sector_pulse — indicator fetch raises exception
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_handles_indicator_exceptions():
    """Stocks whose indicator fetch raises an exception are treated as None."""
    stocks = [{"symbol": "GOOD"}, {"symbol": "BAD"}]
    tool = _build_tool(
        stocks_by_sector={"Mixed": stocks},
        indicators_by_symbol={
            "GOOD": {
                "pct_change": 2.0,
                "current_price": 100.0,
                "dma_10_signal": "hold",
                "dma_20_signal": "hold",
            },
        },
        indicators_error_symbols={"BAD"},
    )
    result = await tool.get_sector_pulse("Mixed")

    assert result is not None
    assert result.stock_count == 2
    # Only GOOD has indicators
    assert result.avg_pct_change == 2.0
    assert result.dma_10_hold_count == 1


# ---------------------------------------------------------------------------
# 5. get_sector_pulse — nested DMA format (dma_{period}.signal)
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_nested_dma_format():
    stocks = [{"symbol": "NESTED"}]
    tool = _build_tool(
        stocks_by_sector={"Bank": stocks},
        indicators_by_symbol={
            "NESTED": {
                "pct_change": 1.0,
                "current_price": 500.0,
                "dma_10": {"signal": "hold", "value": 490.0},
                "dma_20": {"signal": "reversal", "value": 480.0},
            },
        },
    )
    result = await tool.get_sector_pulse("Bank")

    assert result is not None
    assert result.dma_10_hold_count == 1
    assert result.dma_10_reverse_count == 0
    # "reversal" should map to reverse
    assert result.dma_20_hold_count == 0
    assert result.dma_20_reverse_count == 1


# ---------------------------------------------------------------------------
# 6. get_sector_pulse — batching with > 20 stocks
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_batches_large_sector():
    """Ensure more than _BATCH_SIZE (20) stocks are handled correctly."""
    count = 25
    stocks = [{"symbol": f"S{i:03d}"} for i in range(count)]
    indicators = {
        f"S{i:03d}": {
            "pct_change": float(i),
            "current_price": 100.0 + i,
        }
        for i in range(count)
    }
    tool = _build_tool(
        stocks_by_sector={"Large": stocks},
        indicators_by_symbol=indicators,
    )
    result = await tool.get_sector_pulse("Large")

    assert result is not None
    assert result.stock_count == 25
    # avg pct_change = sum(0..24)/25 = 300/25 = 12.0
    assert result.avg_pct_change == 12.0
    # Top 5 gainers should be S024, S023, S022, S021, S020
    assert len(result.top_gainers) == 5
    assert result.top_gainers[0]["symbol"] == "S024"
    # No losers since all pct_change >= 0
    assert result.top_losers == []


# ---------------------------------------------------------------------------
# 7. get_sector_pulse — top losers limited to negative pct_change
# ---------------------------------------------------------------------------


async def test_top_losers_only_negative():
    """All-positive sector should have zero losers."""
    stocks = [{"symbol": "UP1"}, {"symbol": "UP2"}]
    tool = _build_tool(
        stocks_by_sector={"Bull": stocks},
        indicators_by_symbol={
            "UP1": {"pct_change": 5.0, "current_price": 200.0},
            "UP2": {"pct_change": 0.0, "current_price": 150.0},
        },
    )
    result = await tool.get_sector_pulse("Bull")

    assert result is not None
    assert result.top_losers == []


# ---------------------------------------------------------------------------
# 8. _extract_dma_signal — flat key format
# ---------------------------------------------------------------------------


def test_extract_dma_signal_flat_key():
    ind = {"dma_10_signal": "hold", "dma_20_signal": "reverse"}
    assert SectorPulseTool._extract_dma_signal(ind, "10") == "hold"
    assert SectorPulseTool._extract_dma_signal(ind, "20") == "reverse"


# ---------------------------------------------------------------------------
# 9. _extract_dma_signal — nested dict format
# ---------------------------------------------------------------------------


def test_extract_dma_signal_nested_dict():
    ind = {
        "dma_10": {"signal": "reversal", "value": 100.0},
        "dma_20": {"signal": "hold", "value": 200.0},
    }
    assert SectorPulseTool._extract_dma_signal(ind, "10") == "reversal"
    assert SectorPulseTool._extract_dma_signal(ind, "20") == "hold"


# ---------------------------------------------------------------------------
# 10. _extract_dma_signal — missing key returns None
# ---------------------------------------------------------------------------


def test_extract_dma_signal_missing_returns_none():
    ind = {"some_other_key": 42}
    assert SectorPulseTool._extract_dma_signal(ind, "10") is None
    assert SectorPulseTool._extract_dma_signal(ind, "20") is None


# ---------------------------------------------------------------------------
# 11. _extract_dma_signal — flat key takes precedence over nested
# ---------------------------------------------------------------------------


def test_extract_dma_signal_flat_takes_precedence():
    ind = {
        "dma_10_signal": "hold",
        "dma_10": {"signal": "reverse"},
    }
    assert SectorPulseTool._extract_dma_signal(ind, "10") == "hold"


# ---------------------------------------------------------------------------
# 12. SectorPulse.to_prompt_text — basic format
# ---------------------------------------------------------------------------


def test_to_prompt_text_basic():
    pulse = SectorPulse(
        sector="IT",
        stock_count=3,
        stocks_at_52w_high=2,
        stocks_with_volume_breakout=1,
        stocks_with_gap_up=1,
        avg_pct_change=1.03,
        dma_10_hold_count=2,
        dma_10_reverse_count=1,
        dma_20_hold_count=2,
        dma_20_reverse_count=1,
        top_gainers=[
            {"symbol": "INFY", "pct_change": 3.5, "price": 1500.0},
            {"symbol": "WIPRO", "pct_change": 0.8, "price": 450.0},
        ],
        top_losers=[
            {"symbol": "TCS", "pct_change": -1.2, "price": 3400.0},
        ],
    )
    text = pulse.to_prompt_text()

    assert "Sector Pulse (IT):" in text
    assert "Stocks: 3" in text
    assert "At 52W High: 2" in text
    assert "Volume Breakout: 1" in text
    assert "Avg Change: +1.0%" in text
    assert "DMA-10: 2 Hold, 1 Reverse" in text
    assert "DMA-20: 2 Hold, 1 Reverse" in text
    assert "Gap-Ups: 1" in text
    assert "INFY (+3.5%)" in text
    assert "WIPRO (+0.8%)" in text
    assert "TCS (-1.2%)" in text
    assert "Top Gainers:" in text
    assert "Top Losers:" in text


# ---------------------------------------------------------------------------
# 13. SectorPulse.to_prompt_text — negative avg change
# ---------------------------------------------------------------------------


def test_to_prompt_text_negative_avg_change():
    pulse = SectorPulse(
        sector="Pharma",
        stock_count=5,
        avg_pct_change=-2.5,
    )
    text = pulse.to_prompt_text()

    assert "Avg Change: -2.5%" in text
    # No sign prefix for negative
    assert "+-" not in text


# ---------------------------------------------------------------------------
# 14. SectorPulse.to_prompt_text — avg change None shows N/A
# ---------------------------------------------------------------------------


def test_to_prompt_text_avg_change_none():
    pulse = SectorPulse(
        sector="Energy",
        stock_count=2,
        avg_pct_change=None,
    )
    text = pulse.to_prompt_text()
    assert "Avg Change: N/A" in text


# ---------------------------------------------------------------------------
# 15. SectorPulse.to_prompt_text — no gap-ups line when zero
# ---------------------------------------------------------------------------


def test_to_prompt_text_no_gap_ups_when_zero():
    pulse = SectorPulse(
        sector="Auto",
        stock_count=10,
        stocks_with_gap_up=0,
    )
    text = pulse.to_prompt_text()
    assert "Gap-Ups" not in text


# ---------------------------------------------------------------------------
# 16. SectorPulse.to_prompt_text — no gainers/losers lines when empty
# ---------------------------------------------------------------------------


def test_to_prompt_text_no_movers_when_empty():
    pulse = SectorPulse(
        sector="Metals",
        stock_count=0,
    )
    text = pulse.to_prompt_text()
    assert "Top Gainers" not in text
    assert "Top Losers" not in text


# ---------------------------------------------------------------------------
# 17. get_sector_pulse — indicators with partial data
# ---------------------------------------------------------------------------


async def test_get_sector_pulse_partial_indicator_data():
    """Stock with indicators dict but missing most fields should not crash."""
    stocks = [{"symbol": "SPARSE"}]
    tool = _build_tool(
        stocks_by_sector={"Misc": stocks},
        indicators_by_symbol={
            "SPARSE": {
                "some_irrelevant_key": True,
            },
        },
    )
    result = await tool.get_sector_pulse("Misc")

    assert result is not None
    assert result.stock_count == 1
    assert result.stocks_at_52w_high == 0
    assert result.stocks_with_volume_breakout == 0
    assert result.stocks_with_gap_up == 0
    assert result.avg_pct_change is None
    assert result.top_gainers == []
    assert result.top_losers == []
