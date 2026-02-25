"""API endpoints for in-app notification feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationItem(BaseModel):
    """A single in-app notification row."""

    notification_id: str
    kind: Literal["report_created", "investigation_completed"]
    company_symbol: str
    company_name: str
    entity_id: str
    title: str
    message: str
    created_at: datetime


class NotificationFeedResponse(BaseModel):
    """Notification feed response."""

    items: list[NotificationItem]
    total: int
    since: datetime


def _coerce_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return fallback


def _normalize_window_start(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC) - timedelta(hours=24)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _report_notifications(db: Any, *, since: datetime, limit: int) -> list[NotificationItem]:
    items: list[NotificationItem] = []
    cursor = db["reports"].find(
        {"created_at": {"$gte": since}},
        projection={
            "report_id": 1,
            "company_symbol": 1,
            "company_name": 1,
            "recommendation_summary": 1,
            "created_at": 1,
            "_id": 0,
        },
    ).sort("created_at", -1).limit(limit)

    async for row in cursor:
        created_at = _coerce_datetime(row.get("created_at"), since)
        recommendation_summary = str(row.get("recommendation_summary") or "")
        recommendation = recommendation_summary.split(" ", maxsplit=1)[0].strip().upper() or "UPDATE"
        symbol = str(row.get("company_symbol") or "UNKNOWN").upper()
        report_id = str(row.get("report_id") or "")
        items.append(
            NotificationItem(
                notification_id=f"report:{report_id}",
                kind="report_created",
                company_symbol=symbol,
                company_name=str(row.get("company_name") or symbol),
                entity_id=report_id,
                title=f"New report: {symbol} — {recommendation}",
                message=recommendation_summary or "Analysis report is ready.",
                created_at=created_at,
            )
        )
    return items


async def _investigation_notifications(db: Any, *, since: datetime, limit: int) -> list[NotificationItem]:
    items: list[NotificationItem] = []
    cursor = db["investigations"].find(
        {"created_at": {"$gte": since}},
        projection={
            "investigation_id": 1,
            "company_symbol": 1,
            "company_name": 1,
            "significance": 1,
            "created_at": 1,
            "_id": 0,
        },
    ).sort("created_at", -1).limit(limit)

    async for row in cursor:
        created_at = _coerce_datetime(row.get("created_at"), since)
        symbol = str(row.get("company_symbol") or "UNKNOWN").upper()
        investigation_id = str(row.get("investigation_id") or "")
        significance = str(row.get("significance") or "unknown").upper()
        items.append(
            NotificationItem(
                notification_id=f"investigation:{investigation_id}",
                kind="investigation_completed",
                company_symbol=symbol,
                company_name=str(row.get("company_name") or symbol),
                entity_id=investigation_id,
                title=f"Investigation complete: {symbol}",
                message=f"Significance: {significance}",
                created_at=created_at,
            )
        )
    return items


@router.get("/feed", response_model=NotificationFeedResponse)
async def notification_feed(
    request: Request,
    since: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    include_reports: bool = Query(default=True),
    include_investigations: bool = Query(default=True),
) -> NotificationFeedResponse:
    """Return a combined in-app notification feed."""
    window_start = _normalize_window_start(since)
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        return NotificationFeedResponse(items=[], total=0, since=window_start)

    report_items = await _report_notifications(db, since=window_start, limit=limit) if include_reports else []
    investigation_items = (
        await _investigation_notifications(db, since=window_start, limit=limit) if include_investigations else []
    )

    merged = sorted(
        [*report_items, *investigation_items],
        key=lambda row: row.created_at,
        reverse=True,
    )
    items = merged[:limit]
    return NotificationFeedResponse(items=items, total=len(items), since=window_start)
