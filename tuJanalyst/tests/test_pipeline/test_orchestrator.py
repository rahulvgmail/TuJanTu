"""Tests for Layer 1+2 pipeline orchestrator."""

from __future__ import annotations

from typing import Any

import pytest

from src.models.decision import DecisionAssessment, Recommendation, RecommendationTimeframe
from src.models.document import ProcessingStatus, RawDocument
from src.models.investigation import Investigation, SignificanceLevel
from src.models.report import AnalysisReport, ReportDeliveryStatus
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.pipeline.orchestrator import PipelineOrchestrator


class InMemoryTriggerRepo:
    def __init__(self, triggers: list[TriggerEvent] | None = None):
        self.items: dict[str, TriggerEvent] = {}
        self.updates: list[dict[str, Any]] = []
        for trigger in triggers or []:
            self.items[trigger.trigger_id] = trigger

    async def save(self, trigger: TriggerEvent) -> str:
        self.items[trigger.trigger_id] = trigger
        return trigger.trigger_id

    async def get(self, trigger_id: str) -> TriggerEvent | None:
        return self.items.get(trigger_id)

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None:
        trigger = self.items[trigger_id]
        trigger.set_status(status, reason)
        self.items[trigger_id] = trigger
        self.updates.append({"trigger_id": trigger_id, "status": status, "reason": reason})

    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]:
        pending = [item for item in self.items.values() if item.status == TriggerStatus.PENDING.value]
        pending.sort(key=lambda item: item.created_at)
        return pending[:limit]

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[TriggerEvent]:
        del company_symbol, limit
        return []

    async def exists_by_url(self, source_url: str) -> bool:
        del source_url
        return False

    async def list_recent(
        self,
        limit: int = 20,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
    ) -> list[TriggerEvent]:
        del limit, status, company_symbol
        return []


class InMemoryDocumentRepo:
    def __init__(self):
        self.items: dict[str, RawDocument] = {}

    async def save(self, document: RawDocument) -> str:
        self.items[document.document_id] = document
        return document.document_id

    async def get(self, document_id: str) -> RawDocument | None:
        return self.items.get(document_id)

    async def get_by_trigger(self, trigger_id: str) -> list[RawDocument]:
        return [doc for doc in self.items.values() if doc.trigger_id == trigger_id]

    async def update_extracted_text(self, document_id: str, text: str, method: str, metadata: dict) -> None:
        doc = self.items[document_id]
        doc.extracted_text = text
        doc.extraction_method = method
        doc.extraction_metadata = metadata
        self.items[document_id] = doc


class FakeVectorRepo:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        self.calls.append({"document_id": document_id, "text": text, "metadata": metadata})
        return f"vec-{document_id}"

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        del query, n_results, where
        return []

    async def delete_document(self, document_id: str) -> None:
        del document_id


class FakeDocumentFetcher:
    def __init__(self, returned_document: RawDocument | None):
        self.returned_document = returned_document
        self.calls: list[dict[str, Any]] = []

    async def fetch(self, trigger_id: str, url: str, company_symbol: str | None = None) -> RawDocument | None:
        self.calls.append({"trigger_id": trigger_id, "url": url, "company_symbol": company_symbol})
        return self.returned_document


class FakeTextExtractor:
    def __init__(self, returned_document: RawDocument | None):
        self.returned_document = returned_document
        self.calls: list[str] = []

    async def extract(self, document_id: str) -> RawDocument | None:
        self.calls.append(document_id)
        return self.returned_document


class FakeWatchlistFilter:
    def __init__(self, result: dict[str, str | bool]):
        self.result = result
        self.calls: list[str] = []

    def check(self, trigger: TriggerEvent) -> dict[str, str | bool]:
        self.calls.append(trigger.trigger_id)
        return self.result


class FakeGateClassifier:
    def __init__(self, result: dict[str, str | bool]):
        self.result = result
        self.calls: list[dict[str, str]] = []

    def classify(self, announcement_text: str, company_name: str = "", sector: str = "") -> dict[str, str | bool]:
        self.calls.append(
            {
                "announcement_text": announcement_text,
                "company_name": company_name,
                "sector": sector,
            }
        )
        return self.result


class FakeDeepAnalyzer:
    def __init__(self, investigation: Investigation):
        self.investigation = investigation
        self.calls: list[str] = []

    async def analyze(self, trigger: TriggerEvent) -> Investigation:
        self.calls.append(trigger.trigger_id)
        return self.investigation


