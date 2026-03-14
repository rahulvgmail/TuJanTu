"""Performance feedback loop models for tracking recommendation outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class RecommendationOutcome(BaseModel):
    """Tracks the actual market outcome of a recommendation over time."""

    model_config = ConfigDict(use_enum_values=True)

    outcome_id: str = Field(default_factory=lambda: str(uuid4()))
    assessment_id: str
    company_symbol: str
    company_name: str
    recommendation: str  # buy/sell/hold
    confidence: float
    timeframe: str  # short_term/medium_term/long_term

    entry_price: float
    entry_date: datetime

    # Checkpoint prices (filled in over time)
    price_1w: float | None = None
    price_1m: float | None = None
    price_3m: float | None = None

    # Returns (calculated from entry_price)
    return_1w_pct: float | None = None
    return_1m_pct: float | None = None
    return_3m_pct: float | None = None

    # Outcome classification
    outcome: str | None = None  # "win", "loss", "neutral", None (still open)
    is_closed: bool = False
    closed_at: datetime | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "recommendation_outcomes"
