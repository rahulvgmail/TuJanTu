"""DSPy signatures and modules."""

from src.dspy_modules.analysis import (
    DeepAnalysisPipeline,
    DeepAnalysisResult,
    MetricsExtractionModule,
    SynthesisModule,
    WebSearchModule,
)
from src.dspy_modules.decision import DecisionModule, DecisionModuleResult
from src.dspy_modules.gate import GateDecision, GateModule, build_dspy_model_identifier, configure_dspy_lm
from src.dspy_modules.report import ReportModule, ReportModuleResult
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
    "DecisionModuleResult",
    "GateClassification",
    "InvestigationSynthesis",
    "MetricsExtractionModule",
    "ReportGeneration",
    "ReportModule",
    "ReportModuleResult",
    "MetricsExtraction",
    "SynthesisModule",
    "WebResultSynthesis",
    "WebSearchModule",
    "WebSearchQueryGeneration",
    "GateDecision",
    "GateModule",
    "build_dspy_model_identifier",
    "configure_dspy_lm",
]
