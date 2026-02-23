"""Tests for structured logging and trigger traceability."""

from __future__ import annotations

import json
import logging

import pytest
import structlog

from src.logging_setup import configure_structured_logging
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.pipeline.orchestrator import PipelineOrchestrator


class _TriggerRepo:
    def __init__(self, trigger: TriggerEvent):
        self.trigger = trigger

    async def save(self, trigger: TriggerEvent) -> str:
        self.trigger = trigger
        return trigger.trigger_id

    async def get(self, trigger_id: str):  # noqa: ARG002
        return self.trigger

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None:  # noqa: ARG002
        self.trigger.set_status(status, reason)

    async def get_pending(self, limit: int = 50):  # noqa: ARG002
        return []


class _NoopRepo:
    async def save(self, value):  # noqa: ANN001
        del value
        return "ok"


class _NoopVectorRepo:
    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:  # noqa: ARG002
        return document_id


class _NoopFetcher:
    async def fetch(self, trigger_id: str, url: str, company_symbol: str | None = None):  # noqa: ARG002
        return None


class _NoopExtractor:
    async def extract(self, document_id: str):  # noqa: ARG002
        return None


class _NoopWatchlist:
    def check(self, trigger):  # noqa: ANN001
        del trigger
        return {"passed": True, "reason": "match", "method": "symbol_match"}


class _NoopGate:
    def classify(self, announcement_text: str, company_name: str = "", sector: str = ""):  # noqa: ARG002
        return {"passed": True, "reason": "human", "method": "human_bypass", "model": "n/a"}


def test_structlog_json_includes_contextvars(caplog: pytest.LogCaptureFixture) -> None:
    configure_structured_logging()
    caplog.set_level(logging.INFO)

    structlog.contextvars.bind_contextvars(trigger_id="trigger-1", company_symbol="ABB")
    structlog.get_logger("test").info("pipeline_stage", stage="analyzing")
    structlog.contextvars.clear_contextvars()

    payload = json.loads(caplog.records[-1].getMessage())
    assert payload["event"] == "pipeline_stage"
    assert payload["trigger_id"] == "trigger-1"
    assert payload["company_symbol"] == "ABB"
    assert payload["stage"] == "analyzing"


@pytest.mark.asyncio
async def test_orchestrator_logs_include_trigger_context(caplog: pytest.LogCaptureFixture) -> None:
    configure_structured_logging()
    caplog.set_level(logging.INFO)

    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        raw_content="Manual request",
        company_symbol="ABB",
        company_name="ABB India",
    )
    trigger_repo = _TriggerRepo(trigger)

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=_NoopRepo(),
        vector_repo=_NoopVectorRepo(),
        document_fetcher=_NoopFetcher(),
        text_extractor=_NoopExtractor(),
        watchlist_filter=_NoopWatchlist(),
        gate_classifier=_NoopGate(),
    )

    await orchestrator.process_trigger(trigger)

    events = []
    for record in caplog.records:
        try:
            events.append(json.loads(record.getMessage()))
        except Exception:  # noqa: BLE001
            continue

    gate_event = next(item for item in events if item.get("event") == "gate_decision")
    assert gate_event["trigger_id"] == trigger.trigger_id
    assert gate_event["company_symbol"] == "ABB"
    assert gate_event["gate_passed"] is True
