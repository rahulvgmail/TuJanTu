"""Week 4 integration test: full pipeline across Layers 1-5."""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.dspy_modules.decision import DecisionModuleResult
from src.dspy_modules.report import ReportModuleResult
from src.models.decision import Recommendation, RecommendationTimeframe
from src.models.investigation import Investigation, SignificanceLevel
from src.models.report import ReportDeliveryStatus
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.pipeline.layer4_decision.assessor import DecisionAssessor
from src.pipeline.layer5_report.deliverer import ReportDeliverer
from src.pipeline.layer5_report.generator import ReportGenerator
from src.pipeline.orchestrator import PipelineOrchestrator
from src.repositories.mongo import (
    MongoAssessmentRepository,
    MongoDocumentRepository,
    MongoInvestigationRepository,
    MongoPositionRepository,
    MongoReportRepository,
    MongoTriggerRepository,
)


class _NoopDocumentFetcher:
    async def fetch(self, trigger_id: str, url: str, company_symbol: str | None = None):
        del trigger_id, url, company_symbol
        return None


class _NoopTextExtractor:
    async def extract(self, document_id: str):
        del document_id
        return None


class _NoopVectorRepo:
    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        del text, metadata
        return f"vec-{document_id}"

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        del query, n_results, where
        return []

    async def delete_document(self, document_id: str) -> None:
        del document_id


class _PassWatchlistFilter:
    def check(self, trigger: TriggerEvent) -> dict[str, str | bool]:
        return {"passed": True, "reason": f"Watchlist match: {trigger.company_symbol}", "method": "symbol_match"}


class _PassGateClassifier:
    def classify(self, announcement_text: str, company_name: str = "", sector: str = "") -> dict[str, str | bool]:
        del announcement_text, company_name, sector
        return {
            "passed": True,
            "reason": "Material trigger content",
            "method": "llm_classification",
            "model": "test-gate",
        }


class _FakeDeepAnalyzer:
    def __init__(self, investigation_repo, significance_by_symbol: dict[str, bool]):
        self.repo = investigation_repo
        self.significance_by_symbol = significance_by_symbol

    async def analyze(self, trigger: TriggerEvent) -> Investigation:
        is_significant = bool(self.significance_by_symbol.get(trigger.company_symbol or "", True))
        investigation = Investigation(
            trigger_id=trigger.trigger_id,
            company_symbol=(trigger.company_symbol or "UNKNOWN").upper(),
            company_name=trigger.company_name or "Unknown Company",
            synthesis=f"{trigger.company_name or trigger.company_symbol}: synthesized analysis summary.",
            key_findings=["Revenue trend improved", "Order pipeline healthy"],
            red_flags=["Input-cost volatility"],
            positive_signals=["Execution consistency"],
            significance=SignificanceLevel.HIGH if is_significant else SignificanceLevel.LOW,
            is_significant=is_significant,
            llm_model_used="test-analysis",
        )
        await self.repo.save(investigation)
        return investigation


class _FakeDecisionModule:
    def forward(self, **kwargs: Any) -> DecisionModuleResult:
        del kwargs
        return DecisionModuleResult(
            should_change=True,
            new_recommendation=Recommendation.BUY,
            timeframe=RecommendationTimeframe.MEDIUM_TERM,
            confidence=0.73,
            reasoning="Evidence supports a positive medium-term stance.",
            key_factors=["Order momentum", "Margin stability"],
        )


class _FakeReportModule:
    def forward(self, **kwargs: Any) -> ReportModuleResult:
        company_name = kwargs.get("company_name", "Company")
        symbol = kwargs.get("company_symbol", "")
        recommendation = str(kwargs.get("recommendation", "hold")).upper()
        confidence = float(kwargs.get("confidence", 0.0))
        timeframe = str(kwargs.get("timeframe", "medium_term"))
        return ReportModuleResult(
            title=f"{company_name} ({symbol}) Update",
            executive_summary="Summary generated for investment-team review.",
            report_body_markdown="# Report\n\nKey findings and recommendation.",
            recommendation_summary=(
                f"{recommendation} (Confidence: {confidence * 100:.0f}%, Timeframe: {timeframe})"
            ),
        )


