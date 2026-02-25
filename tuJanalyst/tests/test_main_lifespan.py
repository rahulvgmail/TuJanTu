"""Tests for application lifespan startup/shutdown wiring."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI

import src.main as main_module


class _Stub:
    def __init__(self, *args: Any, **kwargs: Any):
        del args, kwargs


class _FakeMongoClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeRSSPoller:
    def __init__(self, *args: Any, **kwargs: Any):
        del args, kwargs

    async def poll(self) -> int:
        return 0


class _FakeOrchestrator:
    def __init__(self, *args: Any, **kwargs: Any):
        del args, kwargs

    async def process_pending_triggers(self, limit: int = 50) -> int:
        return limit


class _FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.running = False
        self.shutdown_called = False
        self.shutdown_wait: bool | None = None

    def add_job(self, func: Any, **kwargs: Any) -> None:
        self.jobs.append({"func": func, **kwargs})

    def start(self) -> None:
        self.running = True

    def shutdown(self, wait: bool = False) -> None:
        self.shutdown_called = True
        self.shutdown_wait = wait
        self.running = False


@pytest.mark.asyncio
async def test_lifespan_registers_trigger_processor_with_batch_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mongo_client = _FakeMongoClient()
    fake_scheduler = _FakeScheduler()

    async def _fake_create_mongo_client(uri: str) -> _FakeMongoClient:
        assert uri == "mongodb://example"
        return fake_mongo_client

    async def _fake_ensure_indexes(db: Any) -> None:
        del db

    settings = SimpleNamespace(
        llm_provider="local",
        watchlist_config_path=Path("config/watchlist.yaml"),
        mongodb_uri="mongodb://example",
        mongodb_database="tujanalyst_test",
        chromadb_persist_dir=Path("data/chromadb"),
        embedding_model="all-MiniLM-L6-v2",
        max_document_size_mb=50,
        text_extraction_timeout_seconds=60,
        gate_model="gate-model",
        resolved_llm_api_key=None,
        llm_base_url=None,
        enable_layer3_analysis=False,
        enable_layer4_decision=False,
        enable_layer5_reporting=False,
        polling_enabled=True,
        polling_interval_seconds=90,
        nse_rss_url="https://nse.example/rss",
        bse_rss_url="https://bse.example/rss",
        rss_dedup_cache_ttl_seconds=1800,
        rss_dedup_lookback_days=14,
        rss_dedup_recent_limit=5000,
    )

    monkeypatch.setattr(main_module, "setup_logging", lambda: None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        main_module,
        "load_watchlist_config",
        lambda _path: SimpleNamespace(companies=[{"symbol": "SUZLON"}], sectors=[{"name": "energy"}]),
    )
    monkeypatch.setattr(main_module, "create_mongo_client", _fake_create_mongo_client)
    monkeypatch.setattr(main_module, "get_database", lambda client, db_name: {"client": client, "db_name": db_name})
    monkeypatch.setattr(main_module, "ensure_indexes", _fake_ensure_indexes)

    monkeypatch.setattr(main_module, "MongoTriggerRepository", _Stub)
    monkeypatch.setattr(main_module, "MongoDocumentRepository", _Stub)
    monkeypatch.setattr(main_module, "MongoInvestigationRepository", _Stub)
    monkeypatch.setattr(main_module, "MongoAssessmentRepository", _Stub)
    monkeypatch.setattr(main_module, "MongoPositionRepository", _Stub)
    monkeypatch.setattr(main_module, "MongoReportRepository", _Stub)
    monkeypatch.setattr(main_module, "ChromaVectorRepository", _Stub)
    monkeypatch.setattr(main_module, "DocumentFetcher", _Stub)
    monkeypatch.setattr(main_module, "TextExtractor", _Stub)
    monkeypatch.setattr(main_module, "WatchlistFilter", _Stub)
    monkeypatch.setattr(main_module, "GateClassifier", _Stub)
    monkeypatch.setattr(main_module, "PipelineOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(main_module, "ExchangeRSSPoller", _FakeRSSPoller)
    monkeypatch.setattr(main_module, "AsyncIOScheduler", lambda: fake_scheduler)

    app = FastAPI()
    async with main_module.lifespan(app):
        assert app.state.scheduler is fake_scheduler
        assert fake_scheduler.running is True

        jobs_by_id = {job["id"]: job for job in fake_scheduler.jobs}
        assert set(jobs_by_id) == {"rss_poller", "trigger_processor"}
        assert jobs_by_id["rss_poller"]["seconds"] == 90
        assert jobs_by_id["trigger_processor"]["seconds"] == 30
        assert jobs_by_id["trigger_processor"]["kwargs"] == {"limit": main_module._TRIGGER_PROCESSOR_BATCH_LIMIT}
        assert jobs_by_id["trigger_processor"]["coalesce"] is True
        assert jobs_by_id["trigger_processor"]["max_instances"] == 1

    assert fake_scheduler.shutdown_called is True
    assert fake_scheduler.shutdown_wait is False
    assert fake_mongo_client.closed is True
