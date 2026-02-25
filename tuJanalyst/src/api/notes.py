"""API endpoints for shared investor/analyst notes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.models.note import AnalysisNote

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


class NoteListResponse(BaseModel):
    """List response for shared notes."""

    items: list[AnalysisNote]
    total: int


class NoteCreateRequest(BaseModel):
    """Payload for creating a shared note."""

    company_symbol: str
    content: str
    company_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    investigation_id: str | None = None
    report_id: str | None = None
    created_by: str | None = None


class NoteUpdateRequest(BaseModel):
    """Payload for updating a shared note."""

    content: str | None = None
    tags: list[str] | None = None


class NoteDeleteResponse(BaseModel):
    """Deletion response."""

    note_id: str
    deleted: bool


def _normalize_symbol(value: str) -> str:
    normalized = (value or "").strip().upper()
    if not normalized:
        raise HTTPException(status_code=400, detail="company_symbol is required")
    return normalized


def _normalize_content(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="content is required")
    return normalized


def _normalize_tags(value: list[str] | None) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for row in value or []:
        tag = str(row).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return fallback


def _to_note(document: dict[str, Any]) -> AnalysisNote:
    cleaned = dict(document)
    cleaned.pop("_id", None)
    now = datetime.now(UTC)
    cleaned["created_at"] = _coerce_datetime(cleaned.get("created_at"), now)
    cleaned["updated_at"] = _coerce_datetime(cleaned.get("updated_at"), cleaned["created_at"])
    return AnalysisNote.model_validate(cleaned)


async def _index_note(request: Request, note: AnalysisNote) -> None:
    vector_repo = getattr(request.app.state, "vector_repo", None)
    if vector_repo is None:
        return
    metadata: dict[str, Any] = {
        "source": "analyst_note",
        "note_id": note.note_id,
        "company_symbol": note.company_symbol,
        "company_name": note.company_name,
        "created_by": note.created_by,
        "created_at": note.created_at,
        "investigation_id": note.investigation_id,
        "report_id": note.report_id,
        "tags": ",".join(note.tags),
    }
    try:
        await vector_repo.delete_document(note.note_id)
        await vector_repo.add_document(note.note_id, note.content, metadata)
    except Exception:  # noqa: BLE001
        return


async def _delete_note_index(request: Request, note_id: str) -> None:
    vector_repo = getattr(request.app.state, "vector_repo", None)
    if vector_repo is None:
        return
    try:
        await vector_repo.delete_document(note_id)
    except Exception:  # noqa: BLE001
        return


def _db(request: Request) -> Any:
    db = getattr(request.app.state, "mongo_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return db


@router.post("/", response_model=AnalysisNote, status_code=201)
async def create_note(
    request: Request,
    payload: NoteCreateRequest,
) -> AnalysisNote:
    """Create and persist a shared note."""
    note = AnalysisNote(
        company_symbol=_normalize_symbol(payload.company_symbol),
        company_name=_normalize_optional(payload.company_name) or "",
        content=_normalize_content(payload.content),
        tags=_normalize_tags(payload.tags),
        investigation_id=_normalize_optional(payload.investigation_id),
        report_id=_normalize_optional(payload.report_id),
        created_by=_normalize_optional(payload.created_by) or "analyst",
    )
    db = _db(request)
    await db["notes"].insert_one(note.model_dump())
    await _index_note(request, note)
    return note


@router.get("/", response_model=NoteListResponse)
async def list_notes(
    request: Request,
    company: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NoteListResponse:
    """List shared notes with optional company/tag filtering."""
    query: dict[str, Any] = {}
    if company:
        query["company_symbol"] = _normalize_symbol(company)
    if tag:
        query["tags"] = tag.strip().lower()

    db = _db(request)
    total = int(await db["notes"].count_documents(query))
    cursor = db["notes"].find(query).sort("updated_at", -1).skip(offset).limit(limit)
    items: list[AnalysisNote] = []
    async for row in cursor:
        items.append(_to_note(row))
    return NoteListResponse(items=items, total=total)


@router.get("/{note_id}", response_model=AnalysisNote)
async def get_note(
    note_id: str,
    request: Request,
) -> AnalysisNote:
    """Get a note by id."""
    db = _db(request)
    row = await db["notes"].find_one({"note_id": note_id})
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return _to_note(row)


@router.put("/{note_id}", response_model=AnalysisNote)
async def update_note(
    note_id: str,
    request: Request,
    payload: NoteUpdateRequest,
) -> AnalysisNote:
    """Update note content/tags."""
    updates: dict[str, Any] = {}
    if payload.content is not None:
        updates["content"] = _normalize_content(payload.content)
    if payload.tags is not None:
        updates["tags"] = _normalize_tags(payload.tags)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    updates["updated_at"] = datetime.now(UTC)
    db = _db(request)
    result = await db["notes"].update_one({"note_id": note_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")

    row = await db["notes"].find_one({"note_id": note_id})
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")
    note = _to_note(row)
    await _index_note(request, note)
    return note


@router.delete("/{note_id}", response_model=NoteDeleteResponse)
async def delete_note(
    note_id: str,
    request: Request,
) -> NoteDeleteResponse:
    """Delete a note by id."""
    db = _db(request)
    existing = await db["notes"].find_one({"note_id": note_id}, {"note_id": 1, "_id": 0})
    if existing is None:
        raise HTTPException(status_code=404, detail="Note not found")

    await db["notes"].delete_one({"note_id": note_id})
    await _delete_note_index(request, note_id)
    return NoteDeleteResponse(note_id=note_id, deleted=True)
