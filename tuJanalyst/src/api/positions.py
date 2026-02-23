"""API endpoints for current recommendation positions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from src.models.company import CompanyPosition
from src.repositories.base import PositionRepository

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


class PositionListResponse(BaseModel):
    """List response for current company positions."""

    items: list[CompanyPosition]
    total: int


def get_position_repo(request: Request) -> PositionRepository:
    """Get position repository from app state."""
    repository = getattr(request.app.state, "position_repo", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="Position repository is not configured")
    return repository


@router.get("/", response_model=PositionListResponse)
async def list_positions(
    position_repo: Annotated[PositionRepository, Depends(get_position_repo)],
    limit: int = Query(default=200, ge=1, le=500),
) -> PositionListResponse:
    """Return all current positions."""
    items = await position_repo.list_positions(limit=limit)
    return PositionListResponse(items=items, total=len(items))


@router.get("/{company_symbol}", response_model=CompanyPosition)
async def get_position(
    company_symbol: str,
    position_repo: Annotated[PositionRepository, Depends(get_position_repo)],
) -> CompanyPosition:
    """Return current position and history for a company symbol."""
    symbol = company_symbol.strip().upper()
    item = await position_repo.get_position(symbol)
    if item is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return item
