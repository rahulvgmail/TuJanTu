"""Tests for the StockPulse webhook receiver endpoint (POST /api/v1/triggers/webhook)."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.triggers import router, _flood_detector
import src.api.triggers as triggers_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "event_id": 101,
    "event_type": "52W_CLOSING_HIGH",
    "stock_id": 42,
    "payload": {"symbol": "INFY", "price": 1800.0, "prev": 1790.0},
    "created_at": "2026-03-14T09:00:00Z",
}


def _make_app(trigger_repo: AsyncMock) -> FastAPI:
    """Build a minimal FastAPI app with the triggers router and a mock repo."""
    app = FastAPI()
    app.include_router(router)
    app.state.trigger_repo = trigger_repo
    return app


def _mock_settings(**overrides):
    """Return a lightweight mock of Settings with webhook-relevant fields."""
    defaults = {
        "stockpulse_webhook_secret": None,
        "technical_event_flood_threshold": 1000,
        "technical_event_flood_window_minutes": 5,
    }
    defaults.update(overrides)

    class _FakeSettings:
        pass

    s = _FakeSettings()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


@pytest.fixture(autouse=True)
def _reset_flood_detector():
    """Reset the module-level flood detector between tests."""
    triggers_module._flood_detector = None
    yield
    triggers_module._flood_detector = None


# ---------------------------------------------------------------------------
# 1. test_webhook_valid_payload
# ---------------------------------------------------------------------------


async def test_webhook_valid_payload():
    repo = AsyncMock()
    repo.save = AsyncMock(return_value="trigger-abc")
    app = _make_app(repo)

    settings = _mock_settings()

    with patch("src.api.triggers.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/triggers/webhook", json=VALID_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert "trigger_id" in body
    assert body["status"] == "accepted"
    repo.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. test_webhook_invalid_payload
# ---------------------------------------------------------------------------


async def test_webhook_invalid_payload():
    repo = AsyncMock()
    app = _make_app(repo)

    settings = _mock_settings()

    with patch("src.api.triggers.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triggers/webhook",
                json={"event_id": 1},  # missing required fields
            )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. test_webhook_hmac_validation_success
# ---------------------------------------------------------------------------


async def test_webhook_hmac_validation_success():
    repo = AsyncMock()
    repo.save = AsyncMock(return_value="trigger-hmac")
    app = _make_app(repo)

    secret = "my-test-secret"
    settings = _mock_settings(stockpulse_webhook_secret=secret)

    body_bytes = json.dumps(VALID_PAYLOAD).encode()
    signature = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

    with patch("src.api.triggers.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triggers/webhook",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-StockPulse-Signature": signature,
                },
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# 4. test_webhook_hmac_validation_failure
# ---------------------------------------------------------------------------


async def test_webhook_hmac_validation_failure():
    repo = AsyncMock()
    app = _make_app(repo)

    secret = "my-test-secret"
    settings = _mock_settings(stockpulse_webhook_secret=secret)

    with patch("src.api.triggers.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triggers/webhook",
                json=VALID_PAYLOAD,
                headers={"X-StockPulse-Signature": "bad-signature"},
            )

    assert resp.status_code == 401
