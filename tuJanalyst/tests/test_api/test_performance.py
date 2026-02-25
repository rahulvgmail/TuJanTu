"""API tests for performance tracking endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.performance import router
from src.models.investigation import MarketDataSnapshot


def _build_app(*, with_db: bool = True, market_data_tool: object | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.market_data_tool = market_data_tool
    if with_db:
        client = AsyncMongoMockClient()
        app.state.mongo_db = client["test_db"]
    return app


def _seed_performance_data(db, now: datetime) -> None:
    asyncio.run(
        db["assessments"].insert_many(
            [
                {
                    "assessment_id": "a-buy",
                    "investigation_id": "inv-buy-1",
                    "company_symbol": "BUYCO",
                    "company_name": "BuyCo",
                    "recommendation_changed": True,
                    "new_recommendation": "buy",
                    "timeframe": "short_term",
                    "confidence": 0.82,
                    "created_at": now - timedelta(days=40),
                },
                {
                    "assessment_id": "a-sell",
                    "investigation_id": "inv-sell-1",
                    "company_symbol": "SELLCO",
                    "company_name": "SellCo",
                    "recommendation_changed": True,
                    "new_recommendation": "sell",
                    "timeframe": "short_term",
                    "confidence": 0.77,
                    "created_at": now - timedelta(days=20),
                },
                {
                    "assessment_id": "a-hold",
                    "investigation_id": "inv-hold-1",
                    "company_symbol": "HOLDCO",
                    "company_name": "HoldCo",
                    "recommendation_changed": True,
                    "new_recommendation": "hold",
                    "timeframe": "medium_term",
                    "confidence": 0.64,
                    "created_at": now - timedelta(days=10),
                },
                {
                    "assessment_id": "a-ignored",
                    "investigation_id": "inv-ignored-1",
                    "company_symbol": "IGNORED",
                    "company_name": "Ignored",
                    "recommendation_changed": False,
                    "new_recommendation": "buy",
                    "timeframe": "short_term",
                    "confidence": 0.5,
                    "created_at": now - timedelta(days=5),
                },
            ]
        )
    )

    asyncio.run(
        db["investigations"].insert_many(
            [
                {
                    "investigation_id": "inv-buy-1",
                    "company_symbol": "BUYCO",
                    "created_at": now - timedelta(days=40),
                    "market_data": {"current_price": 100.0},
                },
                {
                    "investigation_id": "inv-buy-2",
                    "company_symbol": "BUYCO",
                    "created_at": now - timedelta(days=1),
                    "market_data": {"current_price": 120.0},
                },
                {
                    "investigation_id": "inv-sell-1",
                    "company_symbol": "SELLCO",
                    "created_at": now - timedelta(days=20),
                    "market_data": {"current_price": 200.0},
                },
                {
                    "investigation_id": "inv-sell-2",
                    "company_symbol": "SELLCO",
                    "created_at": now - timedelta(days=2),
                    "market_data": {"current_price": 180.0},
                },
                {
                    "investigation_id": "inv-hold-1",
                    "company_symbol": "HOLDCO",
                    "created_at": now - timedelta(days=10),
                    "market_data": {"current_price": 150.0},
                },
                {
                    "investigation_id": "inv-hold-2",
                    "company_symbol": "HOLDCO",
                    "created_at": now - timedelta(days=1),
                    "market_data": {"current_price": 155.0},
                },
            ]
        )
    )


def test_performance_recommendations_uses_historical_prices_by_default() -> None:
    app = _build_app(with_db=True)
    now = datetime.now(UTC)
    _seed_performance_data(app.state.mongo_db, now)
    client = TestClient(app)

    response = client.get("/api/v1/performance/recommendations", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 3

    hold_row = payload["items"][0]
    assert hold_row["assessment_id"] == "a-hold"
    assert hold_row["price_at_recommendation"] == 150.0
    assert hold_row["price_now"] == 155.0
    assert hold_row["return_pct"] == 3.3333
    assert hold_row["status"] == "within_timeframe"
    assert hold_row["outcome"] == "neutral"

    sell_row = payload["items"][1]
    assert sell_row["assessment_id"] == "a-sell"
    assert sell_row["return_pct"] == -10.0
    assert sell_row["status"] == "within_timeframe"
    assert sell_row["outcome"] == "win"

    buy_row = payload["items"][2]
    assert buy_row["assessment_id"] == "a-buy"
    assert buy_row["return_pct"] == 20.0
    assert buy_row["status"] == "expired"
    assert buy_row["outcome"] == "win"


def test_performance_summary_aggregates_core_metrics() -> None:
    app = _build_app(with_db=True)
    now = datetime.now(UTC)
    _seed_performance_data(app.state.mongo_db, now)
    client = TestClient(app)

    response = client.get("/api/v1/performance/summary", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_recommendations"] == 3
    assert payload["buy_recommendations"] == 1
    assert payload["sell_recommendations"] == 1
    assert payload["hold_recommendations"] == 1
    assert payload["evaluated_recommendations"] == 2
    assert payload["wins"] == 2
    assert payload["win_rate"] == 1.0
    assert payload["avg_return_buy"] == 20.0
    assert payload["avg_return_sell"] == -10.0
    assert payload["best_call"]["assessment_id"] == "a-buy"
    assert payload["worst_call"]["assessment_id"] == "a-sell"


class _FakeMarketDataTool:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices

    async def get_snapshot(self, symbol: str) -> MarketDataSnapshot:
        return MarketDataSnapshot(current_price=self.prices.get(symbol))


def test_performance_recommendations_can_use_live_prices() -> None:
    app = _build_app(
        with_db=True,
        market_data_tool=_FakeMarketDataTool({"BUYCO": 130.0, "SELLCO": 170.0, "HOLDCO": 165.0}),
    )
    now = datetime.now(UTC)
    _seed_performance_data(app.state.mongo_db, now)
    client = TestClient(app)

    response = client.get(
        "/api/v1/performance/recommendations",
        params={"limit": 10, "include_live_price": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    rows_by_id = {row["assessment_id"]: row for row in payload["items"]}
    assert rows_by_id["a-buy"]["price_now"] == 130.0
    assert rows_by_id["a-sell"]["price_now"] == 170.0
    assert rows_by_id["a-hold"]["price_now"] == 165.0

