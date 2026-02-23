"""Tests for market data tool behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agents.tools.market_data import MarketDataTool


class _FakeTicker:
    def __init__(self, info: dict, closes: list[float] | None = None):
        self.info = info
        self._closes = closes or []

    def history(self, period: str):  # noqa: ARG002
        return {"Close": self._closes}


@pytest.mark.asyncio
async def test_market_data_tool_uses_nse_snapshot_when_available() -> None:
    now = datetime(2026, 2, 23, tzinfo=timezone.utc)
    closes = [100.0 + i for i in range(25)]
    mapping = {
        "INOXWIND.NS": _FakeTicker(
            info={
                "regularMarketPrice": 212.5,
                "marketCap": 123_450_000_000,
                "trailingPE": 18.2,
                "priceToBook": 2.5,
                "fiftyTwoWeekHigh": 240.0,
                "fiftyTwoWeekLow": 120.0,
                "averageVolume": 1_250_000,
                "regularMarketChangePercent": 1.8,
            },
            closes=closes,
        )
    }

    tool = MarketDataTool(ticker_factory=mapping.__getitem__, now_fn=lambda: now)
    snapshot = await tool.get_snapshot("inoxwind")

    assert snapshot.data_source == "yfinance"
    assert snapshot.current_price == 212.5
    assert snapshot.market_cap_cr == 12345.0
    assert snapshot.pe_ratio == 18.2
    assert snapshot.price_change_1w is not None
    assert snapshot.price_change_1m is not None
    assert snapshot.data_timestamp == now


@pytest.mark.asyncio
async def test_market_data_tool_falls_back_to_bse_when_nse_missing() -> None:
    mapping = {
        "BHEL.NS": _FakeTicker(info={"regularMarketPrice": None}, closes=[100, 101, 99]),
        "BHEL.BO": _FakeTicker(info={"currentPrice": 210.0}, closes=[200, 205, 210]),
    }
    tool = MarketDataTool(ticker_factory=mapping.__getitem__)
    snapshot = await tool.get_snapshot("BHEL")

    assert snapshot.data_source == "yfinance"
    assert snapshot.current_price == 210.0


@pytest.mark.asyncio
async def test_market_data_tool_returns_unavailable_when_symbol_missing() -> None:
    mapping = {
        "UNKNOWN.NS": _FakeTicker(info={}, closes=[]),
        "UNKNOWN.BO": _FakeTicker(info={}, closes=[]),
    }
    tool = MarketDataTool(ticker_factory=mapping.__getitem__)
    snapshot = await tool.get_snapshot("UNKNOWN")

    assert snapshot.data_source == "yfinance_unavailable"
    assert snapshot.current_price is None


@pytest.mark.asyncio
async def test_market_data_tool_returns_error_snapshot_on_unexpected_failure() -> None:
    def failing_factory(symbol_code: str):  # noqa: ARG001
        raise RuntimeError("ticker backend failure")

    tool = MarketDataTool(ticker_factory=failing_factory)
    snapshot = await tool.get_snapshot("ABB")

    assert snapshot.data_source.startswith("error:")


@pytest.mark.asyncio
async def test_market_data_tool_keeps_unavailable_fields_as_none() -> None:
    mapping = {
        "SIEMENS.NS": _FakeTicker(info={"regularMarketPrice": 5000.0}, closes=[5000.0, 5010.0, 4990.0, 5025.0, 5030.0]),
    }
    tool = MarketDataTool(ticker_factory=mapping.__getitem__)
    snapshot = await tool.get_snapshot("SIEMENS")

    assert snapshot.fii_holding_pct is None
    assert snapshot.dii_holding_pct is None
    assert snapshot.promoter_holding_pct is None
    assert snapshot.promoter_pledge_pct is None