class FakeDecisionAssessor:
    def __init__(self, assessment: DecisionAssessment):
        self.assessment = assessment
        self.calls: list[str] = []

    async def assess(self, investigation: Investigation) -> DecisionAssessment:
        self.calls.append(investigation.investigation_id)
        return self.assessment


class FakeReportGenerator:
    def __init__(self, report: AnalysisReport):
        self.report = report
        self.calls: list[dict[str, str]] = []

    async def generate(self, investigation: Investigation, assessment: DecisionAssessment) -> AnalysisReport:
        self.calls.append(
            {
                "investigation_id": investigation.investigation_id,
                "assessment_id": assessment.assessment_id,
            }
        )
        return self.report


class FakeReportDeliverer:
    def __init__(self, channels: list[str]):
        self.channels = channels
        self.calls: list[str] = []

    async def deliver(self, report: AnalysisReport) -> list[str]:
        self.calls.append(report.report_id)
        return self.channels


class FakeRaisingReportDeliverer:
    def __init__(self):
        self.calls: list[str] = []
        self.report_repo = None

    async def deliver(self, report: AnalysisReport) -> list[str]:
        self.calls.append(report.report_id)
        raise RuntimeError("slack webhook timeout")


class InMemoryReportRepo:
    def __init__(self):
        self.items: dict[str, AnalysisReport] = {}

    async def save(self, report: AnalysisReport) -> str:
        self.items[report.report_id] = report
        return report.report_id


@pytest.mark.asyncio
async def test_orchestrator_processes_watched_trigger_and_passes_gate() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        source_url="https://example.test/announcement",
        raw_content="Initial announcement text",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])
    doc_repo = InMemoryDocumentRepo()
    vector_repo = FakeVectorRepo()

    fetched_doc = RawDocument(
        document_id="doc-1",
        trigger_id=trigger.trigger_id,
        source_url=trigger.source_url or "",
        processing_status=ProcessingStatus.DOWNLOADED,
        company_symbol="INOXWIND",
    )
    extracted_doc = RawDocument(
        document_id="doc-1",
        trigger_id=trigger.trigger_id,
        source_url=trigger.source_url or "",
        extracted_text="Extracted quarterly metrics",
        processing_status=ProcessingStatus.EXTRACTED,
        company_symbol="INOXWIND",
    )
    document_fetcher = FakeDocumentFetcher(fetched_doc)
    text_extractor = FakeTextExtractor(extracted_doc)
    watchlist_filter = FakeWatchlistFilter({"passed": True, "reason": "Watched symbol", "method": "symbol_match"})
    gate_classifier = FakeGateClassifier(
        {
            "passed": True,
            "reason": "Quarterly results with margin expansion",
            "method": "llm_classification",
            "model": "claude-haiku",
        }
    )

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=doc_repo,
        vector_repo=vector_repo,
        document_fetcher=document_fetcher,
        text_extractor=text_extractor,
        watchlist_filter=watchlist_filter,
        gate_classifier=gate_classifier,
    )

    result = await orchestrator.process_trigger(trigger)

    assert result["passed"] is True
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.GATE_PASSED.value
    assert trigger.document_ids == ["doc-1"]
    assert "Extracted quarterly metrics" in trigger.raw_content
    assert len(gate_classifier.calls) == 1
    assert len(vector_repo.calls) == 1
    assert doc_repo.items["doc-1"].vector_id == "vec-doc-1"
    assert doc_repo.items["doc-1"].processing_status == ProcessingStatus.COMPLETE.value


@pytest.mark.asyncio
async def test_orchestrator_filters_out_unwatched_trigger_without_llm_call() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        raw_content="Routine filing",
        company_symbol="UNKNOWNCO",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])
    doc_repo = InMemoryDocumentRepo()
    vector_repo = FakeVectorRepo()
    watchlist_filter = FakeWatchlistFilter({"passed": False, "reason": "No watchlist match", "method": "no_match"})
    gate_classifier = FakeGateClassifier(
        {"passed": True, "reason": "Should not be called", "method": "llm_classification", "model": "x"}
    )

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=doc_repo,
        vector_repo=vector_repo,
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=watchlist_filter,
        gate_classifier=gate_classifier,
    )

    result = await orchestrator.process_trigger(trigger)

    assert result["passed"] is False
    assert result["method"] == "no_match"
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.FILTERED_OUT.value
    assert gate_classifier.calls == []


