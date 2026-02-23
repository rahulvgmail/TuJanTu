"""Tests for Layer 3 DSPy analysis modules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.analysis import (
    DeepAnalysisPipeline,
    MetricsExtractionModule,
    SynthesisModule,
    WebSearchModule,
)


def test_metrics_extraction_module_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    module = MetricsExtractionModule()
    monkeypatch.setattr(
        module,
        "extractor",
        lambda **_: SimpleNamespace(
            extracted_metrics_json='[{"name":"Revenue"}]',
            forward_statements_json='[{"statement":"Guidance raised"}]',
            management_highlights_json='["Strong execution"]',
        ),
    )

    result = module.forward(company_symbol="INOXWIND", company_name="Inox Wind", document_text="Quarterly results")

    assert "Revenue" in result.extracted_metrics_json
    assert "Guidance" in result.forward_statements_json


def test_web_search_module_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    module = WebSearchModule()
    monkeypatch.setattr(
        module,
        "query_generator",
        lambda **_: SimpleNamespace(search_queries_json='["INOXWIND Q3 FY26 results"]'),
    )

    result = module.forward(company_symbol="INOXWIND", company_name="Inox Wind", trigger_context="Q3 update")

    assert "INOXWIND" in result.search_queries_json


def test_synthesis_module_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SynthesisModule()
    monkeypatch.setattr(
        module,
        "synthesizer",
        lambda **_: SimpleNamespace(
            synthesis="Company posted strong growth.",
            key_findings_json='["Revenue up"]',
            red_flags_json="[]",
            positive_signals_json='["Order momentum"]',
            significance="high",
            significance_reasoning="Multiple material metrics improved",
            is_significant=True,
        ),
    )

    result = module.forward(
        company_symbol="INOXWIND",
        company_name="Inox Wind",
        extracted_metrics_json="[]",
        forward_statements_json="[]",
        web_findings_json="[]",
        market_data_json="{}",
        historical_context_json="{}",
    )

    assert result.significance == "high"
    assert result.is_significant is True


def test_deep_analysis_pipeline_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeMetrics:
        def forward(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                extracted_metrics_json='[{"name":"Revenue"}]',
                forward_statements_json='[{"statement":"Expansion"}]',
                management_highlights_json='["Execution strong"]',
            )

    class _FakeSearch:
        def forward(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(search_queries_json='["INOXWIND order book update"]')

    class _FakeSynthesis:
        def forward(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                synthesis="Synthesis text",
                key_findings_json='["Finding"]',
                red_flags_json='["Risk"]',
                positive_signals_json='["Signal"]',
                significance="medium",
                significance_reasoning="Mixed but notable signals",
                is_significant=True,
            )

    pipeline = DeepAnalysisPipeline(
        metrics_module=_FakeMetrics(),  # type: ignore[arg-type]
        web_search_module=_FakeSearch(),  # type: ignore[arg-type]
        synthesis_module=_FakeSynthesis(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        pipeline,
        "web_result_synthesizer",
        lambda **_: SimpleNamespace(synthesized_findings_json='[{"summary":"Useful web signal"}]'),
    )

    result = pipeline.forward(
        company_symbol="INOXWIND",
        company_name="Inox Wind",
        document_text="Quarterly results with order update",
        market_data_json="{}",
        historical_context_json="{}",
        web_search_results_json='[{"title":"news"}]',
    )

    assert result.synthesis == "Synthesis text"
    assert result.web_findings_json.startswith("[")
    assert result.is_significant is True
    assert result.errors == []


def test_deep_analysis_pipeline_handles_web_failure_but_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeMetrics:
        def forward(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                extracted_metrics_json="[]",
                forward_statements_json="[]",
                management_highlights_json="[]",
            )

    class _FakeSearch:
        def forward(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(search_queries_json='["query"]')

    class _FakeSynthesis:
        def __init__(self):
            self.last_kwargs = None

        def forward(self, **kwargs):
            self.last_kwargs = kwargs
            return SimpleNamespace(
                synthesis="Fallback synthesis",
                key_findings_json="[]",
                red_flags_json="[]",
                positive_signals_json="[]",
                significance="low",
                significance_reasoning="No strong signals",
                is_significant=False,
            )

    synthesis_module = _FakeSynthesis()
    pipeline = DeepAnalysisPipeline(
        metrics_module=_FakeMetrics(),  # type: ignore[arg-type]
        web_search_module=_FakeSearch(),  # type: ignore[arg-type]
        synthesis_module=synthesis_module,  # type: ignore[arg-type]
    )

    def _raise_web_failure(**kwargs):  # noqa: ARG001
        raise RuntimeError("search backend unavailable")

    monkeypatch.setattr(pipeline, "web_result_synthesizer", _raise_web_failure)

    result = pipeline.forward(
        company_symbol="ABB",
        company_name="ABB India",
        document_text="Routine disclosure",
        web_search_results_json="[]",
    )

    assert any("web_result_synthesis_failed" in item for item in result.errors)
    assert result.synthesis == "Fallback synthesis"
    assert synthesis_module.last_kwargs is not None
    assert synthesis_module.last_kwargs["web_findings_json"] == "[]"
