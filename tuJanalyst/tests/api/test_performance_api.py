"""Tests for Phase 3 performance API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.performance import router
from src.models.performance import RecommendationOutcome


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


def _make_outcome(
    *,
    assessment_id: str = "assess-1",
    company_symbol: str = "AAPL",
    company_name: str = "Apple Inc.",
    recommendation: str = "buy",
    confidence: float = 0.85,
    timeframe: str = "medium_term",
    entry_price: float = 150.0,
    entry_date: datetime | None = None,
    is_closed: bool = False,
    outcome: str | None = None,
    return_3m_pct: float | None = None,
    outcome_id: str | None = None,
) -> RecommendationOutcome:
    now = entry_date or datetime.now(timezone.utc)
    kwargs: dict[str, Any] = dict(
        assessment_id=assessment_id,
        company_symbol=company_symbol,
        company_name=company_name,
        recommendation=recommendation,
        confidence=confidence,
        timeframe=timeframe,
        entry_price=entry_price,
        entry_date=now,
        is_closed=is_closed,
        outcome=outcome,
        return_3m_pct=return_3m_pct,
    )
    if outcome_id is not None:
        kwargs["outcome_id"] = outcome_id
    return RecommendationOutcome(**kwargs)


class FakePerformanceRepo:
    """In-memory fake implementing the subset of MongoPerformanceRepository used by the API."""

    def __init__(self, outcomes: list[RecommendationOutcome] | None = None) -> None:
        self._outcomes: list[RecommendationOutcome] = list(outcomes or [])

    async def get_all(self, limit: int = 100) -> list[RecommendationOutcome]:
        return self._outcomes[:limit]

    async def get_open(self) -> list[RecommendationOutcome]:
        return [o for o in self._outcomes if not o.is_closed]

    async def get_by_company(self, symbol: str) -> list[RecommendationOutcome]:
        return [o for o in self._outcomes if o.company_symbol == symbol]


class FakePerformanceTracker:
    """In-memory fake implementing PerformanceTracker.get_summary()."""

    def __init__(self, summary: dict[str, Any] | None = None) -> None:
        self._summary = summary or {
            "total_recommendations": 0,
            "open_recommendations": 0,
            "closed_recommendations": 0,
            "wins": 0,
            "losses": 0,
            "neutrals": 0,
            "win_rate": 0.0,
            "avg_return_buy": None,
            "avg_return_sell": None,
            "avg_return_hold": None,
            "by_recommendation": {},
        }

    async def get_summary(self) -> dict[str, Any]:
        return self._summary


# ---------------------------------------------------------------------------
# App / client helpers
# ---------------------------------------------------------------------------


def _create_app(
    *,
    repo: FakePerformanceRepo | None = None,
    tracker: FakePerformanceTracker | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if repo is not None:
        app.state.performance_repo = repo
    if tracker is not None:
        app.state.performance_tracker = tracker
    return app


def _client(
    *,
    repo: FakePerformanceRepo | None = None,
    tracker: FakePerformanceTracker | None = None,
) -> TestClient:
    return TestClient(_create_app(repo=repo, tracker=tracker))


# ---------------------------------------------------------------------------
# /api/v1/performance/outcomes
# ---------------------------------------------------------------------------


class TestListOutcomes:
    """Tests for GET /api/v1/performance/outcomes."""

    def test_returns_503_when_repo_not_configured(self) -> None:
        client = _client()
        resp = client.get("/api/v1/performance/outcomes")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_returns_empty_list(self) -> None:
        client = _client(repo=FakePerformanceRepo())
        resp = client.get("/api/v1/performance/outcomes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_all_outcomes(self) -> None:
        outcomes = [
            _make_outcome(assessment_id="a1", company_symbol="AAPL"),
            _make_outcome(assessment_id="a2", company_symbol="GOOG"),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/outcomes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        symbols = {item["company_symbol"] for item in body["items"]}
        assert symbols == {"AAPL", "GOOG"}

    def test_filter_by_symbol(self) -> None:
        outcomes = [
            _make_outcome(assessment_id="a1", company_symbol="AAPL"),
            _make_outcome(assessment_id="a2", company_symbol="GOOG"),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/outcomes", params={"symbol": "GOOG"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["company_symbol"] == "GOOG"

    def test_filter_is_closed_true(self) -> None:
        outcomes = [
            _make_outcome(assessment_id="a1", is_closed=True, outcome="win"),
            _make_outcome(assessment_id="a2", is_closed=False),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/outcomes", params={"is_closed": "true"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["is_closed"] is True

    def test_filter_is_closed_false(self) -> None:
        outcomes = [
            _make_outcome(assessment_id="a1", is_closed=True, outcome="win"),
            _make_outcome(assessment_id="a2", is_closed=False),
            _make_outcome(assessment_id="a3", is_closed=False),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/outcomes", params={"is_closed": "false"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(item["is_closed"] is False for item in body["items"])

    def test_limit_parameter(self) -> None:
        outcomes = [_make_outcome(assessment_id=f"a{i}") for i in range(10)]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/outcomes", params={"limit": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_limit_validation_rejects_zero(self) -> None:
        client = _client(repo=FakePerformanceRepo())
        resp = client.get("/api/v1/performance/outcomes", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_validation_rejects_over_max(self) -> None:
        client = _client(repo=FakePerformanceRepo())
        resp = client.get("/api/v1/performance/outcomes", params={"limit": 501})
        assert resp.status_code == 422

    def test_outcome_fields_serialized(self) -> None:
        outcome = _make_outcome(
            assessment_id="a1",
            company_symbol="TSLA",
            company_name="Tesla Inc.",
            recommendation="sell",
            confidence=0.72,
            timeframe="short_term",
            entry_price=200.0,
            is_closed=True,
            outcome="win",
            return_3m_pct=-12.5,
        )
        client = _client(repo=FakePerformanceRepo([outcome]))
        resp = client.get("/api/v1/performance/outcomes")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["assessment_id"] == "a1"
        assert item["company_symbol"] == "TSLA"
        assert item["company_name"] == "Tesla Inc."
        assert item["recommendation"] == "sell"
        assert item["confidence"] == 0.72
        assert item["timeframe"] == "short_term"
        assert item["entry_price"] == 200.0
        assert item["is_closed"] is True
        assert item["outcome"] == "win"
        assert item["return_3m_pct"] == -12.5


# ---------------------------------------------------------------------------
# /api/v1/performance/outcomes/summary
# ---------------------------------------------------------------------------


class TestOutcomeSummary:
    """Tests for GET /api/v1/performance/outcomes/summary."""

    def test_returns_503_when_tracker_not_configured(self) -> None:
        client = _client()
        resp = client.get("/api/v1/performance/outcomes/summary")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_returns_empty_summary(self) -> None:
        client = _client(tracker=FakePerformanceTracker())
        resp = client.get("/api/v1/performance/outcomes/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_recommendations"] == 0
        assert body["open_recommendations"] == 0
        assert body["closed_recommendations"] == 0
        assert body["wins"] == 0
        assert body["losses"] == 0
        assert body["neutrals"] == 0
        assert body["win_rate"] == 0.0
        assert body["avg_return_buy"] is None
        assert body["avg_return_sell"] is None
        assert body["avg_return_hold"] is None
        assert body["by_recommendation"] == {}

    def test_returns_populated_summary(self) -> None:
        summary = {
            "total_recommendations": 10,
            "open_recommendations": 3,
            "closed_recommendations": 7,
            "wins": 4,
            "losses": 2,
            "neutrals": 1,
            "win_rate": 0.5714,
            "avg_return_buy": 8.25,
            "avg_return_sell": -3.1,
            "avg_return_hold": 0.5,
            "by_recommendation": {"buy": 5, "sell": 3, "hold": 2},
        }
        client = _client(tracker=FakePerformanceTracker(summary))
        resp = client.get("/api/v1/performance/outcomes/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_recommendations"] == 10
        assert body["open_recommendations"] == 3
        assert body["closed_recommendations"] == 7
        assert body["wins"] == 4
        assert body["losses"] == 2
        assert body["neutrals"] == 1
        assert body["win_rate"] == 0.5714
        assert body["avg_return_buy"] == 8.25
        assert body["avg_return_sell"] == -3.1
        assert body["avg_return_hold"] == 0.5
        assert body["by_recommendation"] == {"buy": 5, "sell": 3, "hold": 2}


# ---------------------------------------------------------------------------
# /api/v1/performance/company/{company_symbol}
# ---------------------------------------------------------------------------


class TestOutcomesByCompany:
    """Tests for GET /api/v1/performance/company/{company_symbol}."""

    def test_returns_503_when_repo_not_configured(self) -> None:
        client = _client()
        resp = client.get("/api/v1/performance/company/AAPL")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_returns_empty_for_unknown_symbol(self) -> None:
        client = _client(repo=FakePerformanceRepo())
        resp = client.get("/api/v1/performance/company/ZZZZ")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_outcomes_for_matching_symbol(self) -> None:
        outcomes = [
            _make_outcome(assessment_id="a1", company_symbol="AAPL"),
            _make_outcome(assessment_id="a2", company_symbol="AAPL"),
            _make_outcome(assessment_id="a3", company_symbol="GOOG"),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        resp = client.get("/api/v1/performance/company/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert all(item["company_symbol"] == "AAPL" for item in body["items"])

    def test_symbol_is_case_sensitive_passthrough(self) -> None:
        """The endpoint passes the symbol to the repo as-is."""
        outcomes = [
            _make_outcome(assessment_id="a1", company_symbol="AAPL"),
        ]
        client = _client(repo=FakePerformanceRepo(outcomes))
        # Lowercase won't match uppercase stored symbol
        resp = client.get("/api/v1/performance/company/aapl")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_response_model_shape(self) -> None:
        outcome = _make_outcome(
            assessment_id="a1",
            company_symbol="MSFT",
            company_name="Microsoft Corp.",
            recommendation="hold",
            is_closed=True,
            outcome="neutral",
            return_3m_pct=1.2,
        )
        client = _client(repo=FakePerformanceRepo([outcome]))
        resp = client.get("/api/v1/performance/company/MSFT")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        item = body["items"][0]
        # Verify key fields are present
        assert item["outcome_id"]
        assert item["assessment_id"] == "a1"
        assert item["company_symbol"] == "MSFT"
        assert item["recommendation"] == "hold"
        assert item["entry_price"] > 0
