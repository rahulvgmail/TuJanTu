"""Layer 5 report-generation DSPy module."""

from __future__ import annotations

import dspy

from src.dspy_modules.signatures import ReportGeneration


class ReportModule(dspy.Module):
    """Generate report sections from investigation + decision context."""

    def __init__(self):
        super().__init__()
        self.generator = dspy.Predict(ReportGeneration)

    def forward(
        self,
        *,
        company_symbol: str,
        company_name: str,
        investigation_summary: str,
        key_findings_json: str,
        red_flags_json: str,
        positive_signals_json: str,
        recommendation: str,
        confidence: float,
        timeframe: str,
        reasoning: str,
        sources_json: str,
    ):
        prediction = self.generator(
            company_symbol=company_symbol,
            company_name=company_name,
            investigation_summary=investigation_summary,
            key_findings_json=key_findings_json,
            red_flags_json=red_flags_json,
            positive_signals_json=positive_signals_json,
            recommendation=recommendation,
            confidence=confidence,
            timeframe=timeframe,
            reasoning=reasoning,
            sources_json=sources_json,
        )
        # Normalize whitespace so downstream `or` fallbacks trigger correctly
        prediction.title = str(getattr(prediction, "title", "") or "").strip()
        prediction.executive_summary = str(getattr(prediction, "executive_summary", "") or "").strip()
        prediction.report_body_markdown = str(getattr(prediction, "report_body_markdown", "") or "").strip()
        prediction.recommendation_summary = str(getattr(prediction, "recommendation_summary", "") or "").strip()
        return prediction
