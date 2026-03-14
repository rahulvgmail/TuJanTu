"""Tool that aggregates sector-level technical state from StockPulse."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.tools.stockpulse_client import StockPulseClient
from src.models.sector_pulse import SectorPulse

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


class SectorPulseTool:
    """Aggregates sector-level technical state from StockPulse."""

    def __init__(self, client: StockPulseClient):
        self.client = client

    async def get_sector_pulse(self, sector: str) -> SectorPulse | None:
        """Fetch all stocks in sector, aggregate their indicators."""
        stocks = await self.client.get_stocks_by_sector(sector)
        if not stocks:
            logger.info("No stocks found for sector %s", sector)
            return None

        # Fetch indicators for all stocks, batching if > _BATCH_SIZE
        all_indicators: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        for i in range(0, len(stocks), _BATCH_SIZE):
            batch = stocks[i : i + _BATCH_SIZE]
            coros = [self.client.get_indicators(s.get("symbol", ""), period="1d") for s in batch]
            results = await asyncio.gather(*coros, return_exceptions=True)
            for stock, result in zip(batch, results):
                if isinstance(result, BaseException):
                    logger.warning(
                        "Failed to fetch indicators for %s: %s",
                        stock.get("symbol", "?"),
                        result,
                    )
                    all_indicators.append((stock, None))
                else:
                    all_indicators.append((stock, result))

        # Aggregate
        stock_count = len(stocks)
        stocks_at_52w_high = 0
        stocks_with_volume_breakout = 0
        stocks_with_gap_up = 0
        pct_changes: list[float] = []
        dma_10_hold = 0
        dma_10_reverse = 0
        dma_20_hold = 0
        dma_20_reverse = 0
        movers: list[dict[str, Any]] = []

        for stock, ind in all_indicators:
            if ind is None:
                continue
            symbol = stock.get("symbol", "?")

            # 52W high
            if ind.get("is_52w_high_intraday") or ind.get("is_52w_closing_high"):
                stocks_at_52w_high += 1

            # Volume breakout
            if ind.get("is_volume_breakout"):
                stocks_with_volume_breakout += 1

            # Gap up
            if ind.get("is_gap_up"):
                stocks_with_gap_up += 1

            # Pct change
            pct = ind.get("pct_change")
            if pct is not None:
                pct_changes.append(float(pct))
                movers.append({
                    "symbol": symbol,
                    "pct_change": float(pct),
                    "price": ind.get("current_price"),
                })

            # DMA-10 signal
            dma_10_signal = self._extract_dma_signal(ind, "10")
            if dma_10_signal:
                sig_lower = dma_10_signal.lower()
                if sig_lower == "hold":
                    dma_10_hold += 1
                elif sig_lower in ("reverse", "reversal"):
                    dma_10_reverse += 1

            # DMA-20 signal
            dma_20_signal = self._extract_dma_signal(ind, "20")
            if dma_20_signal:
                sig_lower = dma_20_signal.lower()
                if sig_lower == "hold":
                    dma_20_hold += 1
                elif sig_lower in ("reverse", "reversal"):
                    dma_20_reverse += 1

        avg_pct_change = round(sum(pct_changes) / len(pct_changes), 2) if pct_changes else None

        # Sort for top gainers / losers
        movers.sort(key=lambda m: m["pct_change"], reverse=True)
        top_gainers = movers[:5]
        top_losers = list(reversed(movers[-5:])) if len(movers) >= 5 else list(reversed(movers))
        # Only keep actual losers (negative pct_change)
        top_losers = [m for m in top_losers if m["pct_change"] < 0]

        return SectorPulse(
            sector=sector,
            stock_count=stock_count,
            stocks_at_52w_high=stocks_at_52w_high,
            stocks_with_volume_breakout=stocks_with_volume_breakout,
            stocks_with_gap_up=stocks_with_gap_up,
            avg_pct_change=avg_pct_change,
            dma_10_hold_count=dma_10_hold,
            dma_10_reverse_count=dma_10_reverse,
            dma_20_hold_count=dma_20_hold,
            dma_20_reverse_count=dma_20_reverse,
            top_gainers=top_gainers,
            top_losers=top_losers,
            data_timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _extract_dma_signal(ind: dict[str, Any], period: str) -> str | None:
        """Extract DMA signal from indicator data, handling flat and nested shapes."""
        # Flat key: dma_{period}_signal
        flat_key = f"dma_{period}_signal"
        if flat_key in ind:
            return ind[flat_key]
        # Nested: dma_{period}.signal
        entry = ind.get(f"dma_{period}")
        if isinstance(entry, dict):
            return entry.get("signal")
        return None
