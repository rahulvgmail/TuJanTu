"""Tests for Layer 4 decision DSPy module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.decision import DecisionModule
from src.models.decision import Recommendation, RecommendationTimeframe


def test_decision_module_returns_typed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    module = DecisionModule()
    monkeypatch.setattr(
        module,
        "evaluator",
        lambda **_: SimpleNamespace(
            should_change=True,
            new_recommendation="buy",
            timeframe="long_term",
            confidence=0.82,
            reasoning="Improved earnings visibility and strong order book.",
            key_factors_json='["Order growth","Margin expansion"]',
        ),
    )

    result = module.forward(
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        current_recommendation=Recommendation.HOLD,
        previous_recommendation_basis="Earlier order delays",
        investigation_summary="Q3 turnaround",
        key_findings_json='["Revenue up"]',
        red_flags_json="[]",
        positive_signals_json='["Execution improving"]',
        past_inconclusive_json='["Past mixed quarter"]',
    )

    assert result.should_change is True
    assert result.new_recommendation == Recommendation.BUY
    assert result.timeframe == RecommendationTimeframe.LONG_TERM
    assert result.confidence == 0.82
    assert result.key_factors == ["Order growth", "Margin expansion"]


def test_decision_module_handles_invalid_fields_with_safe_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    module = DecisionModule()
    monkeypatch.setattr(
        module,
        "evaluator",
        lambda **_: SimpleNamespace(
            should_change=False,
            new_recommendation="unknown",
            timeframe="immediate",
            confidence=5.5,
            reasoning="Insufficient evidence",
            key_factors_json="- weak visibility\n- no catalyst",
        ),
    )

    result = module.forward(
        company_symbol="ABB",
        company_name="ABB India",
        current_recommendation="none",
        previous_recommendation_basis="",
        investigation_summary="No major change",
        key_findings_json="[]",
        red_flags_json="[]",
        positive_signals_json="[]",
        past_inconclusive_json="[]",
    )

    assert result.new_recommendation == Recommendation.NONE
    assert result.timeframe == RecommendationTimeframe.MEDIUM_TERM
    assert result.confidence == 1.0
    assert result.key_factors == ["weak visibility", "no catalyst"]
