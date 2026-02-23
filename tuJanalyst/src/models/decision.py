"""Layer 4 decision assessment models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class Recommendation(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NONE = "none"


class RecommendationTimeframe(str, Enum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class DecisionAssessment(BaseModel):
    """Layer 4 recommendation decision for a company."""

    model_config = ConfigDict(use_enum_values=True)

    assessment_id: str = Field(default_factory=lambda: str(uuid4()))
    investigation_id: str
    trigger_id: str
    company_symbol: str
    company_name: str

    previous_recommendation: Recommendation = Recommendation.NONE
    previous_recommendation_date: datetime | None = None
    previous_recommendation_basis: str = ""

    recommendation_changed: bool = False
    new_recommendation: Recommendation = Recommendation.NONE
    timeframe: RecommendationTimeframe = RecommendationTimeframe.MEDIUM_TERM
    confidence: float = 0.0

    reasoning: str = ""
    key_factors_for: list[str] = Field(default_factory=list)
    key_factors_against: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    past_investigations_used: list[str] = Field(default_factory=list)
    past_inconclusive_resurrected: list[str] = Field(default_factory=list)

    llm_model_used: str = ""
    processing_time_seconds: float = 0.0

    created_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "assessments"
