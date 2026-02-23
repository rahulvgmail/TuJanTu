"""API tests for investigation endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.investigations import router
from src.models.investigation import Investigation, SignificanceLevel


class InMemoryInvestigationRepo:
    def __init__(self) -> None:
        self.items: dict[str, Investigation] = {}

    async def save(self, investigation: Investigation) -> str:
        self.items[investigation.investigation_id] = investigation
        return investigation.investigation_id

    async def get(self, investigation_id: str) -> Investigation | None:
        return self.items.get(investigation_id)

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[Investigation]:
        items = [row for row in self.items.values() if row.company_symbol == company_symbol]
        items.sort(key=lambda row: row.created_at, reverse=True)
        return items[:limit]

    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]:
        del company_symbol
        return []


def build_test_client() -> tuple[TestClient, InMemoryInvestigationRepo]:
    app = FastAPI()
    app.include_router(router)
    repo = InMemoryInvestigationRepo()
    app.state.investigation_repo = repo
    return TestClient(app), repo


def _make_investigation(symbol: str, company_name: str) -> Investigation:
    return Investigation(
        trigger_id=f"trigger-{symbol.lower()}",
        company_symbol=symbol,
        company_name=company_name,
        synthesis=f"{company_name} synthesis",
        significance=SignificanceLevel.MEDIUM,
        is_significant=True,
    )


def test_get_investigation_by_id() -> None:
    client, repo = build_test_client()
    inv = _make_investigation("ABB", "ABB India")
    repo.items[inv.investigation_id] = inv

    response = client.get(f"/api/v1/investigations/{inv.investigation_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["investigation_id"] == inv.investigation_id
    assert payload["company_symbol"] == "ABB"


def test_get_investigation_returns_404_for_unknown_id() -> None:
    client, _ = build_test_client()

    response = client.get("/api/v1/investigations/unknown")

    assert response.status_code == 404


def test_list_investigations_by_company() -> None:
    client, repo = build_test_client()
    a = _make_investigation("BHEL", "BHEL")
    b = _make_investigation("BHEL", "BHEL")
    c = _make_investigation("ABB", "ABB India")
    repo.items[a.investigation_id] = a
    repo.items[b.investigation_id] = b
    repo.items[c.investigation_id] = c

    response = client.get("/api/v1/investigations/company/BHEL", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert {item["company_symbol"] for item in payload["items"]} == {"BHEL"}
