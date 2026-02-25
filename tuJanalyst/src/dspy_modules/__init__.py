"""DSPy signatures and modules."""

from src.dspy_modules.analysis import (
    DeepAnalysisPipeline,
    DeepAnalysisResult,
    MetricsExtractionModule,
    SynthesisModule,
    WebSearchModule,
)
from src.dspy_modules.decision import DecisionModule, ParsedDecisionResult, parse_decision_result
from src.dspy_modules.gate import GateModule, build_dspy_model_identifier, configure_dspy_lm
from src.dspy_modules.report import ReportModule
from src.dspy_modules.signatures import (
    DecisionEvaluation,
    GateClassification,
    InvestigationSynthesis,
    MetricsExtraction,
    ReportGeneration,
    WebResultSynthesis,
    WebSearchQueryGeneration,
)

__all__ = [
    "DeepAnalysisPipeline",
    "DeepAnalysisResult",
    "DecisionEvaluation",
    "DecisionModule",
    "ParsedDecisionResult",
    "parse_decision_result",
    "GateClassification",
    "InvestigationSynthesis",
    "MetricsExtractionModule",
    "ReportGeneration",
    "ReportModule",
    "MetricsExtraction",
    "SynthesisModule",
    "WebResultSynthesis",
    "WebSearchModule",
    "WebSearchQueryGeneration",
    "GateModule",
    "build_dspy_model_identifier",
    "configure_dspy_lm",
]
