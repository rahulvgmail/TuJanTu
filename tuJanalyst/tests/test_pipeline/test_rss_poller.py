"""Tests for NSE/BSE exchange poller behavior."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from src.models.trigger import TriggerEvent, TriggerSource
from src.pipeline.layer1_triggers.rss_poller import ExchangeRSSPoller


class InMemoryTriggerRepo:
    """Minimal trigger repository test double for poller tests."""

    def __init__(self) -> None:
        self.items: list[TriggerEvent] = []
        self.seen_urls: set[str] = set()
        self.exists_by_url_calls = 0
        self.recent_override: list[TriggerEvent] | None = None

    async def save(self, trigger: TriggerEvent) -> str:
        self.items.append(trigger)
        if trigger.source_url:
            self.seen_urls.add(trigger.source_url)
        return trigger.trigger_id

    async def exists_by_url(self, source_url: str) -> bool:
        self.exists_by_url_calls += 1
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

    async def list_recent(
        self,
        limit: int = 20,
        offset: int = 0,
        status=None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[TriggerEvent]:
        del offset, status, company_symbol, source, since
        if self.recent_override is not None:
            return self.recent_override[:limit]
        return list(reversed(self.items))[:limit]


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
        existing = TriggerEvent(
            source=TriggerSource.NSE_RSS,
            source_url="https://nse.example/already-seen.pdf",
            raw_content="Board meeting outcome",
            company_symbol="SUZLON",
            company_name="Suzlon Energy Limited",
            source_feed_title="Board meeting outcome",
        )
        repo.recent_override = [existing]
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


@pytest.mark.asyncio
async def test_poll_deduplicates_canonicalized_urls_with_tracking_params() -> None:
    nse_url = "https://example.test/nse"
    payload = {
        "data": [
            {
                "symbol": "ABB",
                "sm_name": "ABB India",
                "desc": "Capacity expansion update",
                "attchmntFile": "https://nse.example/doc.pdf?utm_source=x&a=1",
                "an_dt": "23-Feb-2026",
            },
            {
                "symbol": "ABB",
                "sm_name": "ABB India",
                "desc": "Capacity expansion update",
                "attchmntFile": "https://nse.example/doc.pdf?a=1&utm_medium=y",
                "an_dt": "23-Feb-2026",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, session=session)
        created = await poller.poll()

    assert len(created) == 1
    assert created[0].source_url == "https://nse.example/doc.pdf?a=1"


@pytest.mark.asyncio
async def test_poll_uses_recent_cache_for_content_based_dedup() -> None:
    nse_url = "https://example.test/nse"
    payload = {
        "data": [
            {
                "symbol": "ABB",
                "sm_name": "ABB India",
                "desc": "Capacity expansion update",
                "attchmntFile": "https://nse.example/new-location.pdf",
                "an_dt": "23-Feb-2026",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})

    existing = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        source_url="https://nse.example/old-location.pdf",
        source_feed_title="Capacity expansion update",
        source_feed_published=datetime(2026, 2, 23, tzinfo=timezone.utc),
        company_symbol="ABB",
        company_name="ABB India",
        raw_content="Capacity expansion update",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        repo.recent_override = [existing]
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, session=session)
        created = await poller.poll()

    assert created == []
    assert repo.exists_by_url_calls == 0


@pytest.mark.asyncio
async def test_poll_infers_nse_scrip_code_and_company_name_when_symbol_missing() -> None:
    nse_url = "https://example.test/nse"
    payload = {
        "data": [
            {
                "desc": "JSW Energy Limited - Notice of Shareholders Meeting",
                "attchmntFile": "https://nsearchives.nseindia.com/corporate/xbrl/NOTICE_OF_SHAREHOLDERS_MEETINGS_1629332_24022026010002_WEB.xml",
                "an_dt": "24-Feb-2026",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        repo = InMemoryTriggerRepo()
        poller = ExchangeRSSPoller(trigger_repo=repo, nse_url=nse_url, session=session)
        created = await poller.poll()

    assert len(created) == 1
    assert created[0].company_symbol == "1629332"
    assert created[0].company_name == "JSW Energy Limited"
