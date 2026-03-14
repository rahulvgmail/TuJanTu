"""Performance feedback loop service for tracking recommendation outcomes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.agents.tools.stockpulse_client import StockPulseClient
from src.models.decision import DecisionAssessment
from src.models.performance import RecommendationOutcome
from src.repositories.performance_repo import MongoPerformanceRepository

logger = logging.getLogger(__name__)

_WIN_THRESHOLD_PCT = 5.0
_LOSS_THRESHOLD_PCT = -5.0


def _pct_return(entry_price: float, current_price: float) -> float:
    """Calculate percentage return from entry to current price."""
    if entry_price <= 0:
        return 0.0
    return ((current_price / entry_price) - 1.0) * 100.0


def _classify_outcome(return_pct: float) -> str:
    """Classify a return percentage as win, loss, or neutral."""
    if return_pct > _WIN_THRESHOLD_PCT:
        return "win"
    if return_pct < _LOSS_THRESHOLD_PCT:
        return "loss"
    return "neutral"


class PerformanceTracker:
    """Track recommendation outcomes over time with periodic checkpoint updates."""

    def __init__(
        self,
        repo: MongoPerformanceRepository,
        stockpulse_client: StockPulseClient,
    ):
        self.repo = repo
        self.client = stockpulse_client

    async def record_entry(
        self,
        assessment: DecisionAssessment,
        entry_price: float,
    ) -> RecommendationOutcome:
        """Record a new recommendation with entry price."""
        now = datetime.now(timezone.utc)
        outcome = RecommendationOutcome(
            assessment_id=assessment.assessment_id,
            company_symbol=assessment.company_symbol,
            company_name=assessment.company_name,
            recommendation=assessment.new_recommendation
            if isinstance(assessment.new_recommendation, str)
            else assessment.new_recommendation.value
            if hasattr(assessment.new_recommendation, "value")
            else str(assessment.new_recommendation),
            confidence=assessment.confidence,
            timeframe=assessment.timeframe
            if isinstance(assessment.timeframe, str)
            else assessment.timeframe.value
            if hasattr(assessment.timeframe, "value")
            else str(assessment.timeframe),
            entry_price=entry_price,
            entry_date=now,
        )
        await self.repo.save(outcome)
        logger.info(
            "Recorded recommendation entry: symbol=%s recommendation=%s price=%.2f outcome_id=%s",
            outcome.company_symbol,
            outcome.recommendation,
            entry_price,
            outcome.outcome_id,
        )
        return outcome

    async def update_checkpoints(self) -> int:
        """Check all open outcomes and update price checkpoints.

        Called daily by scheduler. Returns count of outcomes updated.
        """
        open_outcomes = await self.repo.get_open()
        if not open_outcomes:
            logger.info("No open recommendation outcomes to update.")
            return 0

        now = datetime.now(timezone.utc)
        updated_count = 0

        for outcome in open_outcomes:
            current_price = await self._fetch_current_price(outcome.company_symbol)
            if current_price is None:
                logger.warning(
                    "Could not fetch price for %s; skipping outcome %s",
                    outcome.company_symbol,
                    outcome.outcome_id,
                )
                continue

            days_since_entry = (now - outcome.entry_date).days
            changed = False

            # 1-week checkpoint (7+ days)
            if days_since_entry >= 7 and outcome.price_1w is None:
                outcome.price_1w = current_price
                outcome.return_1w_pct = round(_pct_return(outcome.entry_price, current_price), 4)
                changed = True

            # 1-month checkpoint (30+ days)
            if days_since_entry >= 30 and outcome.price_1m is None:
                outcome.price_1m = current_price
                outcome.return_1m_pct = round(_pct_return(outcome.entry_price, current_price), 4)
                changed = True

            # 3-month checkpoint (90+ days) -- also closes the outcome
            if days_since_entry >= 90 and outcome.price_3m is None:
                outcome.price_3m = current_price
                outcome.return_3m_pct = round(_pct_return(outcome.entry_price, current_price), 4)
                # Use the latest available return for classification
                final_return = outcome.return_3m_pct
                outcome.outcome = _classify_outcome(final_return)
                outcome.is_closed = True
                outcome.closed_at = now
                changed = True

            if changed:
                await self.repo.update(outcome)
                updated_count += 1
                logger.info(
                    "Updated outcome checkpoint: outcome_id=%s symbol=%s days=%d closed=%s",
                    outcome.outcome_id,
                    outcome.company_symbol,
                    days_since_entry,
                    outcome.is_closed,
                )

        logger.info(
            "Checkpoint update complete: total_open=%d updated=%d",
            len(open_outcomes),
            updated_count,
        )
        return updated_count

    async def get_summary(self) -> dict:
        """Return aggregate performance stats."""
        all_outcomes = await self.repo.get_all(limit=1000)
        total = len(all_outcomes)

        closed = [o for o in all_outcomes if o.is_closed]
        wins = sum(1 for o in closed if o.outcome == "win")
        losses = sum(1 for o in closed if o.outcome == "loss")
        neutrals = sum(1 for o in closed if o.outcome == "neutral")

        win_rate = (wins / len(closed)) if closed else 0.0

        buy_returns = [
            o.return_3m_pct
            for o in closed
            if o.recommendation == "buy" and o.return_3m_pct is not None
        ]
        sell_returns = [
            o.return_3m_pct
            for o in closed
            if o.recommendation == "sell" and o.return_3m_pct is not None
        ]
        hold_returns = [
            o.return_3m_pct
            for o in closed
            if o.recommendation == "hold" and o.return_3m_pct is not None
        ]

        return {
            "total_recommendations": total,
            "open_recommendations": total - len(closed),
            "closed_recommendations": len(closed),
            "wins": wins,
            "losses": losses,
            "neutrals": neutrals,
            "win_rate": round(win_rate, 4),
            "avg_return_buy": round(sum(buy_returns) / len(buy_returns), 4) if buy_returns else None,
            "avg_return_sell": round(sum(sell_returns) / len(sell_returns), 4) if sell_returns else None,
            "avg_return_hold": round(sum(hold_returns) / len(hold_returns), 4) if hold_returns else None,
            "by_recommendation": {
                "buy": sum(1 for o in all_outcomes if o.recommendation == "buy"),
                "sell": sum(1 for o in all_outcomes if o.recommendation == "sell"),
                "hold": sum(1 for o in all_outcomes if o.recommendation == "hold"),
            },
        }

    async def _fetch_current_price(self, symbol: str) -> float | None:
        """Fetch the current stock price from StockPulse."""
        try:
            stock_data = await self.client.get_stock(symbol)
            if stock_data is None:
                return None
            # Try common price field names
            for key in ("current_price", "price", "last_price", "ltp"):
                value = stock_data.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
            return None
        except Exception:  # noqa: BLE001
            logger.warning("Failed to fetch price for %s from StockPulse", symbol, exc_info=True)
            return None
