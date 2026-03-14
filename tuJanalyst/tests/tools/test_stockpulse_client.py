"""Tests for StockPulseClient — async HTTP wrapper around the StockPulse REST API."""

from __future__ import annotations

import httpx
import pytest

from src.agents.tools.stockpulse_client import StockPulseClient

BASE_URL = "https://stockpulse.test/api"
API_KEY = "test-api-key-123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transport(handler):
    """Build an httpx.MockTransport from an async handler function."""
    return httpx.MockTransport(handler)


def _build_client(transport: httpx.MockTransport, **kwargs) -> StockPulseClient:
    """Create a StockPulseClient with a mock transport injected."""
    session = httpx.AsyncClient(
        transport=transport,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
        },
    )
    return StockPulseClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        session=session,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. test_get_stock_success
# ---------------------------------------------------------------------------


async def test_get_stock_success():
    stock_payload = {"symbol": "INFY", "price": 1500.0, "sector": "IT"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/stocks/INFY"
        return httpx.Response(200, json=stock_payload)

    client = _build_client(_make_transport(handler))
    result = await client.get_stock("INFY")

    assert result == stock_payload
    await client.close()


# ---------------------------------------------------------------------------
# 2. test_get_indicators_success
# ---------------------------------------------------------------------------


async def test_get_indicators_success():
    indicators_payload = {"rsi": 55.3, "macd": 12.1, "period": "1d"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/stocks/RELIANCE/indicators"
        assert request.url.params["period"] == "1d"
        return httpx.Response(200, json=indicators_payload)

    client = _build_client(_make_transport(handler))
    result = await client.get_indicators("RELIANCE", period="1d")

    assert result == indicators_payload
    await client.close()


# ---------------------------------------------------------------------------
# 3. test_get_events_success
# ---------------------------------------------------------------------------


async def test_get_events_success():
    events_payload = [
        {"id": 1, "type": "earnings", "symbol": "TCS"},
        {"id": 2, "type": "dividend", "symbol": "TCS"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/events"
        assert request.url.params["symbol"] == "TCS"
        return httpx.Response(200, json=events_payload)

    client = _build_client(_make_transport(handler))
    result = await client.get_events("TCS")

    assert result == events_payload
    assert len(result) == 2
    await client.close()


# ---------------------------------------------------------------------------
# 4. test_post_note_success
# ---------------------------------------------------------------------------


async def test_post_note_success():
    note_response = {"id": 42, "content": "Strong quarter", "author_type": "agent"}
    captured_body: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        assert request.method == "POST"
        assert request.url.path == "/api/stocks/INFY/notes"
        import json

        captured_body = json.loads(request.content)
        return httpx.Response(200, json=note_response)

    client = _build_client(_make_transport(handler))
    result = await client.post_note("INFY", "Strong quarter", author_type="agent")

    assert result == note_response
    assert captured_body == {"content": "Strong quarter", "author_type": "agent"}
    await client.close()


# ---------------------------------------------------------------------------
# 5. test_update_color_success
# ---------------------------------------------------------------------------


async def test_update_color_success():
    color_response = {"symbol": "INFY", "color": "green", "comment": "looks good"}
    captured_body: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        assert request.method == "PUT"
        assert request.url.path == "/api/stocks/INFY/color"
        import json

        captured_body = json.loads(request.content)
        return httpx.Response(200, json=color_response)

    client = _build_client(_make_transport(handler))
    result = await client.update_color("INFY", "green", comment="looks good")

    assert result == color_response
    assert captured_body == {"color": "green", "comment": "looks good"}
    await client.close()


# ---------------------------------------------------------------------------
# 6. test_add_to_universe_success
# ---------------------------------------------------------------------------


async def test_add_to_universe_success():
    universe_response = {"symbol": "NEWCO", "company_name": "New Company Ltd", "sector": "Finance"}
    captured_body: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        assert request.method == "POST"
        assert request.url.path == "/api/universe"
        import json

        captured_body = json.loads(request.content)
        return httpx.Response(200, json=universe_response)

    client = _build_client(_make_transport(handler))
    result = await client.add_to_universe(
        symbol="NEWCO",
        company_name="New Company Ltd",
        sector="Finance",
        nse_symbol="NEWCO",
        isin="INE999A01234",
    )

    assert result == universe_response
    assert captured_body == {
        "symbol": "NEWCO",
        "company_name": "New Company Ltd",
        "sector": "Finance",
        "nse_symbol": "NEWCO",
        "isin": "INE999A01234",
    }
    await client.close()


# ---------------------------------------------------------------------------
# 7. test_auth_header_sent
# ---------------------------------------------------------------------------


async def test_auth_header_sent():
    captured_headers: dict | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    client = _build_client(_make_transport(handler))
    await client.get_stock("INFY")

    assert captured_headers is not None
    assert captured_headers["authorization"] == f"Bearer {API_KEY}"
    await client.close()


# ---------------------------------------------------------------------------
# 8. test_http_error_returns_none
# ---------------------------------------------------------------------------


async def test_http_error_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal Server Error"})

    client = _build_client(_make_transport(handler))
    result = await client.get_stock("INFY")

    assert result is None
    await client.close()


# ---------------------------------------------------------------------------
# 9. test_timeout_returns_none
# ---------------------------------------------------------------------------


async def test_timeout_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out")

    client = _build_client(_make_transport(handler))
    result = await client.get_stock("INFY")

    assert result is None
    await client.close()


# ---------------------------------------------------------------------------
# 10. test_circuit_breaker_opens
# ---------------------------------------------------------------------------


async def test_circuit_breaker_opens():
    """After 3 consecutive failures the circuit breaker opens and subsequent
    calls short-circuit without issuing an HTTP request."""

    call_count = 0
    fake_time = 0.0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "fail"})

    client = _build_client(
        _make_transport(handler),
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_seconds=60,
        circuit_time_fn=lambda: fake_time,
    )

    # First 3 calls hit the transport and fail, tripping the breaker.
    for _ in range(3):
        result = await client.get_stock("INFY")
        assert result is None

    assert call_count == 3

    # 4th call should be short-circuited — no HTTP request made.
    result = await client.get_stock("INFY")
    assert result is None
    assert call_count == 3, "Expected circuit breaker to prevent HTTP call"

    # Advance time past recovery window — breaker should close.
    fake_time = 61.0
    call_count = 0

    result = await client.get_stock("INFY")
    assert result is None  # still 500, but the request was made
    assert call_count == 1, "Expected breaker to close after recovery period"

    await client.close()
