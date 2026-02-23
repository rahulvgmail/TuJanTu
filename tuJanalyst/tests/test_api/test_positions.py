"""API tests for position endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.positions import router
from src.models.company import CompanyPosition
from src.models.decision import Recommendation


class InMemoryPositionRepo:
    def __init__(self) -> None:
        self.items: dict[str, CompanyPosition] = {}

    async def get_position(self, company_symbol: str) -> CompanyPosition | None:
        return self.items.get(company_symbol)

    async def list_positions(self, limit: int = 200) -> list[CompanyPosition]:
        items = list(self.items.values())
        items.sort(key=lambda row: row.updated_at, reverse=True)
        return items[:limit]

    async def upsert_position(self, position: CompanyPosition) -> None:
        self.items[position.company_symbol] = position


def build_test_client() -> tuple[TestClient, InMemoryPositionRepo]:
    app = FastAPI()
    app.include_router(router)
    repo = InMemoryPositionRepo()
    app.state.position_repo = repo
    return TestClient(app), repo


def _make_position(symbol: str, rec: Recommendation) -> CompanyPosition:
    return CompanyPosition(
        company_symbol=symbol,
        company_name=f"{symbol} Ltd",
        current_recommendation=rec,
        recommendation_basis="Initial thesis",
        total_investigations=3,
    )


def test_list_positions_returns_current_positions() -> None:
    client, repo = build_test_client()
    repo.items["ABB"] = _make_position("ABB", Recommendation.BUY)
    repo.items["BHEL"] = _make_position("BHEL", Recommendation.HOLD)

    response = client.get("/api/v1/positions", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert {item["company_symbol"] for item in payload["items"]} == {"ABB", "BHEL"}


def test_get_position_by_symbol() -> None:
    client, repo = build_test_client()
    repo.items["SIEMENS"] = _make_position("SIEMENS", Recommendation.SELL)

    response = client.get("/api/v1/positions/SIEMENS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_symbol"] == "SIEMENS"
    assert payload["current_recommendation"] == Recommendation.SELL.value


def test_get_position_returns_404_for_unknown_symbol() -> None:
    client, _ = build_test_client()

    response = client.get("/api/v1/positions/UNKNOWN")

    assert response.status_code == 404
