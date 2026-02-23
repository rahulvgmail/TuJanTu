"""Layer 4 decision DSPy module."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import dspy

from src.dspy_modules.signatures import DecisionEvaluation
from src.models.decision import Recommendation, RecommendationTimeframe


@dataclass
class DecisionModuleResult:
    """Normalized structured decision output."""

    should_change: bool
    new_recommendation: Recommendation
    timeframe: RecommendationTimeframe
    confidence: float
    reasoning: str
    key_factors: list[str] = field(default_factory=list)


class DecisionModule(dspy.Module):
    """Evaluate recommendation changes with Chain-of-Thought reasoning."""

    def __init__(self):
        super().__init__()
        self.evaluator = dspy.ChainOfThought(DecisionEvaluation)

    def forward(
        self,
        *,
        company_symbol: str,
        company_name: str,
        current_recommendation: Recommendation | str,
        previous_recommendation_basis: str,
        investigation_summary: str,
        key_findings_json: str,
        red_flags_json: str,
        positive_signals_json: str,
        past_inconclusive_json: str,
    ) -> DecisionModuleResult:
        prediction = self.evaluator(
            company_symbol=company_symbol,
            company_name=company_name,
            current_recommendation=self._recommendation_to_str(current_recommendation),
            previous_recommendation_basis=previous_recommendation_basis,
            investigation_summary=investigation_summary,
            key_findings_json=key_findings_json,
            red_flags_json=red_flags_json,
            positive_signals_json=positive_signals_json,
            past_inconclusive_json=past_inconclusive_json,
        )

        return DecisionModuleResult(
            should_change=bool(getattr(prediction, "should_change", False)),
            new_recommendation=self._parse_recommendation(getattr(prediction, "new_recommendation", "none")),
            timeframe=self._parse_timeframe(getattr(prediction, "timeframe", "medium_term")),
            confidence=self._parse_confidence(getattr(prediction, "confidence", 0.0)),
            reasoning=str(getattr(prediction, "reasoning", "")).strip(),
            key_factors=self._parse_key_factors(getattr(prediction, "key_factors_json", "[]")),
        )

    def _recommendation_to_str(self, value: Recommendation | str) -> str:
        if isinstance(value, Recommendation):
            return value.value
        return str(value)

    def _parse_recommendation(self, value: Any) -> Recommendation:
        normalized = str(value).strip().lower()
        try:
            return Recommendation(normalized)
        except Exception:  # noqa: BLE001
            return Recommendation.NONE

    def _parse_timeframe(self, value: Any) -> RecommendationTimeframe:
        normalized = str(value).strip().lower()
        try:
            return RecommendationTimeframe(normalized)
        except Exception:  # noqa: BLE001
            return RecommendationTimeframe.MEDIUM_TERM

    def _parse_confidence(self, value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed < 0:
            return 0.0
        if parsed > 1:
            return 1.0
        return parsed

    def _parse_key_factors(self, value: Any) -> list[str]:
        raw = str(value)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:  # noqa: BLE001
            pass

        line_items = [line.strip("- ").strip() for line in raw.splitlines() if line.strip()]
        if line_items:
            return line_items
        return []
