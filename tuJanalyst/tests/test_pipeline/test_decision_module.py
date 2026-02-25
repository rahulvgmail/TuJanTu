"""Tests for Layer 4 decision DSPy module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.dspy_modules.decision import DecisionModule, parse_decision_result
from src.models.decision import Recommendation, RecommendationTimeframe


def test_decision_module_returns_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
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

    prediction = module(
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

    assert prediction.should_change is True
    assert prediction.new_recommendation == "buy"
    assert prediction.confidence == 0.82

    result = parse_decision_result(prediction)
    assert result.new_recommendation == Recommendation.BUY
    assert result.timeframe == RecommendationTimeframe.LONG_TERM
    assert result.key_factors == ["Order growth", "Margin expansion"]


def test_parse_decision_result_handles_invalid_fields_with_safe_fallbacks() -> None:
    prediction = SimpleNamespace(
        should_change=False,
        new_recommendation="unknown",
        timeframe="immediate",
        confidence=5.5,
        reasoning="Insufficient evidence",
        key_factors_json="- weak visibility\n- no catalyst",
    )

    result = parse_decision_result(prediction)

    assert result.new_recommendation == Recommendation.NONE
    assert result.timeframe == RecommendationTimeframe.MEDIUM_TERM
    assert result.confidence == 1.0
    assert result.key_factors == ["weak visibility", "no catalyst"]
