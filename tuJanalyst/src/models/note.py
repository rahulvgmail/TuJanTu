"""Shared analyst/investor notes model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(UTC)


class AnalysisNote(BaseModel):
    """Shared note attached to a company and optional analysis entities."""

    model_config = ConfigDict(use_enum_values=True)

    note_id: str = Field(default_factory=lambda: str(uuid4()))
    company_symbol: str
    company_name: str = ""
    content: str
    tags: list[str] = Field(default_factory=list)
    investigation_id: str | None = None
    report_id: str | None = None
    created_by: str = "analyst"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "notes"