@pytest.mark.asyncio
async def test_orchestrator_human_trigger_bypasses_layer2_gate() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        raw_content="Manual investigation request",
        company_symbol="SIEMENS",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])
    gate_classifier = FakeGateClassifier(
        {"passed": False, "reason": "Should not be called", "method": "llm_classification", "model": "x"}
    )

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=InMemoryDocumentRepo(),
        vector_repo=FakeVectorRepo(),
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=FakeWatchlistFilter({"passed": False, "reason": "no", "method": "no_match"}),
        gate_classifier=gate_classifier,
    )

    result = await orchestrator.process_trigger(trigger)

    assert result["passed"] is True
    assert result["method"] == "human_bypass"
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.GATE_PASSED.value
    assert gate_classifier.calls == []


@pytest.mark.asyncio
async def test_orchestrator_process_pending_triggers_returns_processed_count() -> None:
    human_trigger = TriggerEvent(source=TriggerSource.HUMAN, raw_content="manual")
    exchange_trigger = TriggerEvent(source=TriggerSource.NSE_RSS, raw_content="routine notice")
    trigger_repo = InMemoryTriggerRepo([human_trigger, exchange_trigger])

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=InMemoryDocumentRepo(),
        vector_repo=FakeVectorRepo(),
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=FakeWatchlistFilter({"passed": False, "reason": "No match", "method": "no_match"}),
        gate_classifier=FakeGateClassifier(
            {"passed": True, "reason": "Should not be called", "method": "llm_classification", "model": "x"}
        ),
    )

    processed = await orchestrator.process_pending_triggers(limit=10)

    assert processed == 2
    assert trigger_repo.items[human_trigger.trigger_id].status == TriggerStatus.GATE_PASSED.value
    assert trigger_repo.items[exchange_trigger.trigger_id].status == TriggerStatus.FILTERED_OUT.value


@pytest.mark.asyncio
async def test_orchestrator_runs_full_layers_3_to_5_for_significant_investigation() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        raw_content="Manual high-priority trigger",
        company_symbol="ABB",
        company_name="ABB India",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])

    investigation = Investigation(
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        synthesis="Material order inflow change with margin impact.",
        significance=SignificanceLevel.HIGH,
        is_significant=True,
    )
    assessment = DecisionAssessment(
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        new_recommendation=Recommendation.BUY,
        timeframe=RecommendationTimeframe.MEDIUM_TERM,
        confidence=0.74,
        reasoning="Order quality and execution support upside.",
    )
    report = AnalysisReport(
        assessment_id=assessment.assessment_id,
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        title="ABB India Investment Update",
        recommendation_summary="BUY (Confidence: 74%, Timeframe: medium_term)",
    )

    deep_analyzer = FakeDeepAnalyzer(investigation)
    decision_assessor = FakeDecisionAssessor(assessment)
    report_generator = FakeReportGenerator(report)
    report_deliverer = FakeReportDeliverer(["slack"])

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=InMemoryDocumentRepo(),
        vector_repo=FakeVectorRepo(),
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=FakeWatchlistFilter({"passed": True, "reason": "ignored", "method": "human"}),
        gate_classifier=FakeGateClassifier({"passed": True, "reason": "ignored", "method": "human"}),
        deep_analyzer=deep_analyzer,
        decision_assessor=decision_assessor,
        report_generator=report_generator,
        report_deliverer=report_deliverer,
    )

    await orchestrator.process_trigger(trigger)

    assert deep_analyzer.calls == [trigger.trigger_id]
    assert decision_assessor.calls == [investigation.investigation_id]
    assert report_generator.calls == [
        {
            "investigation_id": investigation.investigation_id,
            "assessment_id": assessment.assessment_id,
        }
    ]
    assert report_deliverer.calls == [report.report_id]

    status_history = [entry.status for entry in trigger_repo.items[trigger.trigger_id].status_history]
    assert status_history == [
        TriggerStatus.GATE_PASSED.value,
        TriggerStatus.ANALYZING.value,
        TriggerStatus.ANALYZED.value,
        TriggerStatus.ASSESSING.value,
        TriggerStatus.ASSESSED.value,
        TriggerStatus.REPORTED.value,
    ]
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.REPORTED.value


