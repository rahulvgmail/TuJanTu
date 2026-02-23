"""Tests for NSE/BSE exchange poller behavior."""

from __future__ import annotations

import json

import httpx
import pytest

from src.models.trigger import TriggerEvent
from src.pipeline.layer1_triggers.rss_poller import ExchangeRSSPoller


class InMemoryTriggerRepo:
    """Minimal trigger repository test double for poller tests."""

    def __init__(self) -> None:
        self.items: list[TriggerEvent] = []
        self.seen_urls: set[str] = set()

    async def save(self, trigger: TriggerEvent) -> str:
        self.items.append(trigger)
        if trigger.source_url:
            self.seen_urls.add(trigger.source_url)
        return trigger.trigger_id

    async def exists_by_url(self, source_url: str) -> bool:
        return source_url in self.seen_urls

    async def get(self, trigger_id: str):  # pragma: no cover
        for item in self.items:
            if item.trigger_id == trigger_id:
                return item
        return None

    async def update_status(self, trigger_id: str, status, reason: str = ""):  # pragma: no cover
        return None

    async def get_pending(self, limit: int = 50):  # pragma: no cover
        return []

    async def get_by_company(self, company_symbol: str, limit: int = 20):  # pragma: no cover
        return []


@pytest.mark.asyncio
async def test_poll_creates_triggers_from_nse_and_bse() -> None:
    nse_url = "https://example.test/nse"
    bse_url = "https://example.test/bse"
    payloads = {
        nse_url: {
            "data": [
                {
                    "symbol": "INOXWIND",
                    "sm_name": "Inox Wind Limited",
                    "desc": "Q3 financial results announced",
                    "attchmntFile": "https://nse.example/doc1.pdf",
                    "an_dt": "23-Feb-2026",
                }
            ]
        },
        bse_url: {
            "Table": [
                {
                    "SCRIP_CD": "500112",
                    "CompanyName": "BHEL",
                    "News_Sub": "Order win update",
                    "Attachment": "https://bse.example/doc2.pdf",
                    "News_submission_dt": "2026-02-23 10:10:00",
                }
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = payloads[str(request.url)]
        return httpx.Response(200, json=body, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, bse_url=bse_url, session=session)

        created = await poller.poll()

    assert len(created) == 2
    assert {item.source for item in created} == {"nse_rss", "bse_rss"}
    assert {item.company_symbol for item in created} == {"INOXWIND", "500112"}


@pytest.mark.asyncio
async def test_poll_skips_duplicate_urls() -> None:
    nse_url = "https://example.test/nse"
    bse_url = "https://example.test/bse"
    payloads = {
        nse_url: {
            "data": [
                {
                    "symbol": "SUZLON",
                    "sm_name": "Suzlon Energy Limited",
                    "desc": "Board meeting outcome",
                    "attchmntFile": "https://nse.example/already-seen.pdf",
                },
                {
                    "symbol": "SUZLON",
                    "sm_name": "Suzlon Energy Limited",
                    "desc": "Fresh announcement",
                    "attchmntFile": "https://nse.example/new.pdf",
                },
            ]
        },
        bse_url: {"Table": []},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(payloads[str(request.url)]),
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        repo.seen_urls.add("https://nse.example/already-seen.pdf")
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, bse_url=bse_url, session=session)

        created = await poller.poll()

    assert len(created) == 1
    assert created[0].source_url == "https://nse.example/new.pdf"


@pytest.mark.asyncio
async def test_poll_continues_when_one_source_fails() -> None:
    nse_url = "https://example.test/nse"
    bse_url = "https://example.test/bse"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == nse_url:
            return httpx.Response(500, text="nse failure")
        return httpx.Response(
            200,
            json={
                "Table": [
                    {
                        "SCRIP_CD": "500114",
                        "CompanyName": "ABB",
                        "News_Sub": "Capacity expansion",
                        "Attachment": "https://bse.example/doc3.pdf",
                    }
                ]
            },
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, bse_url=bse_url, session=session)
        created = await poller.poll()

    assert len(created) == 1
    assert created[0].source == "bse_rss"
    assert created[0].company_symbol == "500114"

