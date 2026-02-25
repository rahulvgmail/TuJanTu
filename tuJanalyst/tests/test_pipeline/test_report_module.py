"""Tests for Layer 5 report-generation DSPy module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.report import ReportModule


def test_report_module_returns_structured_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ReportModule()
    monkeypatch.setattr(
        module,
        "generator",
        lambda **_: SimpleNamespace(
            title="Inox Wind Deep-Dive",
            executive_summary="Revenue and order momentum improved with manageable risk.",
            report_body_markdown="# Findings\n\nDetailed markdown body.",
            recommendation_summary="BUY (Confidence: 78%, Timeframe: medium_term)",
        ),
    )

    result = module(
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        investigation_summary="Layer 3 synthesis",
        key_findings_json='["Revenue up"]',
        red_flags_json='["Commodity volatility"]',
        positive_signals_json='["Order book growth"]',
        recommendation="buy",
        confidence=0.78,
        timeframe="medium_term",
        reasoning="Strong risk/reward profile",
        sources_json='["https://example.test/report"]',
    )

    assert result.title == "Inox Wind Deep-Dive"
    assert "Revenue and order momentum" in result.executive_summary
    assert result.report_body_markdown.startswith("# Findings")
    assert result.recommendation_summary.startswith("BUY")
