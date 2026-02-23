"""API endpoints for Layer 3 investigations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from src.models.investigation import Investigation
from src.repositories.base import InvestigationRepository

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


class InvestigationListResponse(BaseModel):
    """List response for company-scoped investigations."""

    items: list[Investigation]
    total: int


def get_investigation_repo(request: Request) -> InvestigationRepository:
    """Get investigation repository from app state."""
    repository = getattr(request.app.state, "investigation_repo", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="Investigation repository is not configured")
    return repository


@router.get("/company/{company_symbol}", response_model=InvestigationListResponse)
async def list_company_investigations(
    company_symbol: str,
    investigation_repo: Annotated[InvestigationRepository, Depends(get_investigation_repo)],
    limit: int = Query(default=20, ge=1, le=100),
) -> InvestigationListResponse:
    """List recent investigations for a company symbol."""
    symbol = company_symbol.strip().upper()
    items = await investigation_repo.get_by_company(symbol, limit=limit)
    return InvestigationListResponse(items=items, total=len(items))


@router.get("/{investigation_id}", response_model=Investigation)
async def get_investigation(
    investigation_id: str,
    investigation_repo: Annotated[InvestigationRepository, Depends(get_investigation_repo)],
) -> Investigation:
    """Return full investigation details by investigation ID."""
    investigation = await investigation_repo.get(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation
