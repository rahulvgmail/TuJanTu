"""Tests for web search tool provider adapters."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agents.tools.web_search import WebSearchTool


@pytest.mark.asyncio
async def test_web_search_tool_brave_normalizes_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/res/v1/web/search"
        assert request.headers.get("X-Subscription-Token") == "brave-key"
        payload = {
            "web": {
                "results": [
                    {
                        "title": "Inox Wind Q3 results",
                        "url": "https://example.test/inox",
                        "description": "Quarterly revenue and margin update",
                    }
                ]
            }
        }
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        tool = WebSearchTool(provider="brave", api_key="brave-key", session=session)
        results = await tool.search("Inox Wind quarterly results")

    assert results == [
        {
            "title": "Inox Wind Q3 results",
            "url": "https://example.test/inox",
            "snippet": "Quarterly revenue and margin update",
        }
    ]


@pytest.mark.asyncio
async def test_web_search_tool_tavily_normalizes_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        body = json.loads(request.content.decode())
        assert body["api_key"] == "tavily-key"
        payload = {
            "results": [
                {
                    "title": "BHEL new order wins",
                    "url": "https://example.test/bhel",
                    "content": "Company secured a large order.",
                }
            ]
        }
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        tool = WebSearchTool(provider="tavily", api_key="tavily-key", session=session)
        results = await tool.search("BHEL order wins")

    assert results[0]["title"] == "BHEL new order wins"
    assert results[0]["url"] == "https://example.test/bhel"
    assert results[0]["snippet"] == "Company secured a large order."


@pytest.mark.asyncio
async def test_web_search_tool_empty_query_returns_empty() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        tool = WebSearchTool(provider="brave", api_key="brave-key", session=session)
        results = await tool.search("   ")

    assert results == []
    assert request_count == 0


@pytest.mark.asyncio
async def test_web_search_tool_gracefully_handles_provider_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        tool = WebSearchTool(provider="tavily", api_key="bad-key", session=session)
        results = await tool.search("financial results")

    assert results == []
