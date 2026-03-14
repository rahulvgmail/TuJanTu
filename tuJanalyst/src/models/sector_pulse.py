"""Sector-level technical pulse aggregation model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SectorPulse(BaseModel):
    """Aggregated technical state for all stocks in a sector."""

    model_config = ConfigDict(use_enum_values=True)

    sector: str
    stock_count: int = 0
    stocks_at_52w_high: int = 0
    stocks_with_volume_breakout: int = 0
    stocks_with_gap_up: int = 0
    avg_pct_change: float | None = None

    # DMA signal distribution
    dma_10_hold_count: int = 0
    dma_10_reverse_count: int = 0
    dma_20_hold_count: int = 0
    dma_20_reverse_count: int = 0

    # Top movers
    top_gainers: list[dict] = Field(default_factory=list)  # [{symbol, pct_change, price}]
    top_losers: list[dict] = Field(default_factory=list)

    data_timestamp: datetime | None = None

    def to_prompt_text(self) -> str:
        """Produce sector summary for LLM prompt."""
        lines = [f"Sector Pulse ({self.sector}):"]

        # Summary line
        avg_change_str = "N/A"
        if self.avg_pct_change is not None:
            sign = "+" if self.avg_pct_change >= 0 else ""
            avg_change_str = f"{sign}{self.avg_pct_change:.1f}%"
        lines.append(
            f"  Stocks: {self.stock_count}"
            f" | At 52W High: {self.stocks_at_52w_high}"
            f" | Volume Breakout: {self.stocks_with_volume_breakout}"
            f" | Avg Change: {avg_change_str}"
        )

        # DMA distribution
        lines.append(
            f"  DMA-10: {self.dma_10_hold_count} Hold, {self.dma_10_reverse_count} Reverse"
            f" | DMA-20: {self.dma_20_hold_count} Hold, {self.dma_20_reverse_count} Reverse"
        )

        # Gap-ups
        if self.stocks_with_gap_up > 0:
            lines.append(f"  Gap-Ups: {self.stocks_with_gap_up}")

        # Top gainers
        if self.top_gainers:
            gainer_parts = []
            for g in self.top_gainers[:5]:
                symbol = g.get("symbol", "?")
                pct = g.get("pct_change", 0)
                sign = "+" if pct >= 0 else ""
                gainer_parts.append(f"{symbol} ({sign}{pct:.1f}%)")
            lines.append("  Top Gainers: " + ", ".join(gainer_parts))

        # Top losers
        if self.top_losers:
            loser_parts = []
            for lo in self.top_losers[:5]:
                symbol = lo.get("symbol", "?")
                pct = lo.get("pct_change", 0)
                loser_parts.append(f"{symbol} ({pct:.1f}%)")
            lines.append("  Top Losers: " + ", ".join(loser_parts))

        return "\n".join(lines)