@pytest.mark.asyncio
async def test_orchestrator_stops_after_layer3_when_investigation_not_significant() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        raw_content="Manual low-priority trigger",
        company_symbol="BHEL",
        company_name="BHEL",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])

    investigation = Investigation(
        trigger_id=trigger.trigger_id,
        company_symbol="BHEL",
        company_name="BHEL",
        synthesis="No material change detected in filing.",
        significance=SignificanceLevel.LOW,
        is_significant=False,
    )
    assessment = DecisionAssessment(
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="BHEL",
        company_name="BHEL",
        new_recommendation=Recommendation.HOLD,
        timeframe=RecommendationTimeframe.MEDIUM_TERM,
        confidence=0.51,
        reasoning="Signal is not material.",
    )
    report = AnalysisReport(
        assessment_id=assessment.assessment_id,
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="BHEL",
        company_name="BHEL",
    )

    deep_analyzer = FakeDeepAnalyzer(investigation)
    decision_assessor = FakeDecisionAssessor(assessment)
    report_generator = FakeReportGenerator(report)
    report_deliverer = FakeReportDeliverer(["slack"])

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=InMemoryDocumentRepo(),
        vector_repo=FakeVectorRepo(),
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=FakeWatchlistFilter({"passed": True, "reason": "ignored", "method": "human"}),
        gate_classifier=FakeGateClassifier({"passed": True, "reason": "ignored", "method": "human"}),
        deep_analyzer=deep_analyzer,
        decision_assessor=decision_assessor,
        report_generator=report_generator,
        report_deliverer=report_deliverer,
    )

    await orchestrator.process_trigger(trigger)

    assert deep_analyzer.calls == [trigger.trigger_id]
    assert decision_assessor.calls == []
    assert report_generator.calls == []
    assert report_deliverer.calls == []

    status_history = [entry.status for entry in trigger_repo.items[trigger.trigger_id].status_history]
    assert status_history == [
        TriggerStatus.GATE_PASSED.value,
        TriggerStatus.ANALYZING.value,
        TriggerStatus.ANALYZED.value,
    ]
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.ANALYZED.value


@pytest.mark.asyncio
async def test_orchestrator_marks_delivery_failure_and_keeps_reported_status() -> None:
    trigger = TriggerEvent(
        source=TriggerSource.HUMAN,
        raw_content="Manual trigger",
        company_symbol="ABB",
        company_name="ABB India",
    )
    trigger_repo = InMemoryTriggerRepo([trigger])

    investigation = Investigation(
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        synthesis="Material findings",
        significance=SignificanceLevel.HIGH,
        is_significant=True,
    )
    assessment = DecisionAssessment(
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        new_recommendation=Recommendation.BUY,
        timeframe=RecommendationTimeframe.MEDIUM_TERM,
        confidence=0.7,
        reasoning="Positive setup",
    )
    report = AnalysisReport(
        assessment_id=assessment.assessment_id,
        investigation_id=investigation.investigation_id,
        trigger_id=trigger.trigger_id,
        company_symbol="ABB",
        company_name="ABB India",
        title="ABB report",
        recommendation_summary="BUY (Confidence: 70%, Timeframe: medium_term)",
    )
    report_repo = InMemoryReportRepo()
    report_generator = FakeReportGenerator(report)
    report_generator.report_repo = report_repo  # type: ignore[attr-defined]
    report_deliverer = FakeRaisingReportDeliverer()

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=InMemoryDocumentRepo(),
        vector_repo=FakeVectorRepo(),
        document_fetcher=FakeDocumentFetcher(None),
        text_extractor=FakeTextExtractor(None),
        watchlist_filter=FakeWatchlistFilter({"passed": True, "reason": "ignored", "method": "human"}),
        gate_classifier=FakeGateClassifier({"passed": True, "reason": "ignored", "method": "human"}),
        deep_analyzer=FakeDeepAnalyzer(investigation),
        decision_assessor=FakeDecisionAssessor(assessment),
        report_generator=report_generator,
        report_deliverer=report_deliverer,
        report_repo=report_repo,
    )

    await orchestrator.process_trigger(trigger)

    saved = report_repo.items[report.report_id]
    assert saved.delivery_status == ReportDeliveryStatus.DELIVERY_FAILED.value
    assert trigger_repo.items[trigger.trigger_id].status == TriggerStatus.REPORTED.value
    assert "delivery failed" in trigger_repo.updates[-1]["reason"].lower()
