"""Shared test fixtures for tuJanalyst."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from src.models.document import RawDocument
from src.models.trigger import TriggerEvent, TriggerSource
from src.repositories.mongo import MongoDocumentRepository, MongoTriggerRepository, ensure_indexes


@pytest.fixture
def mongo_client() -> AsyncMongoMockClient:
    """Return an isolated async Mongo mock client per test."""
    return AsyncMongoMockClient()


@pytest_asyncio.fixture
async def mongo_db(mongo_client: AsyncMongoMockClient):
    """Return indexed test database instance."""
    db = mongo_client["tujanalyst_test"]
    await ensure_indexes(db)
    return db


@pytest.fixture
def trigger_repo(mongo_db):
    """Mongo trigger repository fixture."""
    return MongoTriggerRepository(mongo_db)


@pytest.fixture
def document_repo(mongo_db):
    """Mongo document repository fixture."""
    return MongoDocumentRepository(mongo_db)


@pytest.fixture
def create_test_trigger():
    """Factory for quickly creating TriggerEvent fixtures."""

    def _create(
        *,
        source: TriggerSource = TriggerSource.NSE_RSS,
        source_url: str = "https://example.test/announcement",
        raw_content: str = "Sample announcement",
        company_symbol: str | None = "INOXWIND",
        company_name: str | None = "Inox Wind Limited",
    ) -> TriggerEvent:
        return TriggerEvent(
            source=source,
            source_url=source_url,
            raw_content=raw_content,
            company_symbol=company_symbol,
            company_name=company_name,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    return _create


@pytest.fixture
def create_test_document():
    """Factory for quickly creating RawDocument fixtures."""

    def _create(
        *,
        trigger_id: str = "trigger-1",
        source_url: str = "https://example.test/document.pdf",
        file_path: str | None = None,
    ) -> RawDocument:
        return RawDocument(
            trigger_id=trigger_id,
            source_url=source_url,
            file_path=file_path,
            company_symbol="INOXWIND",
            company_name="Inox Wind Limited",
        )

    return _create
