"""Async HTTP client wrapping the StockPulse REST API for service-to-service communication."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from src.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class StockPulseClient:
    """Thin async wrapper around the StockPulse REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: int = 10,
        circuit_breaker_failure_threshold: int = 3,
        circuit_breaker_recovery_seconds: int = 120,
        circuit_time_fn: Callable[[], float] | None = None,
        session: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_failure_threshold,
            recovery_seconds=float(circuit_breaker_recovery_seconds),
            time_fn=circuit_time_fn or time.monotonic,
        )
        self.session = session or httpx.AsyncClient(
            timeout=float(timeout_seconds),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_stock(self, symbol: str) -> dict[str, Any] | None:
        """GET /api/stocks/{symbol}"""
        result = await self._request("GET", f"/stocks/{symbol}")
        return result if isinstance(result, dict) else None

    async def get_indicators(self, symbol: str, period: str = "1d") -> dict[str, Any] | None:
        """GET /api/stocks/{symbol}/indicators?period={period}"""
        result = await self._request("GET", f"/stocks/{symbol}/indicators", params={"period": period})
        return result if isinstance(result, dict) else None

    async def get_events(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        """GET /api/events?symbol={symbol}&limit={limit}"""
        result = await self._request("GET", "/events", params={"symbol": symbol, "limit": limit})
        return result if isinstance(result, list) else []

    async def get_screener_results(self, screener_id: int, date: str | None = None) -> list[dict[str, Any]]:
        """GET /api/screeners/{screener_id}/results"""
        params: dict[str, Any] = {}
        if date is not None:
            params["date"] = date
        result = await self._request("GET", f"/screeners/{screener_id}/results", params=params or None)
        return result if isinstance(result, list) else []

    async def get_screeners(self) -> list[dict[str, Any]]:
        """GET /api/screeners"""
        result = await self._request("GET", "/screeners")
        return result if isinstance(result, list) else []

    async def get_screener_membership(
        self,
        symbol: str,
        screener_ids: list[int] | None = None,
    ) -> list[str]:
        """Check which screeners a stock currently appears in.

        If *screener_ids* is provided, only those screeners are checked.
        Otherwise all screeners are checked (expensive — prefer passing a subset).

        Returns list of screener names the stock matches.
        """
        screeners = await self.get_screeners()
        if not screeners:
            return []

        if screener_ids is not None:
            screeners = [s for s in screeners if s.get("id") in screener_ids]

        matched: list[str] = []
        for screener in screeners:
            sid = screener.get("id")
            name = screener.get("name", f"screener-{sid}")
            if sid is None:
                continue
            results = await self.get_screener_results(sid)
            # Check if symbol appears in results
            for row in results:
                if row.get("symbol") == symbol:
                    matched.append(name)
                    break
        return matched

    async def post_note(self, symbol: str, content: str, author_type: str = "agent") -> dict[str, Any] | None:
        """POST /api/stocks/{symbol}/notes"""
        result = await self._request(
            "POST",
            f"/stocks/{symbol}/notes",
            json={"content": content, "author_type": author_type},
        )
        return result if isinstance(result, dict) else None

    async def update_color(self, symbol: str, color: str, comment: str = "") -> dict[str, Any] | None:
        """PUT /api/stocks/{symbol}/color"""
        result = await self._request(
            "PUT",
            f"/stocks/{symbol}/color",
            json={"color": color, "comment": comment},
        )
        return result if isinstance(result, dict) else None

    async def add_to_universe(
        self,
        symbol: str,
        company_name: str,
        sector: str | None = None,
        nse_symbol: str | None = None,
        isin: str | None = None,
    ) -> dict[str, Any] | None:
        """POST /api/universe"""
        payload: dict[str, Any] = {"symbol": symbol, "company_name": company_name}
        if sector is not None:
            payload["sector"] = sector
        if nse_symbol is not None:
            payload["nse_symbol"] = nse_symbol
        if isin is not None:
            payload["isin"] = isin
        result = await self._request("POST", "/universe", json=payload)
        return result if isinstance(result, dict) else None

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self.session.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Execute an HTTP request with circuit-breaker protection.

        Returns the parsed JSON body on success, or ``None`` on failure.
        """
        if self._circuit_breaker.is_open():
            logger.warning(
                "StockPulse circuit breaker open; skipping request: path=%s retry_in=%.1fs",
                path,
                self._circuit_breaker.seconds_until_close(),
            )
            return None

        url = f"{self.base_url}{path}"
        try:
            response = await self.session.request(method, url, params=params, json=json)
            response.raise_for_status()
            self._circuit_breaker.record_success()
            return response.json()
        except httpx.HTTPStatusError as exc:
            self._circuit_breaker.record_failure()
            if exc.response.status_code == 429:
                logger.warning("StockPulse API rate limited: path=%s", path)
            else:
                logger.warning(
                    "StockPulse API returned non-success status: path=%s status=%s",
                    path,
                    exc.response.status_code,
                )
            return None
        except httpx.TimeoutException:
            self._circuit_breaker.record_failure()
            logger.warning("StockPulse API request timed out: path=%s", path)
            return None
        except Exception as exc:  # noqa: BLE001
            self._circuit_breaker.record_failure()
            logger.warning("StockPulse API request failed: path=%s error=%s", path, exc)
            return None
