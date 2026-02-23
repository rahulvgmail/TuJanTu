"""Pipeline orchestrator for trigger ingestion, gating, and downstream analysis."""

from __future__ import annotations

import inspect
from typing import Any

import structlog

from src.models.document import ProcessingStatus, RawDocument
from src.models.report import ReportDeliveryStatus
from src.models.trigger import TriggerEvent, TriggerSource, TriggerStatus
from src.repositories.base import DocumentRepository, TriggerRepository, VectorRepository

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    """Run triggers through document ingestion, gate, and optional Layers 3-5."""

    def __init__(
        self,
        trigger_repo: TriggerRepository,
        doc_repo: DocumentRepository,
        vector_repo: VectorRepository,
        document_fetcher: Any,
        text_extractor: Any,
        watchlist_filter: Any,
        gate_classifier: Any,
        deep_analyzer: Any | None = None,
        decision_assessor: Any | None = None,
        report_generator: Any | None = None,
        report_deliverer: Any | None = None,
    ):
        self.trigger_repo = trigger_repo
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo
        self.document_fetcher = document_fetcher
        self.text_extractor = text_extractor
        self.watchlist_filter = watchlist_filter
        self.gate_classifier = gate_classifier
        self.deep_analyzer = deep_analyzer
        self.decision_assessor = decision_assessor
        self.report_generator = report_generator
        self.report_deliverer = report_deliverer

    async def process_trigger(self, trigger: TriggerEvent) -> dict[str, str | bool]:
        """Process a single trigger through configured pipeline layers."""
        structlog.contextvars.bind_contextvars(
            trigger_id=trigger.trigger_id,
            company_symbol=trigger.company_symbol,
            source=str(trigger.source),
        )
        log = logger.bind(component="orchestrator")
        log.info("trigger_processing_started")
        try:
            await self._process_documents(trigger)
            gate_result = await self._run_gate(trigger)
            trigger.gate_result = gate_result
            log.info(
                "gate_decision",
                gate_passed=bool(gate_result.get("passed")),
                gate_method=str(gate_result.get("method", "")),
                gate_model=str(gate_result.get("model", "")),
                gate_reason=str(gate_result.get("reason", "")),
            )

            if bool(gate_result.get("passed")):
                await self.trigger_repo.update_status(
                    trigger.trigger_id,
                    TriggerStatus.GATE_PASSED,
                    str(gate_result.get("reason", "")),
                )
                await self._run_post_gate_pipeline(trigger)
            else:
                await self.trigger_repo.update_status(
                    trigger.trigger_id,
                    TriggerStatus.FILTERED_OUT,
                    str(gate_result.get("reason", "")),
                )
                log.info("trigger_filtered_out")
            return gate_result
        except Exception as exc:  # noqa: BLE001
            log.exception("trigger_processing_failed", error=str(exc))
            await self.trigger_repo.update_status(trigger.trigger_id, TriggerStatus.ERROR, f"Pipeline error: {exc}")
            return {
                "passed": False,
                "reason": f"Pipeline error: {exc}",
                "method": "pipeline_error",
                "model": "n/a",
            }
        finally:
            structlog.contextvars.clear_contextvars()

    async def _run_post_gate_pipeline(self, trigger: TriggerEvent) -> None:
        """Run Layers 3-5 when corresponding dependencies are configured."""
        if self.deep_analyzer is None:
            logger.info("layer3_not_configured_skipping")
            return

        await self.trigger_repo.update_status(
            trigger.trigger_id,
            TriggerStatus.ANALYZING,
            "Starting deep analysis",
        )
        logger.info("layer3_started")
        try:
            investigation = await self.deep_analyzer.analyze(trigger)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Layer 3 analysis failed: {exc}") from exc
        significance = str(getattr(investigation, "significance", "unknown"))
        await self.trigger_repo.update_status(
            trigger.trigger_id,
            TriggerStatus.ANALYZED,
            f"Analysis complete. Significance: {significance}",
        )
        logger.info(
            "layer3_completed",
            significance=significance,
            is_significant=bool(getattr(investigation, "is_significant", False)),
            llm_model=str(getattr(investigation, "llm_model_used", "")),
            llm_input_tokens=int(getattr(investigation, "total_input_tokens", 0)),
            llm_output_tokens=int(getattr(investigation, "total_output_tokens", 0)),
            llm_latency_seconds=float(getattr(investigation, "processing_time_seconds", 0.0)),
        )

        if not bool(getattr(investigation, "is_significant", False)):
            logger.info("layer3_non_significant_stop")
            return

        if self.decision_assessor is None or self.report_generator is None or self.report_deliverer is None:
            logger.warning("layer4_or_layer5_not_configured_skipping")
            return

        await self.trigger_repo.update_status(
            trigger.trigger_id,
            TriggerStatus.ASSESSING,
            "Starting decision assessment",
        )
        logger.info("layer4_started")
        try:
            assessment = await self.decision_assessor.assess(investigation)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Layer 4 assessment failed: {exc}") from exc
        recommendation = self._enum_value(getattr(assessment, "new_recommendation", "none"))
        await self.trigger_repo.update_status(
            trigger.trigger_id,
            TriggerStatus.ASSESSED,
            f"Assessment complete. Recommendation: {recommendation}",
        )
        logger.info(
            "layer4_completed",
            recommendation=recommendation,
            confidence=float(getattr(assessment, "confidence", 0.0)),
            llm_model=str(getattr(assessment, "llm_model_used", "")),
            llm_input_tokens=int(getattr(assessment, "total_input_tokens", 0)),
            llm_output_tokens=int(getattr(assessment, "total_output_tokens", 0)),
            llm_latency_seconds=float(getattr(assessment, "processing_time_seconds", 0.0)),
        )

        try:
            report = await self.report_generator.generate(investigation, assessment)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Layer 5 report generation failed: {exc}") from exc
        logger.info(
            "layer5_report_generated",
            report_id=str(getattr(report, "report_id", "")),
            llm_model=str(getattr(self.report_generator, "model_name", "")),
        )

        try:
            channels = await self.report_deliverer.deliver(report)
        except Exception as exc:  # noqa: BLE001
            await self._persist_delivery_failure(report, exc)
            await self.trigger_repo.update_status(
                trigger.trigger_id,
                TriggerStatus.REPORTED,
                f"Report generated but delivery failed: {exc}",
            )
            logger.warning("layer5_delivery_failed", error=str(exc))
            return

        reason = "Report generated"
        if channels:
            reason = f"{reason} and delivered via {', '.join(channels)}"
        await self.trigger_repo.update_status(trigger.trigger_id, TriggerStatus.REPORTED, reason)
        logger.info(
            "layer5_completed",
            channels=channels,
            report_id=str(getattr(report, "report_id", "")),
            delivery_status=str(getattr(report, "delivery_status", "")),
        )

    async def process_pending_triggers(self, limit: int = 50) -> int:
        """Process pending triggers and return count of attempted items."""
        pending = await self.trigger_repo.get_pending(limit=limit)
        processed = 0
        for trigger in pending:
            await self.process_trigger(trigger)
            processed += 1
        return processed

    async def _process_documents(self, trigger: TriggerEvent) -> None:
        if not trigger.source_url:
            return
        if trigger.document_ids:
            return

        fetched = await self.document_fetcher.fetch(
            trigger_id=trigger.trigger_id,
            url=trigger.source_url,
            company_symbol=trigger.company_symbol,
        )
        if fetched is None:
            return

        trigger.document_ids.append(fetched.document_id)
        if self._status_value(fetched.processing_status) == ProcessingStatus.ERROR.value:
            return

        extracted = await self.text_extractor.extract(fetched.document_id)
        if extracted is None:
            return
        if extracted.extracted_text:
            trigger.raw_content = f"{trigger.raw_content}\n\n{extracted.extracted_text}".strip()
        await self._ensure_document_embedded(extracted)

    async def _run_gate(self, trigger: TriggerEvent) -> dict[str, str | bool]:
        if trigger.source == TriggerSource.HUMAN.value or trigger.source == TriggerSource.HUMAN:
            return {
                "passed": True,
                "reason": "Human trigger bypasses Layer 2 gate",
                "method": "human_bypass",
                "model": "n/a",
            }

        filter_result = self.watchlist_filter.check(trigger)
        if not bool(filter_result.get("passed")):
            return filter_result

        classification = self.gate_classifier.classify(
            announcement_text=trigger.raw_content,
            company_name=trigger.company_name or "",
            sector=trigger.sector or "",
        )
        return await self._maybe_await(classification)

    async def _ensure_document_embedded(self, document: RawDocument) -> None:
        if not document.extracted_text:
            return
        if document.vector_id:
            return

        metadata = {
            "company_symbol": document.company_symbol,
            "trigger_id": document.trigger_id,
            "document_type": str(document.document_type),
            "source": document.source_url,
        }
        try:
            document.processing_status = ProcessingStatus.EMBEDDING
            await self.doc_repo.save(document)
            vector_id = await self.vector_repo.add_document(
                document_id=document.document_id,
                text=document.extracted_text,
                metadata=metadata,
            )
            document.vector_id = vector_id
            document.processing_status = ProcessingStatus.COMPLETE
            await self.doc_repo.save(document)
        except Exception as exc:  # noqa: BLE001
            document.processing_status = ProcessingStatus.ERROR
            document.processing_errors.append(f"Embedding error: {exc}")
            await self.doc_repo.save(document)
            logger.warning("vector_embedding_failed", document_id=document.document_id, error=str(exc))

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _status_value(self, status: ProcessingStatus | str) -> str:
        if isinstance(status, ProcessingStatus):
            return status.value
        return str(status)

    def _enum_value(self, value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)

    async def _persist_delivery_failure(self, report: Any, error: Exception) -> None:
        report.delivery_status = ReportDeliveryStatus.DELIVERY_FAILED
        report.delivered_via = []
        report_repo = getattr(self.report_deliverer, "report_repo", None) or getattr(self.report_generator, "report_repo", None)
        if report_repo is None:
            logger.warning("report_repo_missing_for_delivery_failure", error=str(error))
            return
        try:
            await report_repo.save(report)
        except Exception as save_error:  # noqa: BLE001
            logger.warning(
                "delivery_failure_status_persist_failed",
                error=str(error),
                save_error=str(save_error),
            )
