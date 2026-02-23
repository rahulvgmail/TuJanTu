"""Week 1 integration test: poll -> fetch -> extract."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.pipeline.layer1_triggers.document_fetcher import DocumentFetcher
from src.pipeline.layer1_triggers.rss_poller import ExchangeRSSPoller
from src.pipeline.layer1_triggers.text_extractor import TextExtractor


@pytest.mark.asyncio
async def test_week1_poll_fetch_extract_integration(
    trigger_repo,
    document_repo,
    tmp_path: Path,
) -> None:
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    nse_payload = json.loads((fixtures_dir / "nse_announcements.json").read_text(encoding="utf-8"))
    bse_payload = json.loads((fixtures_dir / "bse_announcements.json").read_text(encoding="utf-8"))
    html_fixture = (fixtures_dir / "sample_announcement.html").read_text(encoding="utf-8")

    nse_url = "https://example.test/nse"
    bse_url = "https://example.test/bse"
    document_url = "https://example.test/docs/ann-001.html"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == nse_url:
            return httpx.Response(200, json=nse_payload, headers={"content-type": "application/json"})
        if str(request.url) == bse_url:
            return httpx.Response(200, json=bse_payload, headers={"content-type": "application/json"})
        if str(request.url) == document_url:
            return httpx.Response(200, text=html_fixture, headers={"content-type": "text/html"})
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        poller = ExchangeRSSPoller(trigger_repo=trigger_repo, nse_url=nse_url, bse_url=bse_url, session=session)
        created_triggers = await poller.poll()
        assert len(created_triggers) == 1

        trigger = created_triggers[0]
        assert trigger.source == "nse_rss"
        assert trigger.source_url == document_url

        fetcher = DocumentFetcher(
            doc_repo=document_repo,
            download_dir=str(tmp_path / "downloads"),
            session=session,
            max_size_mb=1,
        )
        document = await fetcher.fetch(
            trigger_id=trigger.trigger_id,
            url=trigger.source_url or document_url,
            company_symbol=trigger.company_symbol,
        )
        assert document.processing_status == "downloaded"
        assert document.file_path is not None

    extractor = TextExtractor(document_repo)
    extracted = await extractor.extract(document.document_id)
    assert extracted is not None
    assert extracted.processing_status == "extracted"
    assert extracted.extraction_method == "beautifulsoup"
    assert "Quarterly results approved" in (extracted.extracted_text or "")

