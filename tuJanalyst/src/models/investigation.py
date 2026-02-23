"""Layer 3 investigation models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class SignificanceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOISE = "noise"


class ExtractedMetric(BaseModel):
    """A single financial metric extracted from source text."""

    model_config = ConfigDict(use_enum_values=True)

    name: str
    value: float | str
    raw_value: str
    unit: str = ""
    period: str = ""
    yoy_change: float | None = None
    qoq_change: float | None = None
    confidence: float = 0.8


class ForwardStatement(BaseModel):
    """A forward-looking management statement."""

    model_config = ConfigDict(use_enum_values=True)

    statement: str
    target_metric: str | None = None
    target_value: str | None = None
    target_date: str | None = None
    category: str = "general"


class WebSearchResult(BaseModel):
    """A summarized web-search finding."""

    model_config = ConfigDict(use_enum_values=True)

    query: str
    source: str
    title: str
    summary: str
    relevance: str
    sentiment: str = "neutral"


class MarketDataSnapshot(BaseModel):
    """Market snapshot at analysis time."""

    model_config = ConfigDict(use_enum_values=True)

    current_price: float | None = None
    market_cap_cr: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    avg_volume_30d: int | None = None
    price_change_1d: float | None = None
    price_change_1w: float | None = None
    price_change_1m: float | None = None
    sector_pe_avg: float | None = None
    fii_holding_pct: float | None = None
    dii_holding_pct: float | None = None
    promoter_holding_pct: float | None = None
    promoter_pledge_pct: float | None = None
    data_source: str = "yfinance"
    data_timestamp: datetime | None = None


class HistoricalContext(BaseModel):
    """Prior company context used in analysis."""

    model_config = ConfigDict(use_enum_values=True)

    past_investigations: list[dict] = Field(default_factory=list)
    past_recommendations: list[dict] = Field(default_factory=list)
    past_promises: list[dict] = Field(default_factory=list)
    similar_documents: list[dict] = Field(default_factory=list)
    total_past_investigations: int = 0


class Investigation(BaseModel):
    """Primary persisted Layer 3 analysis result."""

    model_config = ConfigDict(use_enum_values=True)

    investigation_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_id: str
    company_symbol: str
    company_name: str

    extracted_metrics: list[ExtractedMetric] = Field(default_factory=list)
    forward_statements: list[ForwardStatement] = Field(default_factory=list)
    management_highlights: list[str] = Field(default_factory=list)
    web_search_results: list[WebSearchResult] = Field(default_factory=list)
    market_data: MarketDataSnapshot | None = None
    historical_context: HistoricalContext | None = None

    synthesis: str = ""
    key_findings: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    significance: SignificanceLevel = SignificanceLevel.MEDIUM
    significance_reasoning: str = ""
    is_significant: bool = False

    llm_model_used: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    processing_time_seconds: float = 0.0

    created_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "investigations"
