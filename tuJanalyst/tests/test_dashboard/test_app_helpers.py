"""Unit tests for dashboard app helper functions."""

from __future__ import annotations

from typing import Any

import pytest

import src.dashboard.app as dashboard_app


class _FakeResponse:
    def __init__(self, payload: Any):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def test_api_get_uses_timeout_and_returns_dict_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *, timeout: float):
            called["timeout"] = timeout

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:
            called["url"] = url
            called["params"] = params
            return _FakeResponse({"items": []})

    monkeypatch.setattr(dashboard_app.httpx, "Client", _FakeClient)

    payload = dashboard_app._api_get("http://app:8000", "/api/v1/reports/", params={"limit": 10})

    assert payload == {"items": []}
    assert called["timeout"] == dashboard_app.HTTP_TIMEOUT_SECONDS
    assert called["url"] == "http://app:8000/api/v1/reports/"
    assert called["params"] == {"limit": 10}


def test_api_get_rejects_non_mapping_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeClient:
        def __init__(self, *, timeout: float):
            del timeout

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:
            del url, params
            return _FakeResponse([1, 2, 3])

    monkeypatch.setattr(dashboard_app.httpx, "Client", _FakeClient)

    with pytest.raises(ValueError, match="Unexpected API payload type"):
        dashboard_app._api_get("http://app:8000", "/api/v1/reports/")


def test_api_post_uses_timeout_and_returns_dict_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *, timeout: float):
            called["timeout"] = timeout

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            called["url"] = url
            called["json"] = json
            return _FakeResponse({"trigger_id": "trg-1"})

    monkeypatch.setattr(dashboard_app.httpx, "Client", _FakeClient)

    payload = dashboard_app._api_post(
        "http://app:8000",
        "/api/v1/triggers/human",
        json_payload={"company_symbol": "SUZLON", "content": "Manual trigger"},
    )

    assert payload == {"trigger_id": "trg-1"}
    assert called["timeout"] == dashboard_app.HTTP_TIMEOUT_SECONDS
    assert called["url"] == "http://app:8000/api/v1/triggers/human"
    assert called["json"] == {"company_symbol": "SUZLON", "content": "Manual trigger"}


def test_fetch_reports_filters_non_dict_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dashboard_app,
        "_api_get",
        lambda base_url, path, *, params=None: {"items": [{"report_id": "r1"}, "ignore", 3, {"report_id": "r2"}]},
    )

    rows = dashboard_app._fetch_reports("http://app:8000", limit=25)

    assert rows == [{"report_id": "r1"}, {"report_id": "r2"}]


