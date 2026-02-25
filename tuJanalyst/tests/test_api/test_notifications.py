"""API tests for in-app notification feed endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.notifications import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.mongo_db = AsyncMongoMockClient()["test_db"]
    return app


def _seed_data(app: FastAPI, now: datetime) -> None:
    asyncio.run(
        app.state.mongo_db["reports"].insert_many(
            [
                {
                    "report_id": "rep-1",
                    "company_symbol": "SUZLON",
                    "company_name": "Suzlon Energy",
                    "recommendation_summary": "BUY (Confidence: 80%)",
                    "created_at": now - timedelta(minutes=10),
                },
                {
                    "report_id": "rep-old",
                    "company_symbol": "BHEL",
                    "company_name": "BHEL",
                    "recommendation_summary": "HOLD",
                    "created_at": now - timedelta(days=2),
                },
            ]
        )
    )
    asyncio.run(
        app.state.mongo_db["investigations"].insert_many(
            [
                {
                    "investigation_id": "inv-1",
                    "company_symbol": "ABB",
                    "company_name": "ABB India",
                    "significance": "high",
                    "created_at": now - timedelta(minutes=5),
                },
                {
                    "investigation_id": "inv-old",
                    "company_symbol": "SIEMENS",
                    "company_name": "Siemens India",
                    "significance": "low",
                    "created_at": now - timedelta(days=3),
                },
            ]
        )
    )


def test_notification_feed_merges_reports_and_investigations_since_window() -> None:
    app = _build_app()
    now = datetime.now(UTC)
    _seed_data(app, now)
    client = TestClient(app)

    response = client.get(
        "/api/v1/notifications/feed",
        params={"since": (now - timedelta(hours=2)).isoformat(), "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["kind"] for item in payload["items"]] == ["investigation_completed", "report_created"]
    assert payload["items"][0]["entity_id"] == "inv-1"
    assert payload["items"][1]["entity_id"] == "rep-1"


def test_notification_feed_can_filter_to_reports_only() -> None:
    app = _build_app()
    now = datetime.now(UTC)
    _seed_data(app, now)
    client = TestClient(app)

    response = client.get(
        "/api/v1/notifications/feed",
        params={
            "since": (now - timedelta(hours=2)).isoformat(),
            "include_reports": "true",
            "include_investigations": "false",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["kind"] == "report_created"
    assert payload["items"][0]["entity_id"] == "rep-1"
