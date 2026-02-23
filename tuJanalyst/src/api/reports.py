"""API endpoints for analysis reports and feedback."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from src.models.report import AnalysisReport
from src.repositories.base import ReportRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportListResponse(BaseModel):
    """List response for recent analysis reports."""

    items: list[AnalysisReport]
    total: int


class ReportFeedbackRequest(BaseModel):
    """Thumbs feedback payload for a report."""

    rating: Literal["up", "down"]
    comment: str | None = None
    by: str | None = None


class ReportFeedbackResponse(BaseModel):
    """Feedback update response."""

    report_id: str
    feedback_rating: int | None = None
    feedback_comment: str | None = None
    feedback_by: str | None = None


def get_report_repo(request: Request) -> ReportRepository:
    """Get report repository from app state."""
    repository = getattr(request.app.state, "report_repo", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="Report repository is not configured")
    return repository


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    report_repo: Annotated[ReportRepository, Depends(get_report_repo)],
    limit: int = Query(default=20, ge=1, le=100),
) -> ReportListResponse:
    """Return recent reports sorted by latest created timestamp."""
    items = await report_repo.get_recent(limit=limit)
    return ReportListResponse(items=items, total=len(items))


@router.get("/{report_id}", response_model=AnalysisReport)
async def get_report(
    report_id: str,
    report_repo: Annotated[ReportRepository, Depends(get_report_repo)],
) -> AnalysisReport:
    """Return full report details by report ID."""
    report = await report_repo.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/{report_id}/feedback", response_model=ReportFeedbackResponse)
async def submit_report_feedback(
    report_id: str,
    payload: ReportFeedbackRequest,
    report_repo: Annotated[ReportRepository, Depends(get_report_repo)],
) -> ReportFeedbackResponse:
    """Submit thumbs feedback for a report."""
    existing = await report_repo.get(report_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Report not found")

    rating_value = 1 if payload.rating == "up" else -1
    await report_repo.update_feedback(
        report_id,
        rating=rating_value,
        comment=payload.comment,
        by=payload.by,
    )
    updated = await report_repo.get(report_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Report not found after feedback update")

    return ReportFeedbackResponse(
        report_id=updated.report_id,
        feedback_rating=updated.feedback_rating,
        feedback_comment=updated.feedback_comment,
        feedback_by=updated.feedback_by,
    )
