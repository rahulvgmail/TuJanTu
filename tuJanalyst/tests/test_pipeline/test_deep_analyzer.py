"""Tests for Layer 3 DeepAnalyzer orchestration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.analysis import DeepAnalysisResult
from src.models.investigation import Investigation, MarketDataSnapshot
from src.models.trigger import TriggerEvent, TriggerSource
from src.pipeline.layer3_analysis.analyzer import DeepAnalyzer


class _InvestigationRepo:
    def __init__(self):
        self.saved: list[Investigation] = []
        self.past_by_symbol: dict[str, list[Investigation]] = {}
        self.inconclusive_by_symbol: dict[str, list[Investigation]] = {}

    async def save(self, investigation: Investigation) -> str:
        self.saved.append(investigation)
        return investigation.investigation_id

    async def get_by_company(self, company_symbol: str, limit: int = 10) -> list[Investigation]:
        return self.past_by_symbol.get(company_symbol, [])[:limit]

    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]:
        return self.inconclusive_by_symbol.get(company_symbol, [])


class _VectorRepo:
    async def search(self, query: str, n_results: int = 5, where: dict | None = None):  # noqa: ARG002
        return [{"id": "doc_chunk_1", "text": "similar content"}]


class _DocRepo:
    def __init__(self, documents: dict[str, SimpleNamespace]):
        self.documents = documents

    async def get(self, document_id: str):
        return self.documents.get(document_id)


class _WebSearchTool:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    async def search(self, query: str):
        if self.should_fail:
            raise RuntimeError("web search unavailable")
        return [{"title": f"Result for {query}", "url": "https://example.test", "snippet": "Context"}]


class _MarketDataTool:
    async def get_snapshot(self, symbol: str):  # noqa: ARG002
        return MarketDataSnapshot(current_price=200.0, market_cap_cr=12000.0)


class _FailingMarketDataTool:
    async def get_snapshot(self, symbol: str):  # noqa: ARG002
        raise RuntimeError("market feed unavailable")


class _WebSearchModule:
    def __call__(self, company_symbol: str = "", company_name: str = "", trigger_context: str = ""):  # noqa: ARG002
        return SimpleNamespace(search_queries_json='["INOXWIND quarterly results", "Inox Wind order book"]')


class _AnalysisPipeline:
    def __init__(self, result: DeepAnalysisResult):
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FlakyAnalysisPipeline:
    def __init__(self, result: DeepAnalysisResult, failures_before_success: int):
        self.result = result
        self.failures_before_success = failures_before_success
        self.calls = 0

    def __call__(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("transient timeout")
        return self.result


@pytest.mark.asyncio
async def test_deep_analyzer_analyze_builds_and_saves_investigation() -> None:
    repo = _InvestigationRepo()
    doc_repo = _DocRepo(
        {
            "doc-1": SimpleNamespace(extracted_text="Revenue grew 20%", source_url="https://example.test/doc1"),
            "doc-2": SimpleNamespace(extracted_text="Order inflow improved", source_url="https://example.test/doc2"),
        }
    )
    pipeline = _AnalysisPipeline(
        DeepAnalysisResult(
            extracted_metrics_json='[{"name":"Revenue","value":"₹1000 Cr","raw_value":"₹1000 Cr"}]',
            forward_statements_json='[{"statement":"Guidance improved"}]',
            management_highlights_json='["Strong execution"]',
            key_findings_json='["Revenue growth"]',
            red_flags_json='["Input cost risk"]',
            positive_signals_json='["Order momentum"]',
            synthesis="Comprehensive synthesis",
            significance="high",
            significance_reasoning="Multiple material positives",
            is_significant=True,
        )
    )
    analyzer = DeepAnalyzer(
        investigation_repo=repo,
        vector_repo=_VectorRepo(),
        doc_repo=doc_repo,
        web_search=_WebSearchTool(),
        market_data=_MarketDataTool(),
        analysis_pipeline=pipeline,  # type: ignore[arg-type]
        web_search_module=_WebSearchModule(),  # type: ignore[arg-type]
        model_name="analysis-test-model",
    )
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="Initial trigger content",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        document_ids=["doc-1", "doc-2"],
    )

    result = await analyzer.analyze(trigger)

    assert result.company_symbol == "INOXWIND"
    assert result.market_data is not None
    assert result.market_data.current_price == 200.0
    assert len(result.extracted_metrics) == 1
    assert result.forward_statements[0].statement == "Guidance improved"
    assert result.is_significant is True
    assert result.llm_model_used == "analysis-test-model"
    assert repo.saved and repo.saved[0].investigation_id == result.investigation_id


@pytest.mark.asyncio
async def test_deep_analyzer_handles_web_search_failures_gracefully() -> None:
    repo = _InvestigationRepo()
    pipeline = _AnalysisPipeline(
        DeepAnalysisResult(
            synthesis="Fallback synthesis",
            significance="low",
            significance_reasoning="Limited evidence",
            is_significant=False,
        )
    )
    analyzer = DeepAnalyzer(
        investigation_repo=repo,
        vector_repo=_VectorRepo(),
        doc_repo=_DocRepo({}),
        web_search=_WebSearchTool(should_fail=True),
        market_data=_MarketDataTool(),
        analysis_pipeline=pipeline,  # type: ignore[arg-type]
        web_search_module=_WebSearchModule(),  # type: ignore[arg-type]
    )
    trigger = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        raw_content="Trigger content",
        company_symbol="ABB",
        company_name="ABB India",
    )

    result = await analyzer.analyze(trigger)

    assert result.web_search_results == []
    assert result.synthesis == "Fallback synthesis"
    assert repo.saved and repo.saved[0].investigation_id == result.investigation_id


@pytest.mark.asyncio
async def test_deep_analyzer_handles_missing_company_symbol_context() -> None:
    repo = _InvestigationRepo()
    pipeline = _AnalysisPipeline(
        DeepAnalysisResult(
            synthesis="No company context",
            significance="noise",
            significance_reasoning="Insufficient signal",
            is_significant=False,
        )
    )
    analyzer = DeepAnalyzer(
        investigation_repo=repo,
        vector_repo=_VectorRepo(),
        doc_repo=_DocRepo({}),
        web_search=_WebSearchTool(),
        market_data=_MarketDataTool(),
        analysis_pipeline=pipeline,  # type: ignore[arg-type]
        web_search_module=_WebSearchModule(),  # type: ignore[arg-type]
    )
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="No symbol trigger",
        company_symbol=None,
        company_name=None,
    )

    result = await analyzer.analyze(trigger)

    assert result.company_symbol == "UNKNOWN"
    assert result.company_name == "Unknown Company"
    assert result.historical_context is not None
    assert result.historical_context.total_past_investigations == 0


@pytest.mark.asyncio
async def test_deep_analyzer_continues_when_market_data_fails() -> None:
    repo = _InvestigationRepo()
    pipeline = _AnalysisPipeline(
        DeepAnalysisResult(
            synthesis="No market data available",
            significance="low",
            significance_reasoning="Market data missing but synthesis still possible",
            is_significant=False,
        )
    )
    analyzer = DeepAnalyzer(
        investigation_repo=repo,
        vector_repo=_VectorRepo(),
        doc_repo=_DocRepo({}),
        web_search=_WebSearchTool(),
        market_data=_FailingMarketDataTool(),
        analysis_pipeline=pipeline,  # type: ignore[arg-type]
        web_search_module=_WebSearchModule(),  # type: ignore[arg-type]
    )
    trigger = TriggerEvent(
        source=TriggerSource.NSE_RSS,
        raw_content="Market-data edge case",
        company_symbol="ABB",
        company_name="ABB India",
    )

    result = await analyzer.analyze(trigger)

    assert result.market_data is None
    assert result.synthesis == "No market data available"
    assert repo.saved and repo.saved[0].investigation_id == result.investigation_id


@pytest.mark.asyncio
async def test_deep_analyzer_retries_transient_pipeline_failures() -> None:
    repo = _InvestigationRepo()
    pipeline = _FlakyAnalysisPipeline(
        DeepAnalysisResult(
            synthesis="Recovered after transient retries",
            significance="medium",
            significance_reasoning="Retry succeeded",
            is_significant=True,
        ),
        failures_before_success=2,
    )
    analyzer = DeepAnalyzer(
        investigation_repo=repo,
        vector_repo=_VectorRepo(),
        doc_repo=_DocRepo({}),
        web_search=_WebSearchTool(),
        market_data=_MarketDataTool(),
        analysis_pipeline=pipeline,  # type: ignore[arg-type]
        web_search_module=_WebSearchModule(),  # type: ignore[arg-type]
    )
    trigger = TriggerEvent(
        source=TriggerSource.BSE_RSS,
        raw_content="Retry case",
        company_symbol="SIEMENS",
        company_name="Siemens Limited",
    )

    result = await analyzer.analyze(trigger)

    assert result.synthesis == "Recovered after transient retries"
    assert pipeline.calls == 3
