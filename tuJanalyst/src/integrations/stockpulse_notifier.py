"""Pushes tuJanalyst analysis results back to StockPulse as notes and color updates."""

from __future__ import annotations

import logging

from src.agents.tools.stockpulse_client import StockPulseClient
from src.models.decision import DecisionAssessment
from src.models.investigation import Investigation

logger = logging.getLogger(__name__)


class StockPulseNotifier:
    """Pushes tuJanalyst results back to StockPulse as notes, events, and color updates."""

    def __init__(self, client: StockPulseClient):
        self.client = client

    async def post_investigation_note(self, investigation: Investigation) -> bool:
        """Format and post investigation findings as a StockPulse note.

        Returns True on success, False on failure.
        """
        try:
            significance = investigation.significance
            if isinstance(significance, str):
                significance_label = significance.upper()
            else:
                significance_label = significance.value.upper()

            lines: list[str] = [f"[AI Investigation - {significance_label} significance]"]

            if investigation.key_findings:
                lines.append("Key Findings:")
                for finding in investigation.key_findings:
                    lines.append(f"\u2022 {finding}")

            if investigation.red_flags:
                lines.append("Red Flags:")
                for flag in investigation.red_flags:
                    lines.append(f"\u2022 {flag}")

            if investigation.positive_signals:
                lines.append("Positive Signals:")
                for signal in investigation.positive_signals:
                    lines.append(f"\u2022 {signal}")

            content = "\n".join(lines)
            result = await self.client.post_note(
                investigation.company_symbol, content, "agent"
            )

            if result is not None:
                logger.info(
                    "Posted investigation note for %s (investigation_id=%s)",
                    investigation.company_symbol,
                    investigation.investigation_id,
                )
                return True

            logger.warning(
                "Failed to post investigation note for %s (investigation_id=%s)",
                investigation.company_symbol,
                investigation.investigation_id,
            )
            return False
        except Exception:
            logger.exception(
                "Error posting investigation note for %s",
                investigation.company_symbol,
            )
            return False

    async def post_recommendation_event(self, assessment: DecisionAssessment) -> bool:
        """Post a recommendation as a structured note to StockPulse.

        Returns True on success, False on failure.
        """
        try:
            recommendation = assessment.new_recommendation
            if isinstance(recommendation, str):
                recommendation_label = recommendation.upper()
            else:
                recommendation_label = recommendation.value.upper()

            timeframe = assessment.timeframe
            if isinstance(timeframe, str):
                timeframe_label = timeframe
            else:
                timeframe_label = timeframe.value

            confidence_pct = int(assessment.confidence * 100)

            lines: list[str] = [
                f"[AI Recommendation: {recommendation_label}"
                f" \u2192 Confidence: {confidence_pct}%"
                f" \u2192 Timeframe: {timeframe_label}]",
            ]

            if assessment.reasoning:
                lines.append(f"Reasoning: {assessment.reasoning}")

            if assessment.key_factors_for:
                lines.append(f"Key Factors: {', '.join(assessment.key_factors_for)}")

            if assessment.risks:
                lines.append(f"Risks: {', '.join(assessment.risks)}")

            content = "\n".join(lines)
            result = await self.client.post_note(
                assessment.company_symbol, content, "agent"
            )

            if result is not None:
                logger.info(
                    "Posted recommendation event for %s (assessment_id=%s, recommendation=%s)",
                    assessment.company_symbol,
                    assessment.assessment_id,
                    recommendation_label,
                )
                return True

            logger.warning(
                "Failed to post recommendation event for %s (assessment_id=%s)",
                assessment.company_symbol,
                assessment.assessment_id,
            )
            return False
        except Exception:
            logger.exception(
                "Error posting recommendation event for %s",
                assessment.company_symbol,
            )
            return False

    async def update_color_from_assessment(
        self,
        assessment: DecisionAssessment,
        investigation: Investigation,
    ) -> bool:
        """Update the stock color in StockPulse based on investigation signals.

        Maps clear positive results to Blue and clear negative results to Red.
        Skips inconclusive investigations (returns False without making an API call).

        Returns True if color was updated, False if skipped or failed.
        """
        try:
            significance = investigation.significance
            if isinstance(significance, str):
                is_high = significance == "high"
            else:
                is_high = significance.value == "high"

            if not is_high:
                logger.debug(
                    "Skipping color update for %s: significance is not high",
                    investigation.company_symbol,
                )
                return False

            positive_count = len(investigation.positive_signals)
            red_flag_count = len(investigation.red_flags)

            if positive_count == red_flag_count:
                logger.debug(
                    "Skipping color update for %s: inconclusive signals "
                    "(positive=%d, red_flags=%d)",
                    investigation.company_symbol,
                    positive_count,
                    red_flag_count,
                )
                return False

            if positive_count > red_flag_count:
                color = "Blue"
                comment = (
                    f"AI assessment: positive outlook "
                    f"({positive_count} positive signals vs {red_flag_count} red flags)"
                )
            else:
                color = "Red"
                comment = (
                    f"AI assessment: negative outlook "
                    f"({red_flag_count} red flags vs {positive_count} positive signals)"
                )

            result = await self.client.update_color(
                investigation.company_symbol, color, comment
            )

            if result is not None:
                logger.info(
                    "Updated color for %s to %s (assessment_id=%s)",
                    investigation.company_symbol,
                    color,
                    assessment.assessment_id,
                )
                return True

            logger.warning(
                "Failed to update color for %s (assessment_id=%s)",
                investigation.company_symbol,
                assessment.assessment_id,
            )
            return False
        except Exception:
            logger.exception(
                "Error updating color for %s",
                investigation.company_symbol,
            )
            return False