def test_fetch_performance_recommendations_normalizes_params(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    def _fake_api_get(base_url: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        called["base_url"] = base_url
        called["path"] = path
        called["params"] = params
        return {"items": [{"assessment_id": "a1"}, "skip-me"]}

    monkeypatch.setattr(dashboard_app, "_api_get", _fake_api_get)

    rows = dashboard_app._fetch_performance_recommendations("http://app:8000", limit=40, include_live_price=True)

    assert rows == [{"assessment_id": "a1"}]
    assert called["base_url"] == "http://app:8000"
    assert called["path"] == "/api/v1/performance/recommendations"
    assert called["params"] == {"limit": 40, "offset": 0, "include_live_price": "true"}


def test_fetch_notes_normalizes_company_and_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    def _fake_api_get(base_url: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        called["base_url"] = base_url
        called["path"] = path
        called["params"] = params
        return {"items": []}

    monkeypatch.setattr(dashboard_app, "_api_get", _fake_api_get)

    rows = dashboard_app._fetch_notes("http://app:8000", company=" suzlon ", tag=" Thesis ", limit=12)

    assert rows == []
    assert called["base_url"] == "http://app:8000"
    assert called["path"] == "/api/v1/notes"
    assert called["params"] == {"limit": 12, "company": "SUZLON", "tag": "thesis"}


def test_parse_tag_list_deduplicates_normalizes_and_drops_empty_values() -> None:
    parsed = dashboard_app._parse_tag_list(" Risk, thesis, ,RISK,  valuation ")

    assert parsed == ["risk", "thesis", "valuation"]


def test_build_recommendation_rows_applies_defaults_and_scoring() -> None:
    rows = dashboard_app._build_recommendation_rows(
        [
            {
                "report_id": "r1",
                "company_symbol": "SUZLON",
                "title": "Q3 results",
                "recommendation_summary": "BUY (Confidence: 82%, Timeframe: short_term)",
                "created_at": "2026-02-25T10:15:00+00:00",
            },
            {
                "report_id": "r2",
                "recommendation_summary": "No call",
                "created_at": "not-a-date",
            },
        ]
    )

    assert rows[0]["report_id"] == "r1"
    assert rows[0]["company"] == "SUZLON"
    assert rows[0]["recommendation"] == "BUY"
    assert rows[0]["confidence_pct"] == 82
    assert rows[0]["created_at"] == "2026-02-25T10:15:00+00:00"
    assert rows[0]["expected_impact_score"] > rows[1]["expected_impact_score"]
    assert rows[1]["company"] == "UNKNOWN"
    assert rows[1]["created_at"] == ""


def test_build_performance_rows_formats_metrics() -> None:
    rows = dashboard_app._build_performance_rows(
        [
            {
                "recommendation_date": "2026-02-25T09:00:00+00:00",
                "company_symbol": "BHEL",
                "company_name": "BHEL Ltd",
                "recommendation": "buy",
                "price_at_recommendation": 100.0,
                "price_now": 106.5,
                "return_pct": 6.5,
                "timeframe": "medium_term",
                "status": "open",
                "outcome": "win",
                "assessment_id": "a-1",
            }
        ]
    )

    assert rows == [
        {
            "date": "2026-02-25T09:00:00",
            "company": "BHEL | BHEL Ltd",
            "action": "BUY",
            "price_at_recommendation": "100.00",
            "price_now": "106.50",
            "return_pct": "+6.50%",
            "timeframe": "MEDIUM TERM",
            "status": "Open",
            "outcome": "WIN",
            "assessment_id": "a-1",
        }
    ]


def test_build_auxiliary_rows_convert_nested_lists_to_text() -> None:
    note_rows = dashboard_app._build_note_rows(
        [
            {
                "updated_at": "2026-02-25T12:00:00+00:00",
                "company_symbol": "SIEMENS",
                "created_by": "analyst-1",
                "tags": ["risk", "valuation"],
                "content": "Monitor order book quality.",
                "report_id": "rep-1",
                "investigation_id": "inv-1",
                "note_id": "note-1",
            }
        ]
    )
    notification_rows = dashboard_app._build_notification_rows(
        [
            {
                "created_at": "2026-02-25T12:30:00+00:00",
                "kind": "report_ready",
                "company_symbol": "SIEMENS",
                "title": "Report ready",
                "message": "A new report is available.",
                "entity_id": "rep-1",
            }
        ]
    )
    company_rows = dashboard_app._build_watchlist_company_rows(
        [
            {
                "symbol": "SIEMENS",
                "name": "Siemens Ltd",
                "sector": "industrials",
                "priority": "high",
                "aliases": ["Siemens India"],
                "status": "active",
                "last_trigger": "2026-02-25T09:01:00+00:00",
                "total_investigations": 3,
                "current_recommendation": "buy",
            }
        ]
    )
    sector_rows = dashboard_app._build_sector_rows(
        [{"sector_name": "industrials", "keywords": ["capex", "order"], "companies_count": 4}]
    )
    policy_rows = dashboard_app._build_policy_rows(
        [{"agent": "deep_analyzer", "domain": "reports", "actions": ["read", "create"]}]
    )

    assert note_rows[0]["tags"] == "risk, valuation"
    assert notification_rows[0]["time"] == "2026-02-25T12:30:00"
    assert company_rows[0]["aliases"] == "Siemens India"
    assert company_rows[0]["current_recommendation"] == "BUY"
    assert sector_rows[0]["keywords"] == "capex, order"
    assert policy_rows[0]["actions"] == "read, create"
