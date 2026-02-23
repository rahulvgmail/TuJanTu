"""Tests for core Pydantic models used in Weeks 1-2."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.company import Company, WatchlistConfig
from src.models.document import DocumentType, ProcessingStatus, RawDocument
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus


def test_trigger_event_defaults_and_status_tracking() -> None:
    trigger = TriggerEvent(source=TriggerSource.HUMAN, raw_content="Important update")

    assert trigger.trigger_id
    assert trigger.status == TriggerStatus.PENDING.value
    assert trigger.status_history == []

    trigger.set_status(TriggerStatus.GATE_PASSED, "Human trigger bypass")

    assert trigger.status == TriggerStatus.GATE_PASSED.value
    assert len(trigger.status_history) == 1
    assert trigger.status_history[0].status == TriggerStatus.GATE_PASSED.value


def test_trigger_enum_serialization_uses_strings() -> None:
    trigger = TriggerEvent(source=TriggerSource.NSE_RSS, raw_content="Quarterly results")
    payload = trigger.model_dump(mode="json")

    assert payload["source"] == TriggerSource.NSE_RSS.value
    assert payload["status"] == TriggerStatus.PENDING.value


def test_raw_document_defaults_and_round_trip() -> None:
    document = RawDocument(trigger_id="trigger-1", source_url="https://example.com/report.pdf")

    assert document.document_id
    assert document.document_type == DocumentType.UNKNOWN.value
    assert document.processing_status == ProcessingStatus.PENDING.value

    payload = document.model_dump(mode="json")
    rebuilt = RawDocument.model_validate(payload)

    assert rebuilt.document_id == document.document_id
    assert rebuilt.source_url == "https://example.com/report.pdf"


def test_watchlist_config_validates_duplicate_symbols() -> None:
    with pytest.raises(ValidationError):
        WatchlistConfig.model_validate(
            {
                "sectors": [{"name": "Capital Goods", "keywords": ["results"]}],
                "companies": [
                    {"symbol": "INOXWIND", "name": "Inox Wind"},
                    {"symbol": "inoxwind", "name": "Inox Wind Duplicate"},
                ],
            }
        )


def test_company_symbol_normalization() -> None:
    company = Company(symbol="suzlon", name="Suzlon Energy Limited")
    assert company.symbol == "SUZLON"

