"""Layer 3 deep-analysis orchestrator."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.dspy_modules.analysis import DeepAnalysisPipeline, DeepAnalysisResult, WebSearchModule
from src.models.investigation import (
    ExtractedMetric,
    ForwardStatement,
    HistoricalContext,
    Investigation,
    SignificanceLevel,
    WebSearchResult,
)
from src.utils.retry import is_transient_error, retry_in_thread
from src.utils.token_usage import run_with_dspy_usage

logger = logging.getLogger(__name__)


class DeepAnalyzer:
    """Run Layer 3 deep analysis for a gate-passed trigger."""

    def __init__(
        self,
        *,
        investigation_repo: Any,
        vector_repo: Any,
        doc_repo: Any,
        web_search: Any,
        market_data: Any,
        analysis_pipeline: DeepAnalysisPipeline | None = None,
        web_search_module: WebSearchModule | None = None,
        model_name: str = "analysis-pipeline",
    ):
        self.investigation_repo = investigation_repo
        self.vector_repo = vector_repo
        self.doc_repo = doc_repo
        self.web_search = web_search
        self.market_data = market_data
        self.pipeline = analysis_pipeline or DeepAnalysisPipeline()
        self.web_search_module = web_search_module or WebSearchModule()
        self.model_name = model_name

    async def analyze(self, trigger: Any) -> Investigation:
        """Produce and persist an Investigation from a gate-passed trigger."""
        started_at = time.time()
        investigation = Investigation(
            trigger_id=trigger.trigger_id,
            company_symbol=(trigger.company_symbol or "UNKNOWN").upper(),
            company_name=trigger.company_name or "Unknown Company",
        )

        document_text = await self._collect_document_text(trigger)
        historical_context = await self._gather_historical_context(investigation.company_symbol)
        investigation.historical_context = historical_context

        if trigger.company_symbol:
            try:
                investigation.market_data = await self.market_data.get_snapshot(trigger.company_symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Market data retrieval failed; continuing without market snapshot: symbol=%s error=%s",
                    trigger.company_symbol,
                    exc,
                )
                investigation.market_data = None

        web_results, query_input_tokens, query_output_tokens = await self._run_web_search(
            trigger=trigger,
            doc_summary=document_text[:2000],
        )
        investigation.web_search_results = web_results

        deep_result, pipeline_input_tokens, pipeline_output_tokens = await retry_in_thread(
            lambda: run_with_dspy_usage(
                lambda: self._invoke_module(
                    self.pipeline,
                    company_symbol=investigation.company_symbol,
                    company_name=investigation.company_name,
                    document_text=document_text,
                    market_data_json=self._to_json(
                        investigation.market_data.model_dump() if investigation.market_data else {}
                    ),
                    historical_context_json=self._to_json(historical_context.model_dump()),
                    web_search_results_json=self._to_json([item.model_dump() for item in web_results]),
                )
            ),
            attempts=3,
            base_delay_seconds=0.2,
            should_retry=is_transient_error,
        )

        self._apply_pipeline_result(investigation, deep_result)

        investigation.llm_model_used = self.model_name
        investigation.processing_time_seconds = round(time.time() - started_at, 4)
        investigation.total_input_tokens = query_input_tokens + pipeline_input_tokens
        investigation.total_output_tokens = query_output_tokens + pipeline_output_tokens

        await self.investigation_repo.save(investigation)
        logger.info(
            "Deep analysis complete: trigger_id=%s symbol=%s significance=%s duration=%ss model=%s input_tokens=%s output_tokens=%s",
            trigger.trigger_id,
            investigation.company_symbol,
            investigation.significance,
            investigation.processing_time_seconds,
            investigation.llm_model_used,
            investigation.total_input_tokens,
            investigation.total_output_tokens,
        )
        return investigation

    async def _collect_document_text(self, trigger: Any) -> str:
        if not getattr(trigger, "document_ids", None):
            return trigger.raw_content

        texts: list[str] = []
        for document_id in trigger.document_ids:
            doc = await self.doc_repo.get(document_id)
            if doc and getattr(doc, "extracted_text", None):
                texts.append(doc.extracted_text)
        return "\n\n---\n\n".join(texts) if texts else trigger.raw_content

    async def _gather_historical_context(self, company_symbol: str) -> HistoricalContext:
        context = HistoricalContext()
        if not company_symbol or company_symbol == "UNKNOWN":
            return context

        past_investigations = await self.investigation_repo.get_by_company(company_symbol, limit=10)
        context.total_past_investigations = len(past_investigations)
        context.past_investigations = [
            {
                "investigation_id": item.investigation_id,
                "date": item.created_at.isoformat(),
                "significance": item.significance,
                "key_findings": item.key_findings[:3],
            }
            for item in past_investigations
        ]

        inconclusive = await self.investigation_repo.get_past_inconclusive(company_symbol)
        context.past_recommendations = [
            {"investigation_id": item.investigation_id, "was_inconclusive": True}
            for item in inconclusive
        ]

        try:
            similar = await self.vector_repo.search(
                query=company_symbol,
                n_results=5,
                where={"company_symbol": company_symbol},
            )
            context.similar_documents = similar
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector context lookup failed: symbol=%s error=%s", company_symbol, exc)

        return context

    async def _run_web_search(self, trigger: Any, doc_summary: str) -> tuple[list[WebSearchResult], int, int]:
        query_input_tokens = 0
        query_output_tokens = 0
        try:
            query_prediction, query_input_tokens, query_output_tokens = await retry_in_thread(
                lambda: run_with_dspy_usage(
                    lambda: self._invoke_module(
                        self.web_search_module,
                        company_symbol=(trigger.company_symbol or "UNKNOWN").upper(),
                        company_name=trigger.company_name or "Unknown Company",
                        trigger_context=doc_summary,
                    )
                ),
                attempts=3,
                base_delay_seconds=0.2,
                should_retry=is_transient_error,
            )
            queries = self._parse_json_list(getattr(query_prediction, "search_queries_json", "[]"))[:5]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web search query generation failed: trigger_id=%s error=%s", trigger.trigger_id, exc)
            queries = []

        findings: list[WebSearchResult] = []
        for raw_query in queries:
            query = str(raw_query).strip()
            if not query:
                continue
            try:
                rows = await self.web_search.search(query)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Web search execution failed: query=%s error=%s", query, exc)
                continue

            for row in rows:
                title = str(row.get("title", "")).strip()
                url = str(row.get("url", "")).strip()
                snippet = str(row.get("snippet", "")).strip()
                if not title or not url:
                    continue
                findings.append(
                    WebSearchResult(
                        query=query,
                        source=url,
                        title=title,
                        summary=snippet,
                        relevance="medium",
                        sentiment="neutral",
                    )
                )
        return findings, query_input_tokens, query_output_tokens

    def _apply_pipeline_result(self, investigation: Investigation, result: DeepAnalysisResult) -> None:
        investigation.extracted_metrics = self._parse_metrics(result.extracted_metrics_json)
        investigation.forward_statements = self._parse_forward_statements(result.forward_statements_json)
        investigation.management_highlights = [str(item) for item in self._parse_json_list(result.management_highlights_json)]

        investigation.synthesis = result.synthesis
        investigation.key_findings = [str(item) for item in self._parse_json_list(result.key_findings_json)]
        investigation.red_flags = [str(item) for item in self._parse_json_list(result.red_flags_json)]
        investigation.positive_signals = [str(item) for item in self._parse_json_list(result.positive_signals_json)]
        investigation.significance = self._parse_significance(result.significance)
        investigation.significance_reasoning = result.significance_reasoning
        investigation.is_significant = bool(result.is_significant)

        if result.errors:
            investigation.key_findings.extend([f"Pipeline warning: {error}" for error in result.errors])

    def _parse_metrics(self, text: str) -> list[ExtractedMetric]:
        rows = self._parse_json_list(text)
        items: list[ExtractedMetric] = []
        for row in rows:
            if isinstance(row, dict):
                try:
                    items.append(ExtractedMetric.model_validate(row))
                except Exception:  # noqa: BLE001
                    continue
        return items

    def _parse_forward_statements(self, text: str) -> list[ForwardStatement]:
        rows = self._parse_json_list(text)
        items: list[ForwardStatement] = []
        for row in rows:
            if isinstance(row, dict):
                try:
                    items.append(ForwardStatement.model_validate(row))
                except Exception:  # noqa: BLE001
                    continue
        return items

    def _parse_json_list(self, text: str) -> list[Any]:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _parse_significance(self, value: str) -> SignificanceLevel:
        normalized = value.strip().lower()
        try:
            return SignificanceLevel(normalized)
        except Exception:  # noqa: BLE001
            return SignificanceLevel.NOISE

    def _to_json(self, payload: Any) -> str:
        try:
            return json.dumps(payload)
        except Exception:  # noqa: BLE001
            return "{}"

    def _invoke_module(self, module: Any, **kwargs: Any) -> Any:
        if callable(module):
            return module(**kwargs)

        forward = getattr(module, "forward", None)
        if callable(forward):
            return forward(**kwargs)

        raise TypeError(f"Unsupported module type for invocation: {type(module)!r}")
