"""Combined technical-analysis context for LLM prompt injection."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TechnicalContext(BaseModel):
    """Combined technical analysis context from StockPulse for a single stock."""

    model_config = ConfigDict(use_enum_values=True)

    symbol: str
    data_timestamp: datetime | None = None

    # Price & trend
    current_price: float | None = None
    pct_change: float | None = None

    # DMA signals (compact representation)
    dma_signals: dict[str, str | None] = Field(default_factory=dict)
    # e.g., {"10": "Hold", "20": "Hold", "50": None, "100": None, "200": None}

    # WMA signals
    wma_signals: dict[str, str | None] = Field(default_factory=dict)

    # 52-week status
    is_52w_high_intraday: bool = False
    is_52w_closing_high: bool = False
    high_52w: float | None = None

    # Volume
    is_volume_breakout: bool = False
    today_volume: int | None = None
    max_vol_21d: int | None = None
    avg_vol_140d: int | None = None

    # Gap
    gap_pct: float | None = None
    is_gap_up: bool = False
    is_gap_down: bool = False

    # 90D
    is_90d_high: bool = False
    is_90d_low_touch: bool = False

    # Breakout
    is_biweek_bo: bool = False
    is_week_bo: bool = False

    # Result dates
    days_to_result: int | None = None
    result_within_7d: bool = False
    result_within_10d: bool = False
    result_within_15d: bool = False
    result_declared_10d: bool = False

    # Color classification from fund
    color: str | None = None

    # Screener membership
    screener_names: list[str] = Field(default_factory=list)

    # Recent technical events
    recent_events: list[dict] = Field(default_factory=list)
    # Each: {"event_type": str, "payload": dict, "created_at": str}

    def to_prompt_text(self) -> str:
        """Produce a concise text summary suitable for LLM prompt injection."""
        lines = [f"Technical State ({self.symbol}):"]

        # Price line
        price_parts: list[str] = []
        if self.current_price is not None:
            price_parts.append(f"Price: ₹{self.current_price:,.2f}")
        if self.pct_change is not None:
            sign = "+" if self.pct_change >= 0 else ""
            price_parts.append(f"({sign}{self.pct_change:.1f}%)")
        if price_parts:
            lines.append("  " + " ".join(price_parts))

        # 52W status
        if self.is_52w_closing_high:
            lines.append("  52W High: YES (closing high)")
        elif self.is_52w_high_intraday:
            lines.append("  52W High: YES (intraday)")

        # DMA signals
        active_dma = [
            f"DMA-{period}: {signal}"
            for period, signal in sorted(self.dma_signals.items(), key=lambda x: int(x[0]))
            if signal
        ]
        if active_dma:
            lines.append("  DMA Signals: " + ", ".join(active_dma))

        # WMA signals
        active_wma = [
            f"WMA-{period}: {signal}"
            for period, signal in sorted(self.wma_signals.items(), key=lambda x: int(x[0]))
            if signal
        ]
        if active_wma:
            lines.append("  WMA Signals: " + ", ".join(active_wma))

        # Volume
        if self.is_volume_breakout:
            vol_detail = ""
            if self.today_volume and self.max_vol_21d:
                vol_detail = (
                    f" (today: {self._fmt_volume(self.today_volume)}"
                    f" vs 21d-max: {self._fmt_volume(self.max_vol_21d)})"
                )
            lines.append(f"  Volume: BREAKOUT{vol_detail}")

        # Gap
        if self.is_gap_up and self.gap_pct is not None:
            lines.append(f"  Gap: +{self.gap_pct:.1f}% gap-up")
        elif self.is_gap_down and self.gap_pct is not None:
            lines.append(f"  Gap: {self.gap_pct:.1f}% gap-down")

        # 90D
        if self.is_90d_high:
            lines.append("  90D: At 90-day high")
        elif self.is_90d_low_touch:
            lines.append("  90D: Touching 90-day low")

        # Breakout
        breakouts: list[str] = []
        if self.is_biweek_bo:
            breakouts.append("biweekly")
        if self.is_week_bo:
            breakouts.append("weekly")
        if breakouts:
            lines.append("  Breakout: " + ", ".join(breakouts))

        # Result dates
        if self.result_declared_10d:
            lines.append("  Result: declared within last 10 days")
        elif self.days_to_result is not None and self.days_to_result > 0:
            lines.append(f"  Result: in {self.days_to_result} days")

        # Color
        if self.color:
            color_labels = {
                "Pink": "Portfolio",
                "Orange": "Post-result breakout",
                "Yellow": "Capex/promoter buying",
                "Blue": "Good results",
                "Red": "Bad results",
                "Green": "Watchlist",
            }
            label = color_labels.get(self.color, "")
            lines.append(f"  Color: {self.color}" + (f" ({label})" if label else ""))

        # Screeners
        if self.screener_names:
            count = len(self.screener_names)
            display = self.screener_names[:5]
            suffix = f", ... (+{count - 5} more)" if count > 5 else ""
            lines.append(f"  Screeners ({count}): " + ", ".join(display) + suffix)

        # Recent events
        if self.recent_events:
            event_strs: list[str] = []
            for evt in self.recent_events[:5]:
                event_strs.append(evt.get("event_type", "UNKNOWN"))
            lines.append("  Recent Events: " + ", ".join(event_strs))

        if len(lines) == 1:
            lines.append("  No technical data available")

        return "\n".join(lines)

    @staticmethod
    def _fmt_volume(vol: int) -> str:
        if vol >= 1_000_000:
            return f"{vol / 1_000_000:.1f}M"
        if vol >= 1_000:
            return f"{vol / 1_000:.0f}K"
        return str(vol)
