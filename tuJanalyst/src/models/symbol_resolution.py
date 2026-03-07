"""Models for canonical NSE/BSE symbol resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class ResolutionMethod(str, Enum):
    """Resolver strategy used to pick final company identifiers."""

    EXACT_SYMBOL = "exact_symbol"
    EXACT_BSE_CODE = "exact_bse_code"
    EXACT_ISIN = "exact_isin"
    EXACT_NAME = "exact_name"
    FUZZY_NAME = "fuzzy_name"
    WEB = "web"
    DSPY = "dspy"
    UNRESOLVED = "unresolved"


class CompanyMaster(BaseModel):
    """Canonical company identity record used for NSE/BSE mapping."""

    model_config = ConfigDict(str_strip_whitespace=True)

    canonical_id: str | None = None
    nse_symbol: str | None = None
    bse_scrip_code: str | None = None
    isin: str | None = None
    company_name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    nse_listed: bool = True
    bse_listed: bool = False
    sector: str | None = None
    industry: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("nse_symbol", mode="before")
    @classmethod
    def _normalize_nse_symbol(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("bse_scrip_code", mode="before")
    @classmethod
    def _normalize_bse_code(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("isin", mode="before")
    @classmethod
    def _normalize_isin(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("aliases", mode="before")
    @classmethod
    def _normalize_aliases(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            normalized = text.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        tags: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            tags.append(text)
        return tags

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        if not self.canonical_id:
            if self.nse_symbol:
                self.canonical_id = f"IN::{self.nse_symbol}"
            elif self.bse_scrip_code:
                self.canonical_id = f"IN::BSE::{self.bse_scrip_code}"
            elif self.isin:
                self.canonical_id = f"IN::ISIN::{self.isin}"
            else:
                slug = self.company_name.strip().upper().replace(" ", "_")
                self.canonical_id = f"IN::{slug}"


class ResolutionInput(BaseModel):
    """Input fields used when resolving exchange company identifiers."""

    model_config = ConfigDict(str_strip_whitespace=True)

    raw_symbol: str | None = None
    company_name: str | None = None
    source_exchange: Literal["nse", "bse", "unknown"] = "unknown"
    title: str | None = None
    content: str | None = None
    isin: str | None = None
    source_url: str | None = None

    @field_validator("raw_symbol", mode="before")
    @classmethod
    def _normalize_raw_symbol(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("isin", mode="before")
    @classmethod
    def _normalize_input_isin(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None


class ResolutionResult(BaseModel):
    """Structured output for ticker resolution decisions."""

    method: ResolutionMethod = ResolutionMethod.UNRESOLVED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    resolved: bool = False
    review_required: bool = True

    canonical_id: str | None = None
    nse_symbol: str | None = None
    bse_scrip_code: str | None = None
    isin: str | None = None
    company_name: str | None = None

    evidence: list[str] = Field(default_factory=list)

