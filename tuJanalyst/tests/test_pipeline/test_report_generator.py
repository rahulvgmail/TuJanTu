"""Tests for Layer 5 ReportGenerator orchestration."""

from __future__ import annotations

import json

import pytest

from src.dspy_modules.report import ReportModuleResult
from src.models.decision import DecisionAssessment, Recommendation, RecommendationTimeframe
from src.models.investigation import HistoricalContext, Investigation, WebSearchResult
from src.pipeline.layer5_report.generator import ReportGenerator


class _ReportRepo:
    def __init__(self):
        self.saved = []

    async def save(self, report):
        self.saved.append(report)
        return report.report_id


class _ReportModule:
    def __init__(self, result: ReportModuleResult):
        self.result = result
        self.calls = []

    def forward(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FlakyReportModule:
    def __init__(self, result: ReportModuleResult, failures_before_success: int):
        self.result = result
        self.failures_before_success = failures_before_success
        self.calls = 0

    def forward(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("transient timeout")
        return self.result


def _make_investigation() -> Investigation:
    return Investigation(
        trigger_id="trigger-1",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        synthesis="Order book expanded and execution cadence improved.",
        key_findings=["Revenue up 18% YoY", "Order inflow crossed guidance"],
        red_flags=["Commodity inflation risk"],
        positive_signals=["Margin recovery", "Execution cycle shortened"],
        web_search_results=[
            WebSearchResult(
                query="Inox Wind order book update",
                source="https://example.com/a",
                title="Order update A",
                summary="Details",
                relevance="high",
            ),
            WebSearchResult(
                query="Inox Wind order book update",
                source="https://example.com/a",
                title="Duplicate URL",
                summary="Duplicate",
                relevance="medium",
            ),
            WebSearchResult(
                query="Inox Wind margin update",
                source="https://example.com/b",
                title="Margin update",
                summary="Details",
                relevance="medium",
            ),
        ],
        historical_context=HistoricalContext(
            total_past_investigations=2,
            past_investigations=[
                {
                    "date": "2026-01-15T10:00:00+00:00",
                    "significance": "medium",
                    "key_findings": ["Execution ramp", "Margin stability"],
                }
            ],
        ),
    )


def _make_assessment() -> DecisionAssessment:
    return DecisionAssessment(
        investigation_id="inv-1",
        trigger_id="trigger-1",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        new_recommendation=Recommendation.BUY,
        timeframe=RecommendationTimeframe.MEDIUM_TERM,
        confidence=0.78,
        reasoning="Order visibility and margin trajectory support upside.",
        risks=["Input cost volatility"],
    )


@pytest.mark.asyncio
async def test_report_generator_creates_and_persists_report() -> None:
    repo = _ReportRepo()
    module = _ReportModule(
        ReportModuleResult(
            title="Inox Wind Deep-Dive",
            executive_summary="Momentum has improved with manageable downside risk.",
            report_body_markdown="# Findings\n\nStructured markdown body.",
            recommendation_summary="BUY (Confidence: 78%, Timeframe: medium_term)",
        )
    )
    generator = ReportGenerator(report_repo=repo, report_module=module)  # type: ignore[arg-type]

    report = await generator.generate(_make_investigation(), _make_assessment())

    assert repo.saved
    assert report.title == "Inox Wind Deep-Dive"
    assert report.report_body.startswith("# Findings")
    assert report.recommendation_summary.startswith("BUY")
    assert module.calls
    payload = module.calls[0]
    assert payload["company_symbol"] == "INOXWIND"
    sources = json.loads(payload["sources_json"])
    assert len(sources) == 2
    assert {row["url"] for row in sources} == {"https://example.com/a", "https://example.com/b"}


@pytest.mark.asyncio
async def test_report_generator_falls_back_when_module_output_is_empty() -> None:
    repo = _ReportRepo()
    module = _ReportModule(
        ReportModuleResult(
            title="",
            executive_summary="",
            report_body_markdown="",
            recommendation_summary="",
        )
    )
    generator = ReportGenerator(report_repo=repo, report_module=module)  # type: ignore[arg-type]

    report = await generator.generate(_make_investigation(), _make_assessment())

    assert report.title == "Inox Wind Limited (INOXWIND) Analysis Report"
    assert "BUY" in report.executive_summary
    assert report.recommendation_summary == "BUY (Confidence: 78%, Timeframe: medium_term)"
    assert "## Recommendation" in report.report_body
    assert "## Sources" in report.report_body
    assert "_Decision support only - not an automated trade instruction._" in report.report_body


@pytest.mark.asyncio
async def test_report_generator_retries_transient_generation_failures() -> None:
    repo = _ReportRepo()
    module = _FlakyReportModule(
        ReportModuleResult(
            title="Recovered report",
            executive_summary="Recovered summary",
            report_body_markdown="# Recovered",
            recommendation_summary="BUY (Confidence: 78%, Timeframe: medium_term)",
        ),
        failures_before_success=2,
    )
    generator = ReportGenerator(report_repo=repo, report_module=module)  # type: ignore[arg-type]

    report = await generator.generate(_make_investigation(), _make_assessment())

    assert report.title == "Recovered report"
    assert module.calls == 3
