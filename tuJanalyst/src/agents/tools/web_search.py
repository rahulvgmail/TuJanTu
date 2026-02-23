"""Web search tool with Brave and Tavily provider adapters."""

from __future__ import annotations

import logging
from typing import Literal

import httpx

SearchProvider = Literal["brave", "tavily"]

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Execute web search queries via configured provider."""

    def __init__(
        self,
        provider: SearchProvider,
        api_key: str,
        *,
        max_results: int = 5,
        timeout_seconds: int = 15,
        session: httpx.AsyncClient | None = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.session = session or httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True)

    async def search(self, query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
        """Return normalized search results `[{title, url, snippet}]`."""
        trimmed = query.strip()
        if not trimmed:
            return []

        result_count = max_results or self.max_results
        try:
            if self.provider == "brave":
                return await self._search_brave(trimmed, result_count)
            if self.provider == "tavily":
                return await self._search_tavily(trimmed, result_count)
            logger.warning("Unsupported web search provider configured: %s", self.provider)
            return []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Web search provider rate limited request: provider=%s", self.provider)
            else:
                logger.warning(
                    "Web search provider returned non-success status: provider=%s status=%s",
                    self.provider,
                    exc.response.status_code,
                )
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web search failed: provider=%s error=%s", self.provider, exc)
            return []

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self.session.aclose()

    async def _search_brave(self, query: str, max_results: int) -> list[dict[str, str]]:
        response = await self.session.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
            params={
                "q": query,
                "count": max_results,
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("web", {}).get("results", [])
        normalized: list[dict[str, str]] = []
        for row in rows:
            title = str(row.get("title", "")).strip()
            url = str(row.get("url", "")).strip()
            snippet = str(row.get("description", "")).strip()
            if title and url:
                normalized.append({"title": title, "url": url, "snippet": snippet})
        return normalized

    async def _search_tavily(self, query: str, max_results: int) -> list[dict[str, str]]:
        response = await self.session.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results", [])
        normalized: list[dict[str, str]] = []
        for row in rows:
            title = str(row.get("title", "")).strip()
            url = str(row.get("url", "")).strip()
            snippet = str(row.get("content", "")).strip()
            if title and url:
                normalized.append({"title": title, "url": url, "snippet": snippet})
        return normalized
