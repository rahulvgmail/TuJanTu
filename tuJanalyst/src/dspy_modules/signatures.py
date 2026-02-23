"""DSPy signatures used across Layer 2+ reasoning modules."""

from __future__ import annotations

import dspy


class GateClassification(dspy.Signature):
    """Classify whether an announcement is worth deeper investment analysis."""

    announcement_text: str = dspy.InputField(desc="Corporate announcement text")
    company_name: str = dspy.InputField(desc="Company name")
    sector: str = dspy.InputField(desc="Company sector")

    is_worth_investigating: bool = dspy.OutputField(desc="True if this should go to Layer 3")
    reason: str = dspy.OutputField(desc="Short reason for pass/reject decision")


class MetricsExtraction(dspy.Signature):
    """
    Extract structured financial and management signals from corporate text.

    Instructions:
    - Parse the provided text for concrete metrics (revenue, EBITDA, order book, capacity, margins, debt, guidance).
    - Prefer explicit values + periods (e.g., "Q3 FY26 Revenue ₹1,200 Cr, +18% YoY").
    - Capture forward-looking statements with targets/timelines when present.
    - Produce concise management highlights.
    - Be conservative: if a metric is ambiguous, omit it instead of guessing.

    Output format requirements:
    - `extracted_metrics_json` must be a JSON array of objects.
    - `forward_statements_json` must be a JSON array of objects.
    - `management_highlights_json` must be a JSON array of short strings.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    document_text: str = dspy.InputField(desc="Announcement/document text content")

    extracted_metrics_json: str = dspy.OutputField(desc="JSON array of extracted metrics")
    forward_statements_json: str = dspy.OutputField(desc="JSON array of forward-looking statements")
    management_highlights_json: str = dspy.OutputField(desc="JSON array of management highlights")


class WebSearchQueryGeneration(dspy.Signature):
    """
    Generate targeted web-search queries for validating and enriching an investigation.

    Instructions:
    - Generate 3-5 high-signal queries focused on company-specific developments.
    - Include recent-period context (quarter, year, order/update specifics) when possible.
    - Prioritize queries likely to return primary reporting (exchange filings, reputable business media).

    Output format requirements:
    - `search_queries_json` must be a JSON array of query strings.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    trigger_context: str = dspy.InputField(desc="Short context from trigger/doc analysis")

    search_queries_json: str = dspy.OutputField(desc="JSON array of 3-5 search query strings")


class WebResultSynthesis(dspy.Signature):
    """
    Synthesize raw web-search findings into relevance-ranked investigative context.

    Instructions:
    - Summarize each material finding in plain, factual language.
    - Label relevance/severity to the ongoing investigation.
    - Prefer numeric details and source-backed statements when available.
    - Omit repetitive/low-quality duplicates.

    Output format requirements:
    - `synthesized_findings_json` must be a JSON array of finding objects.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    web_results_json: str = dspy.InputField(desc="JSON array of raw web results")

    synthesized_findings_json: str = dspy.OutputField(desc="JSON array of synthesized web findings")


class InvestigationSynthesis(dspy.Signature):
    """
    Produce the final Layer 3 synthesis from metrics, statements, web findings, and context.

    Instructions:
    - Provide a coherent narrative with concrete supporting evidence.
    - Reference specific numbers/periods wherever available; avoid generic prose.
    - Distill key findings, risks/red flags, and positive signals.
    - Assign significance as one of: high, medium, low, noise.
    - Set `is_significant` true only if evidence suggests material impact potential.

    Output format requirements:
    - `key_findings_json`, `red_flags_json`, and `positive_signals_json` must be JSON arrays of strings.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    extracted_metrics_json: str = dspy.InputField(desc="JSON array of extracted metrics")
    forward_statements_json: str = dspy.InputField(desc="JSON array of forward statements")
    web_findings_json: str = dspy.InputField(desc="JSON array of synthesized web findings")
    market_data_json: str = dspy.InputField(desc="JSON object for market snapshot")
    historical_context_json: str = dspy.InputField(desc="JSON object for historical context")

    synthesis: str = dspy.OutputField(desc="Narrative synthesis")
    key_findings_json: str = dspy.OutputField(desc="JSON array of key findings")
    red_flags_json: str = dspy.OutputField(desc="JSON array of red flags")
    positive_signals_json: str = dspy.OutputField(desc="JSON array of positive signals")
    significance: str = dspy.OutputField(desc="One of: high, medium, low, noise")
    significance_reasoning: str = dspy.OutputField(desc="Reasoning for significance classification")
    is_significant: bool = dspy.OutputField(desc="True if this should proceed to Layer 4")


