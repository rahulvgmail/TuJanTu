"""Layer 5 report-generation orchestrator."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.dspy_modules.report import ReportModule
from src.models.decision import DecisionAssessment
from src.models.investigation import HistoricalContext, Investigation
from src.models.report import AnalysisReport
from src.utils.retry import is_transient_error, retry_in_thread
from src.utils.token_usage import run_with_dspy_usage

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate and persist analysis reports from investigation + assessment data."""

    def __init__(
        self,
        *,
        report_repo: Any,
        report_module: ReportModule | None = None,
        model_name: str = "report-module",
    ):
        self.report_repo = report_repo
        self.report_module = report_module or ReportModule()
        self.model_name = model_name

    async def generate(
        self,
        investigation: Investigation,
        assessment: DecisionAssessment,
    ) -> AnalysisReport:
        """Create and store an AnalysisReport for a completed assessment."""
        sources_payload = self._build_sources_payload(investigation)
        generation_started = time.time()
        module_result, input_tokens, output_tokens = await retry_in_thread(
            lambda: run_with_dspy_usage(
                lambda: self.report_module(
                    company_symbol=investigation.company_symbol,
                    company_name=investigation.company_name,
                    investigation_summary=investigation.synthesis,
                    key_findings_json=self._to_json(investigation.key_findings),
                    red_flags_json=self._to_json(investigation.red_flags),
                    positive_signals_json=self._to_json(investigation.positive_signals),
                    recommendation=self._enum_to_str(assessment.new_recommendation),
                    confidence=float(assessment.confidence),
                    timeframe=self._enum_to_str(assessment.timeframe),
                    reasoning=assessment.reasoning,
                    sources_json=self._to_json(sources_payload),
                )
            ),
            attempts=3,
            base_delay_seconds=0.2,
            should_retry=is_transient_error,
        )

        recommendation_summary = (
            module_result.recommendation_summary
            or self._build_recommendation_summary(
                recommendation=self._enum_to_str(assessment.new_recommendation),
                confidence=float(assessment.confidence),
                timeframe=self._enum_to_str(assessment.timeframe),
            )
        )
        executive_summary = (
            module_result.executive_summary
            or self._build_executive_summary(
                recommendation=self._enum_to_str(assessment.new_recommendation),
                confidence=float(assessment.confidence),
                timeframe=self._enum_to_str(assessment.timeframe),
                reasoning=assessment.reasoning,
            )
        )
        title = module_result.title or f"{investigation.company_name} ({investigation.company_symbol}) Analysis Report"
        report_body = module_result.report_body_markdown or self._build_fallback_report_body(
            investigation=investigation,
            assessment=assessment,
            recommendation_summary=recommendation_summary,
            executive_summary=executive_summary,
            sources=sources_payload,
        )

        report = AnalysisReport(
            assessment_id=assessment.assessment_id,
            investigation_id=investigation.investigation_id,
            trigger_id=investigation.trigger_id,
            company_symbol=investigation.company_symbol,
            company_name=investigation.company_name,
            title=title,
            executive_summary=executive_summary,
            report_body=report_body,
            recommendation_summary=recommendation_summary,
        )
        await self.report_repo.save(report)

        logger.info(
            "Report generated: report_id=%s symbol=%s model=%s latency_seconds=%.4f input_tokens=%s output_tokens=%s",
            report.report_id,
            report.company_symbol,
            self.model_name,
            time.time() - generation_started,
            input_tokens,
            output_tokens,
        )
        return report

    def _build_recommendation_summary(self, *, recommendation: str, confidence: float, timeframe: str) -> str:
        return (
            f"{recommendation.upper()} "
            f"(Confidence: {self._clamp_confidence(confidence) * 100:.0f}%, "
            f"Timeframe: {timeframe})"
        )

    def _build_executive_summary(
        self,
        *,
        recommendation: str,
        confidence: float,
        timeframe: str,
        reasoning: str,
    ) -> str:
        readable_timeframe = timeframe.replace("_", " ")
        short_reasoning = (reasoning or "").strip()
        if len(short_reasoning) > 220:
            short_reasoning = f"{short_reasoning[:217]}..."
        confidence_pct = self._clamp_confidence(confidence) * 100
        return (
            f"Current recommendation is {recommendation.upper()} with {confidence_pct:.0f}% confidence "
            f"for a {readable_timeframe} horizon. "
            f"Primary rationale: {short_reasoning or 'Evidence from the latest trigger and investigation context.'}"
        )

    def _build_fallback_report_body(
        self,
        *,
        investigation: Investigation,
        assessment: DecisionAssessment,
        recommendation_summary: str,
        executive_summary: str,
        sources: list[dict[str, str]],
    ) -> str:
        key_findings = self._format_bullets(investigation.key_findings)
        positive_signals = self._format_bullets(investigation.positive_signals)
        red_flags = self._format_bullets(investigation.red_flags)
        risks = self._format_bullets(assessment.risks or investigation.red_flags)
        sources_block = self._format_sources(sources)
        context = self._format_historical_context(investigation.historical_context)

        return "\n".join(
            [
                f"# {investigation.company_name} ({investigation.company_symbol})",
                "",
                "## Executive Summary",
                executive_summary,
                "",
                "## Trigger",
                investigation.synthesis or "Trigger context unavailable.",
                "",
                "## Findings",
                key_findings,
                "",
                "## Positive Signals",
                positive_signals,
                "",
                "## Context",
                context,
                "",
                "## Recommendation",
                recommendation_summary,
                "",
                "## Risks",
                risks,
                "",
                "## Red Flags",
                red_flags,
                "",
                "## Sources",
                sources_block,
                "",
                "_Decision support only - not an automated trade instruction._",
            ]
        ).strip()

    def _build_sources_payload(self, investigation: Investigation) -> list[dict[str, str]]:
        seen_urls: set[str] = set()
        items: list[dict[str, str]] = []
        for row in investigation.web_search_results:
            url = str(row.source).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                {
                    "title": str(row.title).strip(),
                    "url": url,
                    "query": str(row.query).strip(),
                }
            )
        return items

    def _format_historical_context(self, context: HistoricalContext | None) -> str:
        if context is None or context.total_past_investigations <= 0:
            return "First recorded investigation for this company."

        lines = [f"{context.total_past_investigations} prior investigations available."]
        for row in (context.past_investigations or [])[:3]:
            if not isinstance(row, dict):
                continue
            date = str(row.get("date", "")).strip()
            significance = str(row.get("significance", "")).strip()
            findings = row.get("key_findings", [])
            if not isinstance(findings, list):
                findings = []
            summary = ", ".join(str(item).strip() for item in findings[:2] if str(item).strip())
            detail = f"{date} [{significance}]".strip()
            if summary:
                detail = f"{detail}: {summary}" if detail else summary
            if detail:
                lines.append(f"- {detail}")
        return "\n".join(lines)

    def _format_sources(self, sources: list[dict[str, str]]) -> str:
        if not sources:
            return "- No external sources captured."
        lines: list[str] = []
        for row in sources:
            title = str(row.get("title", "")).strip() or "Source"
            url = str(row.get("url", "")).strip()
            if url:
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {title}")
        return "\n".join(lines)

    def _format_bullets(self, items: list[str]) -> str:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return "- None noted."
        return "\n".join(f"- {item}" for item in cleaned)

    def _to_json(self, payload: Any) -> str:
        try:
            return json.dumps(payload)
        except Exception:  # noqa: BLE001
            return "[]"

    def _enum_to_str(self, value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)

    def _clamp_confidence(self, confidence: float) -> float:
        if confidence < 0:
            return 0.0
        if confidence > 1:
            return 1.0
        return confidence

