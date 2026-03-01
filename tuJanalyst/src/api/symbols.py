"""API endpoints for canonical NSE/BSE symbol lookup."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.models.symbol_resolution import CompanyMaster
from src.repositories.base import CompanyMasterRepository

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class SymbolMatchRow(BaseModel):
    """Company symbol match row."""

    canonical_id: str
    nse_symbol: str | None = None
    bse_scrip_code: str | None = None
    isin: str | None = None
    company_name: str
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SymbolResolveResponse(BaseModel):
    """Symbol resolve response payload."""

    query: str
    total: int
    matches: list[SymbolMatchRow]


def _repo(request: Request) -> CompanyMasterRepository:
    repo = getattr(request.app.state, "company_master_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Company master repository is not configured")
    return repo


def _normalize(text: str) -> str:
    return _NON_ALNUM.sub(" ", str(text or "").strip().lower()).strip()


def _score_match(query: str, item: CompanyMaster) -> tuple[int, str]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return 0, "none"

    nse = str(item.nse_symbol or "").upper()
    bse = str(item.bse_scrip_code or "")
    isin = str(item.isin or "").upper()
    raw_query = query.strip().upper()
    if raw_query and raw_query == nse:
        return 100, "nse_symbol"
    if raw_query and raw_query == bse:
        return 98, "bse_scrip_code"
    if raw_query and raw_query == isin:
        return 97, "isin"

    all_names = [item.company_name, *item.aliases]
    for name in all_names:
        normalized_name = _normalize(name)
        if normalized_name == normalized_query:
            return 95, "exact_name"
    for name in all_names:
        normalized_name = _normalize(name)
        if normalized_query and normalized_query in normalized_name:
            return 80, "partial_name"
    return 0, "none"


@router.get("/resolve", response_model=SymbolResolveResponse)
async def resolve_symbol(
    request: Request,
    q: Annotated[str, Query(min_length=1)],
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SymbolResolveResponse:
    """Resolve user-entered company text into canonical NSE/BSE identifiers."""
    repo = _repo(request)
    query = q.strip()

    exact_rows: list[CompanyMaster] = []
    as_upper = query.upper()
    if as_upper:
        by_nse = await repo.get_by_nse_symbol(as_upper)
        if by_nse is not None:
            exact_rows.append(by_nse)
    if query.isdigit():
        by_bse = await repo.get_by_bse_scrip_code(query)
        if by_bse is not None:
            exact_rows.append(by_bse)

    search_rows: list[CompanyMaster]
    if tag:
        candidates = await repo.list_by_tag(tag, limit=500)
        scored = []
        for item in candidates:
            score, _ = _score_match(query, item)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda row: row[0], reverse=True)
        search_rows = [row[1] for row in scored[:limit]]
    else:
        search_rows = await repo.search_by_name(query, limit=max(limit * 3, 20))
        scored = []
        for item in search_rows:
            score, _ = _score_match(query, item)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda row: row[0], reverse=True)
        search_rows = [row[1] for row in scored[:limit]]

    merged: list[CompanyMaster] = []
    seen: set[str] = set()
    for row in [*exact_rows, *search_rows]:
        key = str(row.canonical_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    return SymbolResolveResponse(
        query=query,
        total=len(merged),
        matches=[
            SymbolMatchRow(
                canonical_id=str(item.canonical_id),
                nse_symbol=item.nse_symbol,
                bse_scrip_code=item.bse_scrip_code,
                isin=item.isin,
                company_name=item.company_name,
                aliases=item.aliases,
                tags=item.tags,
            )
            for item in merged
        ],
    )