@pytest.mark.asyncio
async def test_week4_full_pipeline_end_to_end(mongo_db, monkeypatch: pytest.MonkeyPatch) -> None:
    trigger_repo = MongoTriggerRepository(mongo_db)
    document_repo = MongoDocumentRepository(mongo_db)
    investigation_repo = MongoInvestigationRepository(mongo_db)
    assessment_repo = MongoAssessmentRepository(mongo_db)
    position_repo = MongoPositionRepository(mongo_db)
    report_repo = MongoReportRepository(mongo_db)

    deep_analyzer = _FakeDeepAnalyzer(
        investigation_repo=investigation_repo,
        significance_by_symbol={
            "ABB": True,
            "INOXWIND": True,
            "SIEMENS": True,
            "SUZLON": True,
            "BHEL": False,
        },
    )
    decision_assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=_FakeDecisionModule(),  # type: ignore[arg-type]
        model_name="test-decision",
    )
    report_generator = ReportGenerator(
        report_repo=report_repo,
        report_module=_FakeReportModule(),  # type: ignore[arg-type]
        model_name="test-report",
    )
    report_deliverer = ReportDeliverer(
        slack_webhook_url="https://example.test/webhook",
        report_repo=report_repo,
    )

    delivered_ids: list[str] = []

    async def _deliver_slack(report) -> bool:
        delivered_ids.append(report.report_id)
        return True

    monkeypatch.setattr(report_deliverer, "_deliver_slack", _deliver_slack)

    orchestrator = PipelineOrchestrator(
        trigger_repo=trigger_repo,
        doc_repo=document_repo,
        vector_repo=_NoopVectorRepo(),
        document_fetcher=_NoopDocumentFetcher(),
        text_extractor=_NoopTextExtractor(),
        watchlist_filter=_PassWatchlistFilter(),
        gate_classifier=_PassGateClassifier(),
        deep_analyzer=deep_analyzer,
        decision_assessor=decision_assessor,
        report_generator=report_generator,
        report_deliverer=report_deliverer,
    )

    triggers = [
        TriggerEvent(
            source=TriggerSource.HUMAN,
            raw_content="Manual priority trigger",
            company_symbol="ABB",
            company_name="ABB India",
        ),
        TriggerEvent(
            source=TriggerSource.NSE_RSS,
            raw_content="NSE trigger 1",
            company_symbol="INOXWIND",
            company_name="Inox Wind Limited",
        ),
        TriggerEvent(
            source=TriggerSource.NSE_RSS,
            raw_content="NSE trigger 2",
            company_symbol="BHEL",
            company_name="BHEL",
        ),
        TriggerEvent(
            source=TriggerSource.BSE_RSS,
            raw_content="BSE trigger 1",
            company_symbol="SIEMENS",
            company_name="Siemens Limited",
        ),
        TriggerEvent(
            source=TriggerSource.BSE_RSS,
            raw_content="BSE trigger 2",
            company_symbol="SUZLON",
            company_name="Suzlon Energy Limited",
        ),
    ]

    for item in triggers:
        await trigger_repo.save(item)

    per_trigger_seconds: list[float] = []
    for item in triggers:
        started = time.perf_counter()
        result = await orchestrator.process_trigger(item)
        elapsed = time.perf_counter() - started
        per_trigger_seconds.append(elapsed)
        assert result["passed"] is True

    assert len(triggers) == 5
    assert sum(1 for item in triggers if item.source == TriggerSource.HUMAN.value) == 1
    assert sum(1 for item in triggers if item.source == TriggerSource.NSE_RSS.value) >= 1
    assert sum(1 for item in triggers if item.source == TriggerSource.BSE_RSS.value) >= 1
    assert all(duration < 300 for duration in per_trigger_seconds)

    assert await mongo_db["investigations"].count_documents({}) == 5
    assert await mongo_db["assessments"].count_documents({}) == 4
    assert await mongo_db["reports"].count_documents({}) == 4
    assert await mongo_db["positions"].count_documents({}) == 4
    assert len(delivered_ids) == 4

    bhel_record = await trigger_repo.get(triggers[2].trigger_id)
    assert bhel_record is not None
    assert bhel_record.status == TriggerStatus.ANALYZED.value

    for idx in [0, 1, 3, 4]:
        processed = await trigger_repo.get(triggers[idx].trigger_id)
        assert processed is not None
        assert processed.status == TriggerStatus.REPORTED.value

    reports = await report_repo.get_recent(limit=10)
    assert len(reports) == 4
    assert all(item.delivery_status == ReportDeliveryStatus.DELIVERED.value for item in reports)
