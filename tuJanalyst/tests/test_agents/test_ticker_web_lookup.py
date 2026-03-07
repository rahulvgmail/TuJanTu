"""Tests for ticker web lookup parser helper."""

from __future__ import annotations

import pytest

from src.agents.tools.ticker_web_lookup import TickerWebLookup


class _FakeSearchTool:
    def __init__(self, rows):
        self.rows = rows

    async def search(self, query: str, *, max_results: int | None = None):  # noqa: ARG002
        return self.rows


@pytest.mark.asyncio
async def test_ticker_web_lookup_extracts_nse_and_bse_codes() -> None:
    search_tool = _FakeSearchTool(
        [
            {
                "title": "State Bank of India NSE: SBIN BSE: 500112",
                "url": "https://www.nseindia.com/some-page",
                "snippet": "ISIN INE062A01020",
            }
        ]
    )
    lookup = TickerWebLookup(search_tool=search_tool)

    result = await lookup.lookup("State Bank of India ticker")

    assert result is not None
    assert result["nse_symbol"] == "SBIN"
    assert result["bse_scrip_code"] == "500112"


@pytest.mark.asyncio
async def test_ticker_web_lookup_returns_none_when_no_match() -> None:
    search_tool = _FakeSearchTool(
        [
            {
                "title": "Bank sector outlook",
                "url": "https://example.test/article",
                "snippet": "No ticker codes here",
            }
        ]
    )
    lookup = TickerWebLookup(search_tool=search_tool)

    result = await lookup.lookup("bank sector")

    assert result is None
