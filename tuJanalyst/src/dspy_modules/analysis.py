"""Layer 3 DSPy modules and composed deep-analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import dspy

from src.dspy_modules.signatures import (
    InvestigationSynthesis,
    MetricsExtraction,
    WebResultSynthesis,
    WebSearchQueryGeneration,
)


@dataclass
class DeepAnalysisResult:
    """Structured output from the composed Layer 3 DSPy pipeline."""

    extracted_metrics_json: str = "[]"
    forward_statements_json: str = "[]"
    management_highlights_json: str = "[]"
    search_queries_json: str = "[]"
    web_findings_json: str = "[]"

    synthesis: str = ""
    key_findings_json: str = "[]"
    red_flags_json: str = "[]"
    positive_signals_json: str = "[]"
    significance: str = "noise"
    significance_reasoning: str = ""
    is_significant: bool = False

    errors: list[str] = field(default_factory=list)


class MetricsExtractionModule(dspy.Module):
    """Wrap MetricsExtraction with Chain-of-Thought reasoning."""

    def __init__(self):
        super().__init__()
        self.extractor = dspy.ChainOfThought(MetricsExtraction)

    def forward(self, company_symbol: str, company_name: str, document_text: str):
        return self.extractor(
            company_symbol=company_symbol,
            company_name=company_name,
            document_text=document_text,
        )


class WebSearchModule(dspy.Module):
    """Wrap search-query generation with lightweight prediction."""

    def __init__(self):
        super().__init__()
        self.query_generator = dspy.Predict(WebSearchQueryGeneration)

    def forward(self, company_symbol: str, company_name: str, trigger_context: str):
        return self.query_generator(
            company_symbol=company_symbol,
            company_name=company_name,
            trigger_context=trigger_context,
        )


class SynthesisModule(dspy.Module):
    """Wrap final investigation synthesis with Chain-of-Thought reasoning."""

    def __init__(self):
        super().__init__()
        self.synthesizer = dspy.ChainOfThought(InvestigationSynthesis)

    def forward(
        self,
        *,
        company_symbol: str,
        company_name: str,
        extracted_metrics_json: str,
        forward_statements_json: str,
        web_findings_json: str,
        market_data_json: str,
        historical_context_json: str,
    ):
        return self.synthesizer(
            company_symbol=company_symbol,
            company_name=company_name,
            extracted_metrics_json=extracted_metrics_json,
            forward_statements_json=forward_statements_json,
            web_findings_json=web_findings_json,
            market_data_json=market_data_json,
            historical_context_json=historical_context_json,
        )


class DeepAnalysisPipeline(dspy.Module):
    """Compose metrics extraction, search query generation, and synthesis."""

    def __init__(
        self,
        *,
        metrics_module: MetricsExtractionModule | None = None,
        web_search_module: WebSearchModule | None = None,
        synthesis_module: SynthesisModule | None = None,
    ):
        super().__init__()
        self.metrics_module = metrics_module or MetricsExtractionModule()
        self.web_search_module = web_search_module or WebSearchModule()
        self.web_result_synthesizer = dspy.Predict(WebResultSynthesis)
        self.synthesis_module = synthesis_module or SynthesisModule()

    def forward(
        self,
        *,
        company_symbol: str,
        company_name: str,
        document_text: str,
        market_data_json: str = "{}",
        historical_context_json: str = "{}",
        web_search_results_json: str = "[]",
    ) -> DeepAnalysisResult:
        result = DeepAnalysisResult()

        try:
            metrics_prediction = self.metrics_module(
                company_symbol=company_symbol,
                company_name=company_name,
                document_text=document_text,
            )
            result.extracted_metrics_json = str(getattr(metrics_prediction, "extracted_metrics_json", "[]"))
            result.forward_statements_json = str(getattr(metrics_prediction, "forward_statements_json", "[]"))
            result.management_highlights_json = str(getattr(metrics_prediction, "management_highlights_json", "[]"))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"metrics_extraction_failed: {exc}")

        try:
            search_prediction = self.web_search_module(
                company_symbol=company_symbol,
                company_name=company_name,
                trigger_context=document_text[:2000],
            )
            result.search_queries_json = str(getattr(search_prediction, "search_queries_json", "[]"))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"search_query_generation_failed: {exc}")

        try:
            web_prediction = self.web_result_synthesizer(
                company_symbol=company_symbol,
                company_name=company_name,
                web_results_json=web_search_results_json,
            )
            result.web_findings_json = str(getattr(web_prediction, "synthesized_findings_json", "[]"))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"web_result_synthesis_failed: {exc}")
            result.web_findings_json = "[]"

        try:
            synthesis_prediction = self.synthesis_module(
                company_symbol=company_symbol,
                company_name=company_name,
                extracted_metrics_json=result.extracted_metrics_json,
                forward_statements_json=result.forward_statements_json,
                web_findings_json=result.web_findings_json,
                market_data_json=market_data_json,
                historical_context_json=historical_context_json,
            )
            result.synthesis = str(getattr(synthesis_prediction, "synthesis", ""))
            result.key_findings_json = str(getattr(synthesis_prediction, "key_findings_json", "[]"))
            result.red_flags_json = str(getattr(synthesis_prediction, "red_flags_json", "[]"))
            result.positive_signals_json = str(getattr(synthesis_prediction, "positive_signals_json", "[]"))
            result.significance = str(getattr(synthesis_prediction, "significance", "noise"))
            result.significance_reasoning = str(getattr(synthesis_prediction, "significance_reasoning", ""))
            result.is_significant = bool(getattr(synthesis_prediction, "is_significant", False))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"investigation_synthesis_failed: {exc}")

        return result
