"""Layer 5 report models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class ReportDeliveryStatus(str, Enum):
    GENERATED = "generated"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"


class AnalysisReport(BaseModel):
    """Layer 5 generated report + delivery metadata."""

    model_config = ConfigDict(use_enum_values=True)

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    assessment_id: str
    investigation_id: str
    trigger_id: str
    company_symbol: str
    company_name: str

    title: str = ""
    executive_summary: str = ""
    report_body: str = ""
    recommendation_summary: str = ""

    delivery_status: ReportDeliveryStatus = ReportDeliveryStatus.GENERATED
    delivered_via: list[str] = Field(default_factory=list)
    delivered_at: datetime | None = None

    feedback_rating: int | None = None
    feedback_comment: str | None = None
    feedback_by: str | None = None
    feedback_at: datetime | None = None

    created_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "reports"
