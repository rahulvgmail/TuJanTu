"""Core document models for ingestion and extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class DocumentType(str, Enum):
    PDF = "pdf"
    HTML = "html"
    EXCEL = "excel"
    TEXT = "text"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EMBEDDING = "embedding"
    COMPLETE = "complete"
    ERROR = "error"


class RawDocument(BaseModel):
    """Document metadata and extracted content tracked across Layer 1/2."""

    model_config = ConfigDict(use_enum_values=True)

    document_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_id: str
    source_url: str
    file_path: str | None = None

    document_type: DocumentType = DocumentType.UNKNOWN
    content_type: str | None = None
    file_size_bytes: int | None = None

    extracted_text: str | None = None
    extraction_method: str | None = None
    extraction_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    company_symbol: str | None = None
    company_name: str | None = None

    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_errors: list[str] = Field(default_factory=list)

    vector_id: str | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

