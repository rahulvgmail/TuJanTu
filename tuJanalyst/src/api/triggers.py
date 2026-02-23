"""API endpoints for human trigger submission and trigger status queries."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.models.trigger import TriggerEvent, TriggerPriority, TriggerSource, TriggerStatus
from src.repositories.base import TriggerRepository

router = APIRouter(prefix="/api/v1/triggers", tags=["triggers"])


class HumanTriggerRequest(BaseModel):
    """Request payload for manual trigger creation."""

    content: str = Field(min_length=1)
    company_symbol: str | None = None
    company_name: str | None = None
    source_url: str | None = None
    triggered_by: str | None = None
    notes: str | None = None


class HumanTriggerAcceptedResponse(BaseModel):
    """Response returned when a human trigger is accepted."""

    trigger_id: str
    status: str


class TriggerStatusResponse(BaseModel):
    """Lightweight trigger status representation."""

    trigger_id: str
    status: str
    source: str
    company_symbol: str | None = None
    company_name: str | None = None
    created_at: datetime


class TriggerListResponse(BaseModel):
    """Paginated trigger list response."""

    items: list[TriggerStatusResponse]
    total: int
    limit: int
    offset: int


class TriggerStatsResponse(BaseModel):
    """Trigger status counts response."""

    total: int
    counts_by_status: dict[str, int]


def get_trigger_repo(request: Request) -> TriggerRepository:
    """Get trigger repository from app state."""
    repository = getattr(request.app.state, "trigger_repo", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="Trigger repository is not configured")
    return repository


@router.post("/human", response_model=HumanTriggerAcceptedResponse)
async def create_human_trigger(
    payload: HumanTriggerRequest,
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
) -> HumanTriggerAcceptedResponse:
    """Create a high-priority human trigger that bypasses gate filtering."""
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        source_url=payload.source_url,
        company_symbol=payload.company_symbol,
        company_name=payload.company_name,
        raw_content=payload.content,
        priority=TriggerPriority.HIGH,
        triggered_by=payload.triggered_by,
        human_notes=payload.notes,
    )
    trigger.set_status(TriggerStatus.GATE_PASSED, "Human trigger bypasses Layer 2 gate")
    await trigger_repo.save(trigger)
    return HumanTriggerAcceptedResponse(trigger_id=trigger.trigger_id, status="accepted")


@router.get("/stats", response_model=TriggerStatsResponse)
async def trigger_stats(
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    since: datetime | None = None,
) -> TriggerStatsResponse:
    """Return trigger counts by status with optional date floor."""
    counts_by_status = await trigger_repo.counts_by_status(since=since)
    total = sum(counts_by_status.values())
    return TriggerStatsResponse(
        total=total,
        counts_by_status=counts_by_status,
    )


@router.get("/{trigger_id}", response_model=TriggerStatusResponse)
async def get_trigger_status(
    trigger_id: str,
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
) -> TriggerStatusResponse:
    """Return current status for a trigger by ID."""
    trigger = await trigger_repo.get(trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerStatusResponse(
        trigger_id=trigger.trigger_id,
        status=trigger.status,
        source=trigger.source,
        company_symbol=trigger.company_symbol,
        company_name=trigger.company_name,
        created_at=trigger.created_at,
    )


@router.get("/", response_model=TriggerListResponse)
async def list_triggers(
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    status: TriggerStatus | None = None,
    company: str | None = None,
    source: TriggerSource | None = None,
    since: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TriggerListResponse:
    """List recent triggers with optional status/company filters."""
    source_value = source.value if source is not None else None
    triggers = await trigger_repo.list_recent(
        limit=limit,
        offset=offset,
        status=status,
        company_symbol=company,
        source=source_value,
        since=since,
    )
    total = await trigger_repo.count(
        status=status,
        company_symbol=company,
        source=source_value,
        since=since,
    )
    return TriggerListResponse(
        items=[
            TriggerStatusResponse(
                trigger_id=trigger.trigger_id,
                status=trigger.status,
                source=trigger.source,
                company_symbol=trigger.company_symbol,
                company_name=trigger.company_name,
                created_at=trigger.created_at,
            )
            for trigger in triggers
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
