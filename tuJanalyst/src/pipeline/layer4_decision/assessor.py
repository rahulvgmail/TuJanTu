"""Layer 4 decision-assessment orchestrator."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.dspy_modules.decision import DecisionModule, ParsedDecisionResult, parse_decision_result
from src.models.company import CompanyPosition
from src.models.decision import DecisionAssessment, Recommendation
from src.utils.retry import is_transient_error, retry_in_thread
from src.utils.token_usage import run_with_dspy_usage

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


class DecisionAssessor:
    """Orchestrate Layer 4 recommendation assessment and position updates."""

    def __init__(
        self,
        *,
        assessment_repo: Any,
        investigation_repo: Any,
        position_repo: Any,
        decision_module: DecisionModule | None = None,
        model_name: str = "decision-module",
    ):
        self.assessment_repo = assessment_repo
        self.investigation_repo = investigation_repo
        self.position_repo = position_repo
        self.decision_module = decision_module or DecisionModule()
        self.model_name = model_name

    async def assess(self, investigation: Any) -> DecisionAssessment:
        """Create DecisionAssessment and update company position when needed."""
        started = time.time()
        symbol = investigation.company_symbol
        name = investigation.company_name

        existing_position = await self.position_repo.get_position(symbol)
        past_investigations = await self.investigation_repo.get_by_company(symbol, limit=20)
        past_inconclusive = await self.investigation_repo.get_past_inconclusive(symbol)

        decision_started = time.time()
        prediction, input_tokens, output_tokens = await retry_in_thread(
            lambda: run_with_dspy_usage(
                lambda: self.decision_module(
                    company_symbol=symbol,
                    company_name=name,
                    current_recommendation=(
                        existing_position.current_recommendation
                        if existing_position is not None
                        else Recommendation.NONE
                    ),
                    previous_recommendation_basis=(existing_position.recommendation_basis if existing_position else ""),
                    investigation_summary=investigation.synthesis,
                    key_findings_json=json.dumps(investigation.key_findings),
                    red_flags_json=json.dumps(investigation.red_flags),
                    positive_signals_json=json.dumps(investigation.positive_signals),
                    past_inconclusive_json=json.dumps(
                        [
                            {
                                "investigation_id": item.investigation_id,
                                "created_at": item.created_at.isoformat(),
                                "significance": item.significance,
                                "summary": item.synthesis[:400],
                            }
                            for item in past_inconclusive
                        ]
                    ),
                )
            ),
            attempts=3,
            base_delay_seconds=0.2,
            should_retry=is_transient_error,
        )
        logger.info(
            "Decision LLM call complete: symbol=%s model=%s latency_seconds=%.4f input_tokens=%s output_tokens=%s",
            symbol,
            self.model_name,
            time.time() - decision_started,
            input_tokens,
            output_tokens,
        )

        decision = parse_decision_result(prediction)

        assessment = self._build_assessment(
            investigation=investigation,
            existing_position=existing_position,
            past_investigations=past_investigations,
            past_inconclusive=past_inconclusive,
            decision=decision,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            processing_time=time.time() - started,
        )
        await self.assessment_repo.save(assessment)

        updated_position = self._derive_position(existing_position, investigation, assessment)
        if updated_position is not None:
            await self.position_repo.upsert_position(updated_position)

        return assessment

    def _build_assessment(
        self,
        *,
        investigation: Any,
        existing_position: CompanyPosition | None,
        past_investigations: list[Any],
        past_inconclusive: list[Any],
        decision: ParsedDecisionResult,
        input_tokens: int,
        output_tokens: int,
        processing_time: float,
    ) -> DecisionAssessment:
        previous_recommendation = (
            Recommendation(existing_position.current_recommendation)
            if existing_position is not None
            else Recommendation.NONE
        )
        recommendation_changed = bool(decision.should_change) and decision.new_recommendation != previous_recommendation

        return DecisionAssessment(
            investigation_id=investigation.investigation_id,
            trigger_id=investigation.trigger_id,
            company_symbol=investigation.company_symbol,
            company_name=investigation.company_name,
            previous_recommendation=previous_recommendation,
            previous_recommendation_date=(
                existing_position.recommendation_date if existing_position is not None else None
            ),
            previous_recommendation_basis=(
                existing_position.recommendation_basis if existing_position is not None else ""
            ),
            recommendation_changed=recommendation_changed,
            new_recommendation=decision.new_recommendation,
            timeframe=decision.timeframe,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            key_factors_for=decision.key_factors,
            key_factors_against=list(investigation.red_flags),
            risks=list(investigation.red_flags),
            past_investigations_used=[item.investigation_id for item in past_investigations],
            past_inconclusive_resurrected=[item.investigation_id for item in past_inconclusive],
            llm_model_used=self.model_name,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            processing_time_seconds=round(processing_time, 4),
        )

    def _derive_position(
        self,
        existing_position: CompanyPosition | None,
        investigation: Any,
        assessment: DecisionAssessment,
    ) -> CompanyPosition | None:
        now = utc_now()
        if existing_position is None:
            return CompanyPosition(
                company_symbol=investigation.company_symbol,
                company_name=investigation.company_name,
                current_recommendation=assessment.new_recommendation,
                recommendation_date=now,
                recommendation_basis=assessment.reasoning[:1000],
                recommendation_assessment_id=assessment.assessment_id,
                recommendation_history=[],
                total_investigations=1,
                last_investigation_date=investigation.created_at,
            )

        position = CompanyPosition.model_validate(existing_position.model_dump())
        position.total_investigations += 1
        position.last_investigation_date = investigation.created_at

        if assessment.recommendation_changed:
            position.recommendation_history.append(
                {
                    "recommendation": position.current_recommendation,
                    "date": position.recommendation_date.isoformat() if position.recommendation_date else None,
                    "assessment_id": position.recommendation_assessment_id,
                }
            )
            position.current_recommendation = assessment.new_recommendation
            position.recommendation_date = now
            position.recommendation_basis = assessment.reasoning[:1000]
            position.recommendation_assessment_id = assessment.assessment_id
        else:
            position.recommendation_basis = assessment.reasoning[:1000]

        position.updated_at = now
        return position

