"""API tests for watchlist admin endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.watchlist import router
from src.models.company import Company, Sector, WatchlistConfig


def _build_watchlist() -> WatchlistConfig:
    return WatchlistConfig(
        sectors=[
            Sector(
                name="Capital Goods - Electrical Equipment",
                keywords=["order", "earnings"],
            )
        ],
        companies=[
            Company(
                symbol="SUZLON",
                name="Suzlon Energy",
                priority="high",
                aliases=["Suzlon"],
                monitoring_active=True,
            ),
            Company(
                symbol="ABB",
                name="ABB India",
                priority="normal",
                aliases=["ABB"],
                monitoring_active=False,
            ),
        ],
        global_keywords=["sebi"],
    )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.mongo_db = AsyncMongoMockClient()["test_db"]
    app.state.watchlist = _build_watchlist()
    app.state.watchlist_path = "config/watchlist.yaml"
    app.state.watchlist_loaded_at = datetime.now(UTC)
    return app


def test_watchlist_overview_includes_runtime_counts_and_recommendations() -> None:
    app = _build_app()
    now = datetime.now(UTC)
    asyncio.run(
        app.state.mongo_db["triggers"].insert_many(
            [
                {
                    "trigger_id": "t-old",
                    "company_symbol": "SUZLON",
                    "created_at": now - timedelta(days=1),
                },
                {
                    "trigger_id": "t-new",
                    "company_symbol": "SUZLON",
                    "created_at": now - timedelta(hours=2),
                },
            ]
        )
    )
    asyncio.run(
        app.state.mongo_db["investigations"].insert_many(
            [
                {"investigation_id": "i-1", "company_symbol": "SUZLON"},
                {"investigation_id": "i-2", "company_symbol": "SUZLON"},
                {"investigation_id": "i-3", "company_symbol": "ABB"},
            ]
        )
    )
    asyncio.run(
        app.state.mongo_db["positions"].insert_one(
            {
                "company_symbol": "SUZLON",
                "current_recommendation": "buy",
            }
        )
    )
    client = TestClient(app)

    response = client.get("/api/v1/watchlist/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist_path"] == "config/watchlist.yaml"
    assert payload["watchlist_loaded_at"] is not None
    assert len(payload["companies"]) == 2
    assert len(payload["sectors"]) == 1
    assert payload["sectors"][0]["companies_count"] == 2

    companies = {row["symbol"]: row for row in payload["companies"]}
    assert companies["SUZLON"]["status"] == "active"
    assert companies["SUZLON"]["last_trigger"] is not None
    assert companies["SUZLON"]["total_investigations"] == 2
    assert companies["SUZLON"]["current_recommendation"] == "buy"
    assert companies["ABB"]["status"] == "paused"
    assert companies["ABB"]["total_investigations"] == 1
    assert companies["ABB"]["current_recommendation"] == "none"


def test_agent_policy_endpoint_reads_config_file(tmp_path: Path) -> None:
    app = _build_app()
    policy_path = tmp_path / "agent_access_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "domains": ["triggers", "reports"],
                "actions": ["read", "update"],
                "agents": [
                    {
                        "agent": "gate_classifier",
                        "permissions": [{"domain": "triggers", "actions": ["read"]}],
                    },
                    {
                        "agent": "report_generator",
                        "permissions": [{"domain": "reports", "actions": ["create", "update"]}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    app.state.agent_policy_path = str(policy_path)
    client = TestClient(app)

    response = client.get("/api/v1/watchlist/agent-policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "config_file"
    assert payload["exists"] is True
    assert payload["policy_path"] == str(policy_path)
    assert payload["domains"] == ["triggers", "reports"]
    assert payload["actions"] == ["read", "update"]
    assert payload["editable_in_ui"] is False
    assert payload["last_loaded_at"] is not None
    assert {"agent": "gate_classifier", "domain": "triggers", "actions": ["read"]} in payload["permissions"]


def test_agent_policy_endpoint_returns_placeholder_when_file_missing() -> None:
    app = _build_app()
    app.state.agent_policy_path = "/tmp/not-present-policy.yaml"
    client = TestClient(app)

    response = client.get("/api/v1/watchlist/agent-policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is False
    assert payload["editable_in_ui"] is False
    assert payload["domains"] == ["triggers", "documents", "reports", "notes", "users", "licenses"]
    assert payload["actions"] == ["read", "create", "update", "delete"]
    assert payload["permissions"] == []
