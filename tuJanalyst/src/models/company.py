"""Company and watchlist configuration models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.decision import Recommendation

CompanyPriority = Literal["high", "normal"]


class Sector(BaseModel):
    """Sector configuration and associated trigger keywords."""

    name: str
    keywords: list[str] = Field(default_factory=list)
    nse_industry_code: str | None = None
    bse_industry_code: str | None = None

    @model_validator(mode="after")
    def validate_keywords(self) -> "Sector":
        if not self.keywords:
            raise ValueError(f"Sector '{self.name}' must define at least one keyword")
        return self


class Company(BaseModel):
    """Company metadata used for monitoring and filtering."""

    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str
    name: str
    sector: str | None = None
    industry: str | None = None
    market_cap_category: str | None = None
    bse_code: str | None = None
    nse_listed: bool = True
    bse_listed: bool = False
    priority: CompanyPriority = "normal"
    monitoring_active: bool = True
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_symbol(self) -> "Company":
        self.symbol = self.symbol.upper()
        return self


class WatchlistConfig(BaseModel):
    """Loaded from watchlist YAML at startup."""

    sectors: list[Sector] = Field(default_factory=list)
    companies: list[Company] = Field(default_factory=list)
    global_keywords: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_collections(self) -> "WatchlistConfig":
        if not self.sectors:
            raise ValueError("Watchlist config must define at least one sector")

        if not self.companies:
            raise ValueError("Watchlist config must define at least one company")

        symbols = [company.symbol for company in self.companies]
        duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
        if duplicates:
            raise ValueError(f"Duplicate company symbols in watchlist: {', '.join(duplicates)}")

        return self


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class CompanyPosition(BaseModel):
    """Current recommendation state tracked per company."""

    model_config = ConfigDict(use_enum_values=True)

    company_symbol: str
    company_name: str

    current_recommendation: Recommendation = Recommendation.NONE
    recommendation_date: datetime | None = None
    recommendation_basis: str = ""
    recommendation_assessment_id: str | None = None

    recommendation_history: list[dict[str, Any]] = Field(default_factory=list)

    total_investigations: int = 0
    last_investigation_date: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    collection_name: ClassVar[str] = "positions"
