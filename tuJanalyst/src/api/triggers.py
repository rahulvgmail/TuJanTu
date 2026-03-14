"""API endpoints for human trigger submission, webhook ingestion, and trigger status queries."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.config import get_settings
from src.integrations.event_formatter import format_technical_event
from src.integrations.flood_detector import FloodDetector
from src.models.trigger import TriggerEvent, TriggerPriority, TriggerSource, TriggerStatus
from src.repositories.base import TriggerRepository

logger = logging.getLogger(__name__)

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


class WebhookTriggerRequest(BaseModel):
    """Request payload for StockPulse technical event webhooks."""

    event_id: int
    event_type: str
    stock_id: int
    payload: dict
    created_at: str


class WebhookAcceptedResponse(BaseModel):
    """Response returned when a webhook trigger is accepted."""

    trigger_id: str
    status: str


# Module-level flood detector instance (shared across requests).
_flood_detector: FloodDetector | None = None


def _get_flood_detector() -> FloodDetector:
    """Return the shared flood detector, lazily initialised from settings."""
    global _flood_detector  # noqa: PLW0603
    if _flood_detector is None:
        settings = get_settings()
        _flood_detector = FloodDetector(
            threshold=settings.technical_event_flood_threshold,
            window_minutes=settings.technical_event_flood_window_minutes,
        )
    return _flood_detector


class TriggerStatusResponse(BaseModel):
    """Lightweight trigger status representation."""

    trigger_id: str
    status: str
    source: str
    company_symbol: str | None = None
    company_name: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    status_history: list[dict[str, Any]] | None = None
    gate_result: dict[str, Any] | None = None
    raw_content_preview: str | None = None


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
    counts_by_source: dict[str, int]


def get_trigger_repo(request: Request) -> TriggerRepository:
    """Get trigger repository from app state."""
    repository = getattr(request.app.state, "trigger_repo", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="Trigger repository is not configured")
    return repository


def _truncate_preview(content: str, max_chars: int) -> str:
    text = content.strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _build_trigger_status_response(
    trigger: TriggerEvent,
    *,
    include_details: bool,
    include_content_preview: bool,
    content_preview_chars: int,
) -> TriggerStatusResponse:
    status_history: list[dict[str, Any]] | None = None
    if include_details:
        status_history = [entry.model_dump() for entry in trigger.status_history]

    raw_content_preview = (
        _truncate_preview(trigger.raw_content, content_preview_chars)
        if include_content_preview
        else None
    )

    return TriggerStatusResponse(
        trigger_id=trigger.trigger_id,
        status=trigger.status,
        source=trigger.source,
        company_symbol=trigger.company_symbol,
        company_name=trigger.company_name,
        created_at=trigger.created_at,
        updated_at=trigger.updated_at if include_details else None,
        status_history=status_history,
        gate_result=trigger.gate_result if include_details else None,
        raw_content_preview=raw_content_preview,
    )


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
    await trigger_repo.save(trigger)
    return HumanTriggerAcceptedResponse(trigger_id=trigger.trigger_id, status="accepted")


@router.post("/webhook", response_model=WebhookAcceptedResponse)
async def receive_webhook(
    payload: WebhookTriggerRequest,
    request: Request,
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    x_stockpulse_signature: str | None = Header(default=None),
) -> WebhookAcceptedResponse:
    """Receive a StockPulse technical event webhook and create a trigger."""
    settings = get_settings()

    # --- HMAC signature validation (optional) ---
    if settings.stockpulse_webhook_secret:
        if not x_stockpulse_signature:
            raise HTTPException(status_code=401, detail="Missing X-StockPulse-Signature header")
        body_bytes = await request.body()
        expected = hmac.new(
            settings.stockpulse_webhook_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_stockpulse_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # --- Flood detection ---
    detector = _get_flood_detector()
    detector.record_event()
    if detector.is_flooding():
        logger.warning(
            "Webhook flood detected: %d events in %d-minute window, rejecting event_id=%d",
            detector.event_count_in_window(),
            detector.window_minutes,
            payload.event_id,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many webhook events; flood threshold exceeded",
        )

    # --- Build trigger ---
    symbol = payload.payload.get("symbol")
    raw_content = format_technical_event(
        event_type=payload.event_type,
        payload=payload.payload,
        symbol=symbol,
    )

    trigger = TriggerEvent(
        source=TriggerSource.TECHNICAL_EVENT,
        company_symbol=symbol,
        raw_content=raw_content,
        triggered_by=f"stockpulse_webhook:event_id={payload.event_id}",
    )
    await trigger_repo.save(trigger)
    return WebhookAcceptedResponse(trigger_id=trigger.trigger_id, status="accepted")


@router.get("/stats", response_model=TriggerStatsResponse)
async def trigger_stats(
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    since: datetime | None = None,
) -> TriggerStatsResponse:
    """Return trigger counts by status with optional date floor."""
    counts_by_status = await trigger_repo.counts_by_status(since=since)
    counts_by_source = await trigger_repo.counts_by_source(since=since)
    total = sum(counts_by_status.values())
    return TriggerStatsResponse(
        total=total,
        counts_by_status=counts_by_status,
        counts_by_source=counts_by_source,
    )


@router.get("/{trigger_id}", response_model=TriggerStatusResponse)
async def get_trigger_status(
    trigger_id: str,
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    include_details: bool = Query(default=False),
    include_content_preview: bool = Query(default=False),
    content_preview_chars: int = Query(default=100, ge=20, le=500),
) -> TriggerStatusResponse:
    """Return current status for a trigger by ID."""
    trigger = await trigger_repo.get(trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return _build_trigger_status_response(
        trigger,
        include_details=include_details,
        include_content_preview=include_content_preview,
        content_preview_chars=content_preview_chars,
    )


@router.get("/", response_model=TriggerListResponse)
async def list_triggers(
    trigger_repo: Annotated[TriggerRepository, Depends(get_trigger_repo)],
    status: TriggerStatus | None = None,
    company: str | None = None,
    source: TriggerSource | None = None,
    since: datetime | None = None,
    include_details: bool = Query(default=False),
    include_content_preview: bool = Query(default=False),
    content_preview_chars: int = Query(default=100, ge=20, le=500),
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
            _build_trigger_status_response(
                trigger,
                include_details=include_details,
                include_content_preview=include_content_preview,
                content_preview_chars=content_preview_chars,
            )
            for trigger in triggers
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
