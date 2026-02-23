"""API tests for report endpoints and feedback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.reports import router
from src.models.report import AnalysisReport


class InMemoryReportRepo:
    def __init__(self) -> None:
        self.items: dict[str, AnalysisReport] = {}

    async def save(self, report: AnalysisReport) -> str:
        self.items[report.report_id] = report
        return report.report_id

    async def get(self, report_id: str) -> AnalysisReport | None:
        return self.items.get(report_id)

    async def get_recent(self, limit: int = 20) -> list[AnalysisReport]:
        items = list(self.items.values())
        items.sort(key=lambda row: row.created_at, reverse=True)
        return items[:limit]

    async def update_feedback(
        self,
        report_id: str,
        rating: int | None = None,
        comment: str | None = None,
        by: str | None = None,
    ) -> None:
        report = self.items[report_id]
        report.feedback_rating = rating
        report.feedback_comment = comment
        report.feedback_by = by
        report.feedback_at = datetime.now(timezone.utc)
        self.items[report_id] = report


def build_test_client() -> tuple[TestClient, InMemoryReportRepo]:
    app = FastAPI()
    app.include_router(router)
    repo = InMemoryReportRepo()
    app.state.report_repo = repo
    return TestClient(app), repo


def _make_report(symbol: str, created_offset_minutes: int = 0) -> AnalysisReport:
    return AnalysisReport(
        assessment_id=f"a-{symbol}",
        investigation_id=f"i-{symbol}",
        trigger_id=f"t-{symbol}",
        company_symbol=symbol,
        company_name=f"{symbol} Ltd",
        title=f"{symbol} report",
        executive_summary="Summary",
        report_body="# Body",
        recommendation_summary="HOLD (Confidence: 50%, Timeframe: medium_term)",
        created_at=datetime.now(timezone.utc) + timedelta(minutes=created_offset_minutes),
    )


def test_list_reports_returns_recent_reports() -> None:
    client, repo = build_test_client()
    older = _make_report("ABB", created_offset_minutes=-10)
    newer = _make_report("BHEL", created_offset_minutes=1)
    repo.items[older.report_id] = older
    repo.items[newer.report_id] = newer

    response = client.get("/api/v1/reports", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["report_id"] == newer.report_id
    assert payload["items"][1]["report_id"] == older.report_id


def test_get_report_by_id() -> None:
    client, repo = build_test_client()
    report = _make_report("SIEMENS")
    repo.items[report.report_id] = report

    response = client.get(f"/api/v1/reports/{report.report_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == report.report_id
    assert payload["company_symbol"] == "SIEMENS"


def test_submit_report_feedback_updates_report() -> None:
    client, repo = build_test_client()
    report = _make_report("SUZLON")
    repo.items[report.report_id] = report

    response = client.post(
        f"/api/v1/reports/{report.report_id}/feedback",
        json={"rating": "up", "comment": "Useful", "by": "analyst"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == report.report_id
    assert payload["feedback_rating"] == 1
    assert payload["feedback_comment"] == "Useful"
    assert payload["feedback_by"] == "analyst"


def test_submit_report_feedback_returns_404_for_unknown_report() -> None:
    client, _ = build_test_client()

    response = client.post(
        "/api/v1/reports/unknown/feedback",
        json={"rating": "down", "comment": "Not useful"},
    )

    assert response.status_code == 404
