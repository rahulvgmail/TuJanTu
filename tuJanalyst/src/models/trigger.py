"""Core trigger models for Layer 1 ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class TriggerSource(str, Enum):
    NSE_RSS = "nse_rss"
    BSE_RSS = "bse_rss"
    HUMAN = "human"


class TriggerStatus(str, Enum):
    PENDING = "pending"
    FILTERED_OUT = "filtered_out"
    GATE_PASSED = "gate_passed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ASSESSING = "assessing"
    ASSESSED = "assessed"
    REPORTED = "reported"
    ERROR = "error"


class TriggerPriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"


class StatusTransition(BaseModel):
    """A status change event in the trigger processing lifecycle."""

    model_config = ConfigDict(use_enum_values=True)

    status: TriggerStatus
    timestamp: datetime = Field(default_factory=utc_now)
    reason: str = ""


class TriggerEvent(BaseModel):
    """Represents a single investigation trigger entering the pipeline."""

    model_config = ConfigDict(use_enum_values=True)

    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    source: TriggerSource
    source_url: str | None = None
    source_feed_title: str | None = None
    source_feed_published: datetime | None = None

    company_symbol: str | None = None
    company_name: str | None = None
    sector: str | None = None

    raw_content: str
    document_ids: list[str] = Field(default_factory=list)

    priority: TriggerPriority = TriggerPriority.NORMAL
    triggered_by: str | None = None
    human_notes: str | None = None

    status: TriggerStatus = TriggerStatus.PENDING
    status_history: list[StatusTransition] = Field(default_factory=list)
    gate_result: dict[str, Any] | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def set_status(self, status: TriggerStatus, reason: str = "") -> None:
        """Update current status and append a status transition record."""
        self.status = status
        self.updated_at = utc_now()
        self.status_history.append(StatusTransition(status=status, reason=reason))

