"""API tests for human trigger and trigger status endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.triggers import router
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus


class InMemoryTriggerRepo:
    """Simple in-memory trigger repository for API tests."""

    def __init__(self) -> None:
        self.items: dict[str, TriggerEvent] = {}

    async def save(self, trigger: TriggerEvent) -> str:
        self.items[trigger.trigger_id] = trigger
        return trigger.trigger_id

    async def get(self, trigger_id: str) -> TriggerEvent | None:
        return self.items.get(trigger_id)

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None:
        trigger = self.items[trigger_id]
        trigger.set_status(status, reason)
        self.items[trigger_id] = trigger

    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]:
        pending = [item for item in self.items.values() if item.status == TriggerStatus.PENDING.value]
        pending.sort(key=lambda item: item.created_at)
        return pending[:limit]

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[TriggerEvent]:
        items = [item for item in self.items.values() if item.company_symbol == company_symbol]
        items.sort(key=lambda item: item.created_at)
        return items[:limit]

    async def exists_by_url(self, source_url: str) -> bool:
        return any(item.source_url == source_url for item in self.items.values())

    async def list_recent(
        self,
        limit: int = 20,
        offset: int = 0,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[TriggerEvent]:
        items = list(self.items.values())
        if status is not None:
            items = [item for item in items if item.status == status.value]
        if company_symbol:
            items = [item for item in items if item.company_symbol == company_symbol]
        if source:
            items = [item for item in items if item.source == source]
        if since is not None:
            items = [item for item in items if item.created_at >= since]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[offset : offset + limit]

    async def count(
        self,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> int:
        items = await self.list_recent(
            limit=len(self.items) + 1,
            offset=0,
            status=status,
            company_symbol=company_symbol,
            source=source,
            since=since,
        )
        return len(items)

    async def counts_by_status(self, since: datetime | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items.values():
            if since is not None and item.created_at < since:
                continue
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    async def counts_by_source(self, since: datetime | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items.values():
            if since is not None and item.created_at < since:
                continue
            counts[item.source] = counts.get(item.source, 0) + 1
        return counts


def build_test_client() -> tuple[TestClient, InMemoryTriggerRepo]:
    app = FastAPI()
    app.include_router(router)
    repo = InMemoryTriggerRepo()
    app.state.trigger_repo = repo
    return TestClient(app), repo


def test_create_human_trigger_success() -> None:
    client, repo = build_test_client()

    response = client.post(
        "/api/v1/triggers/human",
        json={"content": "Please investigate this update", "company_symbol": "INOXWIND", "triggered_by": "analyst"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    trigger = repo.items[payload["trigger_id"]]
    assert trigger.source == "human"
    assert trigger.priority == "high"
    assert trigger.status == "pending"
    assert trigger.company_symbol == "INOXWIND"


def test_get_trigger_status() -> None:
    client, repo = build_test_client()
    post = client.post("/api/v1/triggers/human", json={"content": "manual trigger", "company_symbol": "SUZLON"})
    trigger_id = post.json()["trigger_id"]

    response = client.get(f"/api/v1/triggers/{trigger_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trigger_id"] == trigger_id
    assert payload["status"] == "pending"
    assert payload["company_symbol"] == "SUZLON"
    assert trigger_id in repo.items


def test_create_human_trigger_validation_error() -> None:
    client, _ = build_test_client()

    response = client.post("/api/v1/triggers/human", json={"company_symbol": "INOXWIND"})

    assert response.status_code == 422


def test_create_human_trigger_without_company_symbol() -> None:
    client, repo = build_test_client()

    response = client.post("/api/v1/triggers/human", json={"content": "Company not specified"})

    assert response.status_code == 200
    trigger_id = response.json()["trigger_id"]
    assert repo.items[trigger_id].company_symbol is None


def test_list_triggers_with_filters() -> None:
    client, _ = build_test_client()
    first = client.post("/api/v1/triggers/human", json={"content": "One", "company_symbol": "BHEL"}).json()
    second = client.post("/api/v1/triggers/human", json={"content": "Two", "company_symbol": "ABB"}).json()

    response = client.get("/api/v1/triggers", params={"company": "ABB"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["trigger_id"] == second["trigger_id"]
    assert payload["items"][0]["trigger_id"] != first["trigger_id"]


def test_list_triggers_supports_pagination_source_and_since() -> None:
    client, repo = build_test_client()
    now = datetime.now(timezone.utc)

    t1 = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="First",
        company_symbol="INOXWIND",
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=3),
    )
    t1.set_status(TriggerStatus.FILTERED_OUT, "old item")
    t2 = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="Second",
        company_symbol="INOXWIND",
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
    )
    t2.set_status(TriggerStatus.GATE_PASSED, "new item")
    t3 = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        raw_content="Third",
        company_symbol="INOXWIND",
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    t3.set_status(TriggerStatus.GATE_PASSED, "new bse item")
    for trigger in [t1, t2, t3]:
        repo.items[trigger.trigger_id] = trigger

    since = (now - timedelta(days=1)).isoformat()
    response = client.get(
        "/api/v1/triggers",
        params={
            "source": "nse_rss",
            "since": since,
            "status": "gate_passed",
            "limit": 1,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["trigger_id"] == t2.trigger_id


def test_trigger_stats_endpoint_returns_counts_by_status() -> None:
    client, repo = build_test_client()
    a = TriggerEvent(source=TriggerSource.NSE_RSS, raw_content="A")
    b = TriggerEvent(source=TriggerSource.NSE_RSS, raw_content="B")
    c = TriggerEvent(source=TriggerSource.BSE_RSS, raw_content="C")
    a.set_status(TriggerStatus.GATE_PASSED, "pass")
    b.set_status(TriggerStatus.FILTERED_OUT, "filtered")
    c.set_status(TriggerStatus.GATE_PASSED, "pass")
    repo.items[a.trigger_id] = a
    repo.items[b.trigger_id] = b
    repo.items[c.trigger_id] = c

    response = client.get("/api/v1/triggers/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["counts_by_status"]["gate_passed"] == 2
    assert payload["counts_by_status"]["filtered_out"] == 1
    assert payload["counts_by_source"]["nse_rss"] == 2
    assert payload["counts_by_source"]["bse_rss"] == 1


def test_get_trigger_status_can_include_details_and_preview() -> None:
    client, repo = build_test_client()
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="Very long content that should be truncated for preview display",
        company_symbol="SIEMENS",
    )
    trigger.set_status(TriggerStatus.GATE_PASSED, "Gate passed")
    trigger.gate_result = {"passed": True, "reason": "Matched watchlist", "method": "watchlist_filter"}
    repo.items[trigger.trigger_id] = trigger

    response = client.get(
        f"/api/v1/triggers/{trigger.trigger_id}",
        params={"include_details": "true", "include_content_preview": "true", "content_preview_chars": 24},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trigger_id"] == trigger.trigger_id
    assert payload["updated_at"] is not None
    assert payload["status_history"][0]["reason"] == "Gate passed"
    assert payload["gate_result"]["method"] == "watchlist_filter"
    assert payload["raw_content_preview"].endswith("...")
