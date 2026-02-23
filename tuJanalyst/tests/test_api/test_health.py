"""API tests for health and operational stats endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.health import router


def _build_app(with_db: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.scheduler = None
    app.state.vector_repo = None
    if with_db:
        client = AsyncMongoMockClient()
        app.state.mongo_db = client["test_db"]
    return app


class _FakeJob:
    def __init__(self, job_id: str, next_run_time: datetime | None):
        self.id = job_id
        self.next_run_time = next_run_time


class _FakeScheduler:
    def __init__(self, running: bool, jobs: list[_FakeJob]):
        self.running = running
        self._jobs = jobs

    def get_jobs(self) -> list[_FakeJob]:
        return self._jobs


def test_health_connected_when_db_available() -> None:
    app = _build_app(with_db=True)
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["mongodb"] == "connected"
    assert payload["scheduler"] == "not_initialized"
    assert payload["scheduler_jobs"] == {}


def test_health_unhealthy_without_db() -> None:
    app = _build_app(with_db=False)
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unhealthy"
    assert payload["mongodb"] == "disconnected"
    assert payload["scheduler_jobs"] == {}


def test_health_stats_counts() -> None:
    app = _build_app(with_db=True)
    db = app.state.mongo_db
    now = datetime.now(timezone.utc)

    asyncio.run(
        db["triggers"].insert_many(
            [
                {"trigger_id": "t1", "status": "gate_passed", "created_at": now},
                {"trigger_id": "t2", "status": "pending", "created_at": now},
                {"trigger_id": "t3", "status": "gate_passed", "created_at": now},
            ]
        )
    )

    client = TestClient(app)
    response = client.get("/api/v1/health/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["triggers_today"] == 3
    assert payload["status_counts"]["gate_passed"] == 2
    assert payload["status_counts"]["pending"] == 1
    assert payload["gate_pass_rate"] == 0.6667


def test_health_reports_scheduler_job_next_runs() -> None:
    app = _build_app(with_db=True)
    next_run = datetime.now(timezone.utc)
    app.state.scheduler = _FakeScheduler(
        running=True,
        jobs=[
            _FakeJob("rss_poller", next_run),
            _FakeJob("trigger_processor", None),
        ],
    )
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler"] == "running"
    assert payload["scheduler_jobs"]["rss_poller"] == next_run.isoformat()
    assert payload["scheduler_jobs"]["trigger_processor"] is None
