"""Tests for Layer 4 DecisionAssessor orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.dspy_modules.decision import DecisionModuleResult
from src.models.company import CompanyPosition
from src.models.decision import Recommendation, RecommendationTimeframe
from src.models.investigation import Investigation
from src.pipeline.layer4_decision.assessor import DecisionAssessor


class _AssessmentRepo:
    def __init__(self):
        self.saved = []

    async def save(self, assessment):
        self.saved.append(assessment)
        return assessment.assessment_id


class _InvestigationRepo:
    def __init__(self):
        self.by_company = {}
        self.inconclusive = {}

    async def get_by_company(self, company_symbol: str, limit: int = 20):
        return self.by_company.get(company_symbol, [])[:limit]

    async def get_past_inconclusive(self, company_symbol: str):
        return self.inconclusive.get(company_symbol, [])


class _PositionRepo:
    def __init__(self):
        self.positions = {}
        self.upserts = []

    async def get_position(self, company_symbol: str):
        return self.positions.get(company_symbol)

    async def upsert_position(self, position):
        self.positions[position.company_symbol] = position
        self.upserts.append(position)


class _DecisionModule:
    def __init__(self, result: DecisionModuleResult):
        self.result = result
        self.calls = []

    def forward(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FlakyDecisionModule:
    def __init__(self, result: DecisionModuleResult, failures_before_success: int):
        self.result = result
        self.failures_before_success = failures_before_success
        self.calls = 0

    def forward(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("transient timeout")
        return self.result


def _make_investigation(symbol: str, name: str) -> Investigation:
    return Investigation(
        trigger_id=f"trigger-{symbol.lower()}",
        company_symbol=symbol,
        company_name=name,
        synthesis="Comprehensive analysis",
        key_findings=["Revenue grew", "Order book improved"],
        red_flags=["Raw material volatility"],
        positive_signals=["Margin expansion"],
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_decision_assessor_creates_initial_company_position() -> None:
    assessment_repo = _AssessmentRepo()
    investigation_repo = _InvestigationRepo()
    position_repo = _PositionRepo()
    decision_module = _DecisionModule(
        DecisionModuleResult(
            should_change=True,
            new_recommendation=Recommendation.BUY,
            timeframe=RecommendationTimeframe.MEDIUM_TERM,
            confidence=0.78,
            reasoning="Strong positive momentum.",
            key_factors=["Order growth", "Margin expansion"],
        )
    )
    assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=decision_module,  # type: ignore[arg-type]
    )
    investigation = _make_investigation("INOXWIND", "Inox Wind Limited")

    assessment = await assessor.assess(investigation)

    assert assessment.new_recommendation == Recommendation.BUY.value
    assert assessment.recommendation_changed is True
    assert position_repo.positions["INOXWIND"].current_recommendation == Recommendation.BUY.value
    assert position_repo.positions["INOXWIND"].total_investigations == 1
    assert assessment_repo.saved


@pytest.mark.asyncio
async def test_decision_assessor_keeps_recommendation_when_not_changed() -> None:
    assessment_repo = _AssessmentRepo()
    investigation_repo = _InvestigationRepo()
    position_repo = _PositionRepo()
    position_repo.positions["ABB"] = CompanyPosition(
        company_symbol="ABB",
        company_name="ABB India",
        current_recommendation=Recommendation.BUY,
        recommendation_basis="Existing thesis",
        total_investigations=2,
    )
    decision_module = _DecisionModule(
        DecisionModuleResult(
            should_change=False,
            new_recommendation=Recommendation.BUY,
            timeframe=RecommendationTimeframe.LONG_TERM,
            confidence=0.6,
            reasoning="Thesis remains valid.",
            key_factors=["Stable execution"],
        )
    )
    assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=decision_module,  # type: ignore[arg-type]
    )

    assessment = await assessor.assess(_make_investigation("ABB", "ABB India"))

    assert assessment.recommendation_changed is False
    assert position_repo.positions["ABB"].current_recommendation == Recommendation.BUY.value
    assert position_repo.positions["ABB"].total_investigations == 3
    assert position_repo.positions["ABB"].recommendation_history == []


@pytest.mark.asyncio
async def test_decision_assessor_tracks_history_when_recommendation_changes() -> None:
    assessment_repo = _AssessmentRepo()
    investigation_repo = _InvestigationRepo()
    position_repo = _PositionRepo()
    position_repo.positions["SIEMENS"] = CompanyPosition(
        company_symbol="SIEMENS",
        company_name="Siemens Limited",
        current_recommendation=Recommendation.BUY,
        recommendation_basis="Strong demand",
        recommendation_assessment_id="old-assessment",
        total_investigations=4,
    )
    decision_module = _DecisionModule(
        DecisionModuleResult(
            should_change=True,
            new_recommendation=Recommendation.SELL,
            timeframe=RecommendationTimeframe.SHORT_TERM,
            confidence=0.74,
            reasoning="Adverse evidence outweighs positives.",
            key_factors=["Margin compression", "Order slowdown"],
        )
    )
    assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=decision_module,  # type: ignore[arg-type]
    )

    assessment = await assessor.assess(_make_investigation("SIEMENS", "Siemens Limited"))
    updated = position_repo.positions["SIEMENS"]

    assert assessment.recommendation_changed is True
    assert updated.current_recommendation == Recommendation.SELL.value
    assert len(updated.recommendation_history) == 1
    assert updated.recommendation_history[0]["recommendation"] == Recommendation.BUY.value
    assert updated.total_investigations == 5


@pytest.mark.asyncio
async def test_decision_assessor_passes_past_inconclusive_context_to_module() -> None:
    assessment_repo = _AssessmentRepo()
    investigation_repo = _InvestigationRepo()
    position_repo = _PositionRepo()
    past_item = _make_investigation("BHEL", "BHEL")
    investigation_repo.inconclusive["BHEL"] = [past_item]
    decision_module = _DecisionModule(
        DecisionModuleResult(
            should_change=False,
            new_recommendation=Recommendation.HOLD,
            timeframe=RecommendationTimeframe.MEDIUM_TERM,
            confidence=0.52,
            reasoning="Mixed signals.",
            key_factors=["Insufficient trend clarity"],
        )
    )
    assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=decision_module,  # type: ignore[arg-type]
    )

    assessment = await assessor.assess(_make_investigation("BHEL", "BHEL"))

    assert decision_module.calls
    payload = json.loads(decision_module.calls[0]["past_inconclusive_json"])
    assert payload[0]["investigation_id"] == past_item.investigation_id
    assert assessment.past_inconclusive_resurrected == [past_item.investigation_id]


@pytest.mark.asyncio
async def test_decision_assessor_retries_transient_decision_failures() -> None:
    assessment_repo = _AssessmentRepo()
    investigation_repo = _InvestigationRepo()
    position_repo = _PositionRepo()
    decision_module = _FlakyDecisionModule(
        DecisionModuleResult(
            should_change=True,
            new_recommendation=Recommendation.BUY,
            timeframe=RecommendationTimeframe.MEDIUM_TERM,
            confidence=0.7,
            reasoning="Recovered decision call",
            key_factors=["Resilient demand"],
        ),
        failures_before_success=2,
    )
    assessor = DecisionAssessor(
        assessment_repo=assessment_repo,
        investigation_repo=investigation_repo,
        position_repo=position_repo,
        decision_module=decision_module,  # type: ignore[arg-type]
    )

    assessment = await assessor.assess(_make_investigation("ABB", "ABB India"))

    assert assessment.new_recommendation == Recommendation.BUY.value
    assert decision_module.calls == 3
