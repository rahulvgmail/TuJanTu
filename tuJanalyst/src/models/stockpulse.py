"""Pydantic models for StockPulse API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ── Moving-average sub-models ──────────────────────────────────────────


class DMAEntry(BaseModel):
    """Daily moving-average entry (10/20/50/100/200-day)."""

    model_config = ConfigDict(use_enum_values=True)

    value: float | None = None
    touch: bool = False
    signal: str | None = None  # "Hold" / "Reverse"


class WMAEntry(BaseModel):
    """Weekly moving-average entry (5/10/20/30-week)."""

    model_config = ConfigDict(use_enum_values=True)

    value: float | None = None
    touch: bool = False
    signal: str | None = None


# ── StockPulse indicator response ──────────────────────────────────────


class StockPulseIndicators(BaseModel):
    """Mirrors the full StockPulse indicator response for a stock."""

    model_config = ConfigDict(use_enum_values=True)

    # Price
    current_price: float | None = None
    prev_close: float | None = None
    pct_change: float | None = None
    pe: float | None = None
    market_cap_cr: float | None = None
    today_high: float | None = None
    today_low: float | None = None
    today_open: float | None = None
    today_volume: int | None = None

    # Daily moving averages
    dma_10: DMAEntry | None = None
    dma_20: DMAEntry | None = None
    dma_50: DMAEntry | None = None
    dma_100: DMAEntry | None = None
    dma_200: DMAEntry | None = None

    # Weekly moving averages
    wma_5: WMAEntry | None = None
    wma_10: WMAEntry | None = None
    wma_20: WMAEntry | None = None
    wma_30: WMAEntry | None = None

    # 52-week
    high_52w: float | None = None
    is_52w_high_intraday: bool = False
    is_52w_closing_high: bool = False
    was_52w_high_yesterday: bool = False
    high_52w_date: str | None = None

    # Volume
    max_vol_21d: int | None = None
    avg_vol_140d: int | None = None
    avg_vol_280d: int | None = None
    is_volume_breakout: bool = False

    # Gap
    gap_pct: float | None = None
    is_gap_up: bool = False
    is_gap_down: bool = False

    # 90-day
    high_90d: float | None = None
    low_90d: float | None = None
    is_90d_high: bool = False
    is_90d_low_touch: bool = False

    # Breakout
    is_biweek_bo: bool = False
    is_week_bo: bool = False

    # Result proximity
    days_to_result: int | None = None
    result_within_7d: bool = False
    result_within_10d: bool = False
    result_within_15d: bool = False
    result_declared_10d: bool = False


# ── Other StockPulse resource models ───────────────────────────────────


class StockPulseEvent(BaseModel):
    """A single event record from StockPulse."""

    model_config = ConfigDict(use_enum_values=True)

    id: int
    stock_id: int
    symbol: str | None = None
    event_type: str
    payload: dict | None = None
    created_at: str


class StockPulseStock(BaseModel):
    """Stock master record from StockPulse."""

    model_config = ConfigDict(use_enum_values=True)

    id: int
    symbol: str
    nse_symbol: str | None = None
    company_name: str
    sector: str | None = None
    industry: str | None = None
    is_active: bool = True
    color: str | None = None


class StockPulseScreener(BaseModel):
    """Screener definition from StockPulse."""

    model_config = ConfigDict(use_enum_values=True)

    id: int
    name: str
    slug: str | None = None
    category: str | None = None
    is_builtin: bool = True
    is_active: bool = True
    condition_count: int = 0
