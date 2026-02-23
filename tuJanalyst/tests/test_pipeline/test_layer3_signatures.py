"""Tests for Layer 3 DSPy signature definitions."""

from __future__ import annotations

import dspy

from src.dspy_modules import (
    DecisionEvaluation,
    InvestigationSynthesis,
    MetricsExtraction,
    ReportGeneration,
    WebResultSynthesis,
    WebSearchQueryGeneration,
)


def test_metrics_extraction_signature_fields() -> None:
    assert issubclass(MetricsExtraction, dspy.Signature)
    assert set(MetricsExtraction.input_fields.keys()) == {"company_symbol", "company_name", "document_text"}
    assert set(MetricsExtraction.output_fields.keys()) == {
        "extracted_metrics_json",
        "forward_statements_json",
        "management_highlights_json",
    }
    assert MetricsExtraction.output_fields["extracted_metrics_json"].annotation is str
    assert MetricsExtraction.output_fields["forward_statements_json"].annotation is str
    assert MetricsExtraction.output_fields["management_highlights_json"].annotation is str
    dspy.Predict(MetricsExtraction)


def test_web_search_query_generation_signature_fields() -> None:
    assert issubclass(WebSearchQueryGeneration, dspy.Signature)
    assert set(WebSearchQueryGeneration.output_fields.keys()) == {"search_queries_json"}
    assert WebSearchQueryGeneration.output_fields["search_queries_json"].annotation is str
    dspy.Predict(WebSearchQueryGeneration)


def test_web_result_synthesis_signature_fields() -> None:
    assert issubclass(WebResultSynthesis, dspy.Signature)
    assert set(WebResultSynthesis.output_fields.keys()) == {"synthesized_findings_json"}
    assert WebResultSynthesis.output_fields["synthesized_findings_json"].annotation is str
    dspy.Predict(WebResultSynthesis)


def test_investigation_synthesis_signature_fields() -> None:
    assert issubclass(InvestigationSynthesis, dspy.Signature)
    expected_outputs = {
        "synthesis",
        "key_findings_json",
        "red_flags_json",
        "positive_signals_json",
        "significance",
        "significance_reasoning",
        "is_significant",
    }
    assert set(InvestigationSynthesis.output_fields.keys()) == expected_outputs
    assert InvestigationSynthesis.output_fields["key_findings_json"].annotation is str
    assert InvestigationSynthesis.output_fields["red_flags_json"].annotation is str
    assert InvestigationSynthesis.output_fields["positive_signals_json"].annotation is str
    assert InvestigationSynthesis.output_fields["is_significant"].annotation is bool
    dspy.ChainOfThought(InvestigationSynthesis)


def test_decision_evaluation_signature_fields() -> None:
    assert issubclass(DecisionEvaluation, dspy.Signature)
    expected_outputs = {
        "should_change",
        "new_recommendation",
        "timeframe",
        "confidence",
        "reasoning",
        "key_factors_json",
    }
    assert set(DecisionEvaluation.output_fields.keys()) == expected_outputs
    assert DecisionEvaluation.output_fields["should_change"].annotation is bool
    assert DecisionEvaluation.output_fields["key_factors_json"].annotation is str
    dspy.ChainOfThought(DecisionEvaluation)


def test_report_generation_signature_fields() -> None:
    assert issubclass(ReportGeneration, dspy.Signature)
    expected_outputs = {
        "title",
        "executive_summary",
        "report_body_markdown",
        "recommendation_summary",
    }
    assert set(ReportGeneration.output_fields.keys()) == expected_outputs
    assert ReportGeneration.output_fields["title"].annotation is str
    assert ReportGeneration.output_fields["executive_summary"].annotation is str
    assert ReportGeneration.output_fields["report_body_markdown"].annotation is str
    dspy.Predict(ReportGeneration)


def test_decision_evaluation_signature_prompt_includes_decision_first_guidance() -> None:
    doc = DecisionEvaluation.__doc__ or ""
    assert "state verdict" in doc
    assert "net-balance justification" in doc


def test_report_generation_signature_prompt_includes_scannable_structure_guidance() -> None:
    doc = ReportGeneration.__doc__ or ""
    assert "scannable markdown" in doc
    assert "`## Trigger`" in doc
    assert "`## Recommendation`" in doc
