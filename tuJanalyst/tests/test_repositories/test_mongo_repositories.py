"""Integration-style tests for MongoDB repository implementations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from src.models.document import RawDocument
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.repositories.mongo import MongoDocumentRepository, MongoTriggerRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_db():
    client = AsyncMongoMockClient()
    return client["test_db"]


@pytest.fixture
def trigger_repo(mock_db):
    return MongoTriggerRepository(mock_db)


@pytest.fixture
def document_repo(mock_db):
    return MongoDocumentRepository(mock_db)


@pytest.mark.asyncio
async def test_trigger_save_and_get(trigger_repo: MongoTriggerRepository) -> None:
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        source_url="https://example.com/1",
        raw_content="Quarterly results announced",
        company_symbol="INOXWIND",
    )

    trigger_id = await trigger_repo.save(trigger)
    loaded = await trigger_repo.get(trigger_id)

    assert loaded is not None
    assert loaded.trigger_id == trigger_id
    assert loaded.company_symbol == "INOXWIND"


@pytest.mark.asyncio
async def test_trigger_get_pending_returns_oldest_first_with_limit(trigger_repo: MongoTriggerRepository) -> None:
    now = _utc_now()
    for index in range(5):
        trigger = TriggerEvent(
            source=TriggerSource.NSE_RSS,
            source_url=f"https://example.com/{index}",
            raw_content=f"Announcement {index}",
            created_at=now + timedelta(minutes=index),
            updated_at=now + timedelta(minutes=index),
        )
        await trigger_repo.save(trigger)

    pending = await trigger_repo.get_pending(limit=3)

    assert len(pending) == 3
    assert pending[0].source_url == "https://example.com/0"
    assert pending[2].source_url == "https://example.com/2"


@pytest.mark.asyncio
async def test_trigger_update_status_appends_history(trigger_repo: MongoTriggerRepository) -> None:
    trigger = TriggerEvent(source=TriggerSource.HUMAN, raw_content="Manual trigger")
    await trigger_repo.save(trigger)

    await trigger_repo.update_status(trigger.trigger_id, TriggerStatus.GATE_PASSED, "human bypass")
    await trigger_repo.update_status(trigger.trigger_id, TriggerStatus.ANALYZING, "analysis started")

    loaded = await trigger_repo.get(trigger.trigger_id)
    assert loaded is not None
    assert loaded.status == TriggerStatus.ANALYZING.value
    assert len(loaded.status_history) == 2
    assert loaded.status_history[0].reason == "human bypass"
    assert loaded.status_history[1].status == TriggerStatus.ANALYZING.value


@pytest.mark.asyncio
async def test_trigger_exists_by_url(trigger_repo: MongoTriggerRepository) -> None:
    trigger = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        source_url="https://example.com/bse/1",
        raw_content="BSE announcement",
    )
    await trigger_repo.save(trigger)

    assert await trigger_repo.exists_by_url("https://example.com/bse/1") is True
    assert await trigger_repo.exists_by_url("https://example.com/unknown") is False


@pytest.mark.asyncio
async def test_trigger_list_recent_with_filters_offset_and_count(trigger_repo: MongoTriggerRepository) -> None:
    now = _utc_now()
    entries = [
        TriggerEvent(
            source=TriggerSource.NSE_RSS,
            source_url="https://example.com/a",
            raw_content="A",
            company_symbol="INOXWIND",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
        ),
        TriggerEvent(
            source=TriggerSource.NSE_RSS,
            source_url="https://example.com/b",
            raw_content="B",
            company_symbol="INOXWIND",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        ),
        TriggerEvent(
            source=TriggerSource.BSE_RSS,
            source_url="https://example.com/c",
            raw_content="C",
            company_symbol="BHEL",
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        ),
    ]
    for trigger in entries:
        await trigger_repo.save(trigger)

    await trigger_repo.update_status(entries[0].trigger_id, TriggerStatus.FILTERED_OUT, "old")
    await trigger_repo.update_status(entries[1].trigger_id, TriggerStatus.GATE_PASSED, "pass")
    await trigger_repo.update_status(entries[2].trigger_id, TriggerStatus.GATE_PASSED, "pass")

    filtered = await trigger_repo.list_recent(
        limit=10,
        offset=0,
        status=TriggerStatus.GATE_PASSED,
        source=TriggerSource.NSE_RSS.value,
        since=now - timedelta(days=1),
    )
    assert len(filtered) == 1
    assert filtered[0].trigger_id == entries[1].trigger_id

    paged = await trigger_repo.list_recent(limit=1, offset=1)
    assert len(paged) == 1

    total = await trigger_repo.count(
        status=TriggerStatus.GATE_PASSED,
        source=TriggerSource.NSE_RSS.value,
        since=now - timedelta(days=1),
    )
    assert total == 1


@pytest.mark.asyncio
async def test_trigger_counts_by_status_with_since_filter(trigger_repo: MongoTriggerRepository) -> None:
    now = _utc_now()
    old_trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        source_url="https://example.com/old",
        raw_content="old",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    recent_a = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        source_url="https://example.com/recent-a",
        raw_content="recent-a",
        created_at=now - timedelta(hours=4),
        updated_at=now - timedelta(hours=4),
    )
    recent_b = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        source_url="https://example.com/recent-b",
        raw_content="recent-b",
        created_at=now - timedelta(hours=3),
        updated_at=now - timedelta(hours=3),
    )
    for trigger in [old_trigger, recent_a, recent_b]:
        await trigger_repo.save(trigger)

    await trigger_repo.update_status(old_trigger.trigger_id, TriggerStatus.FILTERED_OUT, "old")
    await trigger_repo.update_status(recent_a.trigger_id, TriggerStatus.GATE_PASSED, "pass")
    await trigger_repo.update_status(recent_b.trigger_id, TriggerStatus.GATE_PASSED, "pass")

    counts = await trigger_repo.counts_by_status(since=now - timedelta(days=1))
    assert counts["gate_passed"] == 2
    assert counts.get("filtered_out", 0) == 0


@pytest.mark.asyncio
async def test_document_save_get_and_update(document_repo: MongoDocumentRepository) -> None:
    document = RawDocument(
        trigger_id="trigger-123",
        source_url="https://example.com/doc.pdf",
        company_symbol="SUZLON",
    )
    document_id = await document_repo.save(document)

    await document_repo.update_extracted_text(
        document_id,
        text="Extracted body text",
        method="pdfplumber",
        metadata={"page_count": 5},
    )

    loaded = await document_repo.get(document_id)
    assert loaded is not None
    assert loaded.extracted_text == "Extracted body text"
    assert loaded.extraction_method == "pdfplumber"
    assert loaded.extraction_metadata["page_count"] == 5


@pytest.mark.asyncio
async def test_document_get_by_trigger(document_repo: MongoDocumentRepository) -> None:
    first = RawDocument(trigger_id="trigger-xyz", source_url="https://example.com/1.pdf")
    second = RawDocument(trigger_id="trigger-xyz", source_url="https://example.com/2.pdf")
    third = RawDocument(trigger_id="trigger-other", source_url="https://example.com/3.pdf")
    await document_repo.save(first)
    await document_repo.save(second)
    await document_repo.save(third)

    documents = await document_repo.get_by_trigger("trigger-xyz")
    urls = {doc.source_url for doc in documents}

    assert len(documents) == 2
    assert urls == {"https://example.com/1.pdf", "https://example.com/2.pdf"}
