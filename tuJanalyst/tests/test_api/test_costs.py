"""API tests for cost summary endpoint."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.costs import router


def _build_app(with_db: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.settings = SimpleNamespace(web_search_provider="tavily")
    if with_db:
        client = AsyncMongoMockClient()
        app.state.mongo_db = client["test_db"]
    return app


def test_cost_summary_aggregates_llm_and_web_search_costs() -> None:
    app = _build_app(with_db=True)
    db = app.state.mongo_db
    now = datetime.now(UTC)

    asyncio.run(
        db["investigations"].insert_many(
            [
                {
                    "investigation_id": "inv-1",
                    "created_at": now,
                    "llm_model_used": "claude-3-5-sonnet",
                    "total_input_tokens": 1000,
                    "total_output_tokens": 500,
                    "web_search_calls": 3,
                },
                {
                    "investigation_id": "inv-2",
                    "created_at": now,
                    "llm_model_used": "claude-3-haiku",
                    "total_input_tokens": 2000,
                    "total_output_tokens": 100,
                    "web_search_calls": 1,
                },
            ]
        )
    )
    asyncio.run(
        db["assessments"].insert_one(
            {
                "assessment_id": "assess-1",
                "created_at": now,
                "llm_model_used": "claude-3-5-sonnet",
                "total_input_tokens": 500,
                "total_output_tokens": 200,
            }
        )
    )
    asyncio.run(
        db["reports"].insert_many(
            [
                {"report_id": "r-1", "created_at": now, "delivery_status": "generated"},
                {"report_id": "r-2", "created_at": now, "delivery_status": "delivered"},
                {"report_id": "r-3", "created_at": now, "delivery_status": "delivery_failed"},
            ]
        )
    )

    client = TestClient(app)
    response = client.get("/api/v1/costs/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_input_tokens"] == 3500
    assert payload["llm_output_tokens"] == 800
    assert payload["llm_estimated_cost_usd"] == 0.017
    assert payload["web_search_calls"] == 4
    assert payload["web_search_estimated_cost_usd"] == 0.02
    assert payload["total_estimated_cost_usd"] == 0.037
    assert payload["completed_reports"] == 2
    assert payload["cost_per_completed_report_usd"] == 0.0185


def test_cost_summary_rejects_invalid_time_window() -> None:
    app = _build_app(with_db=True)
    client = TestClient(app)
    now = datetime.now(UTC)
    response = client.get(
        "/api/v1/costs/summary",
        params={
            "since": now.isoformat(),
            "until": (now - timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "'until' must be greater than or equal to 'since'"