class DecisionEvaluation(dspy.Signature):
    """
    Evaluate whether the current recommendation should change based on new evidence.

    Instructions:
    - Consider current recommendation, new investigation evidence, and historical context.
    - Explicitly account for past inconclusive investigations in final reasoning.
    - Choose recommendation from: buy, sell, hold, none.
    - Choose timeframe from: short_term, medium_term, long_term.
    - Keep confidence calibrated; avoid unjustified extreme values.
    - Keep reasoning decision-first and evidence-backed:
      1) state verdict,
      2) cite strongest positive signals,
      3) cite strongest opposing/risk signals,
      4) conclude with net-balance justification.
    - If `should_change` is false, keep recommendation aligned with current stance.
    - Avoid vague language without concrete support.

    Output format requirements:
    - `key_factors_json` must be a JSON array of 3-6 concise factor strings.
    - Factors should be specific and attributable to investigation evidence.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    current_recommendation: str = dspy.InputField(desc="Current recommendation state")
    previous_recommendation_basis: str = dspy.InputField(desc="Prior recommendation basis summary")
    investigation_summary: str = dspy.InputField(desc="Latest investigation synthesis summary")
    key_findings_json: str = dspy.InputField(desc="JSON array of key findings")
    red_flags_json: str = dspy.InputField(desc="JSON array of red flags")
    positive_signals_json: str = dspy.InputField(desc="JSON array of positive signals")
    past_inconclusive_json: str = dspy.InputField(desc="JSON array of past inconclusive investigation summaries")

    should_change: bool = dspy.OutputField(desc="True if recommendation should be changed")
    new_recommendation: str = dspy.OutputField(desc="One of: buy, sell, hold, none")
    timeframe: str = dspy.OutputField(desc="One of: short_term, medium_term, long_term")
    confidence: float = dspy.OutputField(desc="Confidence score between 0 and 1")
    reasoning: str = dspy.OutputField(desc="Detailed reasoning for recommendation decision")
    key_factors_json: str = dspy.OutputField(desc="JSON array of key decision factors")


class ReportGeneration(dspy.Signature):
    """
    Generate a structured markdown report from investigation and decision context.

    Instructions:
    - Produce a concise executive summary (2-3 actionable sentences).
    - Include concrete evidence, numbers, and source references in the report body.
    - Clearly present recommendation, confidence, timeframe, and key risks.
    - Keep tone analytical and decision-support oriented.
    - Use scannable markdown with short sections and bullet points for findings/risks.
    - Keep recommendation highly visible near the top for quick operator scanning.
    - Preferred report-body structure:
      - `## Trigger`
      - `## Findings`
      - `## Context`
      - `## Recommendation`
      - `## Risks`
      - `## Sources`
    - Include the disclaimer that this is decision support, not trade execution advice.
    """

    company_symbol: str = dspy.InputField(desc="Company symbol")
    company_name: str = dspy.InputField(desc="Company name")
    investigation_summary: str = dspy.InputField(desc="Layer 3 synthesis narrative")
    key_findings_json: str = dspy.InputField(desc="JSON array of key findings")
    red_flags_json: str = dspy.InputField(desc="JSON array of red flags")
    positive_signals_json: str = dspy.InputField(desc="JSON array of positive signals")
    recommendation: str = dspy.InputField(desc="Decision recommendation")
    confidence: float = dspy.InputField(desc="Decision confidence between 0 and 1")
    timeframe: str = dspy.InputField(desc="Recommendation timeframe")
    reasoning: str = dspy.InputField(desc="Decision reasoning text")
    sources_json: str = dspy.InputField(desc="JSON array of source links/titles")

    title: str = dspy.OutputField(desc="Report title")
    executive_summary: str = dspy.OutputField(desc="2-3 sentence executive summary")
    report_body_markdown: str = dspy.OutputField(desc="Full markdown report body")
    recommendation_summary: str = dspy.OutputField(desc="Single-line recommendation summary")
