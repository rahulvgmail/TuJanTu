"""Tests for MongoDB connection/bootstrap helpers."""

from __future__ import annotations

from typing import Any

import pytest

from src.repositories.mongo import (
    ASSESSMENTS_COLLECTION,
    DOCUMENTS_COLLECTION,
    INVESTIGATIONS_COLLECTION,
    POSITIONS_COLLECTION,
    REPORTS_COLLECTION,
    TRIGGERS_COLLECTION,
    ensure_indexes,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.index_calls: list[dict[str, Any]] = []

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> None:
        self.index_calls.append({"keys": keys, **kwargs})


class _FakeDatabase:
    def __init__(self) -> None:
        self.collections = {
            TRIGGERS_COLLECTION: _FakeCollection(),
            DOCUMENTS_COLLECTION: _FakeCollection(),
            INVESTIGATIONS_COLLECTION: _FakeCollection(),
            ASSESSMENTS_COLLECTION: _FakeCollection(),
            POSITIONS_COLLECTION: _FakeCollection(),
            REPORTS_COLLECTION: _FakeCollection(),
        }

    def __getitem__(self, name: str) -> _FakeCollection:
        return self.collections[name]


@pytest.mark.asyncio
async def test_ensure_indexes_creates_expected_indexes() -> None:
    db = _FakeDatabase()
    await ensure_indexes(db)  # type: ignore[arg-type]

    trigger_index_names = {call["name"] for call in db.collections[TRIGGERS_COLLECTION].index_calls}
    document_index_names = {call["name"] for call in db.collections[DOCUMENTS_COLLECTION].index_calls}
    investigation_index_names = {call["name"] for call in db.collections[INVESTIGATIONS_COLLECTION].index_calls}
    assessment_index_names = {call["name"] for call in db.collections[ASSESSMENTS_COLLECTION].index_calls}
    position_index_names = {call["name"] for call in db.collections[POSITIONS_COLLECTION].index_calls}
    report_index_names = {call["name"] for call in db.collections[REPORTS_COLLECTION].index_calls}

    assert trigger_index_names == {
        "uq_trigger_id",
        "idx_source_url",
        "idx_status",
        "idx_trigger_company_symbol",
        "idx_trigger_created_at",
    }
    assert document_index_names == {
        "uq_document_id",
        "idx_document_trigger_id",
        "idx_document_company_symbol",
    }
    assert investigation_index_names == {
        "uq_investigation_id",
        "idx_investigation_company_created",
        "idx_investigation_significant",
    }
    assert assessment_index_names == {
        "uq_assessment_id",
        "idx_assessment_investigation_id",
        "idx_assessment_company_created",
    }
    assert position_index_names == {
        "uq_position_company_symbol",
    }
    assert report_index_names == {
        "uq_report_id",
        "idx_report_created_at",
        "idx_report_company_symbol",
    }
