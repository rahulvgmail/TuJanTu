"""Unit tests for the Phase 3A performance tracking system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.models.decision import DecisionAssessment, Recommendation, RecommendationTimeframe
from src.models.performance import RecommendationOutcome
from src.services.performance_tracker import PerformanceTracker, _classify_outcome, _pct_return


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeStockPulseClient:
    """In-memory stub for StockPulseClient.get_stock()."""

    def __init__(self, prices: dict[str, float | None] | None = None):
        # symbol -> price (or None to simulate missing data)
        self._prices: dict[str, float | None] = prices or {}

    def set_price(self, symbol: str, price: float | None) -> None:
        self._prices[symbol] = price

    async def get_stock(self, symbol: str) -> dict[str, Any] | None:
        price = self._prices.get(symbol)
        if price is None:
            return None
        return {"current_price": price}


class FakePerformanceRepository:
    """In-memory dict-backed repository matching MongoPerformanceRepository interface."""

    def __init__(self) -> None:
        self._store: dict[str, RecommendationOutcome] = {}

    async def save(self, outcome: RecommendationOutcome) -> str:
        if outcome.outcome_id in self._store:
            raise ValueError(f"Outcome with id '{outcome.outcome_id}' already exists")
        self._store[outcome.outcome_id] = outcome
        return outcome.outcome_id

    async def get(self, outcome_id: str) -> RecommendationOutcome | None:
        return self._store.get(outcome_id)

    async def get_open(self) -> list[RecommendationOutcome]:
        return [o for o in self._store.values() if not o.is_closed]

    async def get_by_company(self, symbol: str) -> list[RecommendationOutcome]:
        return [o for o in self._store.values() if o.company_symbol == symbol]

    async def update(self, outcome: RecommendationOutcome) -> None:
        self._store[outcome.outcome_id] = outcome

    async def get_all(self, limit: int = 100) -> list[RecommendationOutcome]:
        items = sorted(self._store.values(), key=lambda o: o.created_at, reverse=True)
        return items[:limit]

    async def ensure_indexes(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assessment(
    *,
    symbol: str = "RELIANCE",
    company_name: str = "Reliance Industries",
    recommendation: Recommendation = Recommendation.BUY,
    timeframe: RecommendationTimeframe = RecommendationTimeframe.MEDIUM_TERM,
    confidence: float = 0.85,
) -> DecisionAssessment:
    return DecisionAssessment(
        investigation_id="inv-001",
        trigger_id="trg-001",
        company_symbol=symbol,
        company_name=company_name,
        new_recommendation=recommendation,
        timeframe=timeframe,
        confidence=confidence,
    )


def _make_outcome(
    *,
    symbol: str = "RELIANCE",
    company_name: str = "Reliance Industries",
    recommendation: str = "buy",
    confidence: float = 0.85,
    entry_price: float = 100.0,
    entry_date: datetime | None = None,
    is_closed: bool = False,
    outcome: str | None = None,
    return_3m_pct: float | None = None,
    price_1w: float | None = None,
    price_1m: float | None = None,
    price_3m: float | None = None,
) -> RecommendationOutcome:
    return RecommendationOutcome(
        assessment_id="asmt-001",
        company_symbol=symbol,
        company_name=company_name,
        recommendation=recommendation,
        confidence=confidence,
        timeframe="medium_term",
        entry_price=entry_price,
        entry_date=entry_date or datetime.now(timezone.utc),
        is_closed=is_closed,
        outcome=outcome,
        return_3m_pct=return_3m_pct,
        price_1w=price_1w,
        price_1m=price_1m,
        price_3m=price_3m,
    )


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestPctReturn:
    def test_positive_return(self) -> None:
        assert _pct_return(100.0, 110.0) == pytest.approx(10.0)

    def test_negative_return(self) -> None:
        assert _pct_return(100.0, 90.0) == pytest.approx(-10.0)

    def test_zero_entry_price_returns_zero(self) -> None:
        assert _pct_return(0.0, 50.0) == 0.0

    def test_no_change(self) -> None:
        assert _pct_return(100.0, 100.0) == pytest.approx(0.0)


class TestClassifyOutcome:
    def test_win(self) -> None:
        assert _classify_outcome(5.01) == "win"

    def test_loss(self) -> None:
        assert _classify_outcome(-5.01) == "loss"

    def test_neutral_positive(self) -> None:
        assert _classify_outcome(5.0) == "neutral"

    def test_neutral_negative(self) -> None:
        assert _classify_outcome(-5.0) == "neutral"

    def test_neutral_zero(self) -> None:
        assert _classify_outcome(0.0) == "neutral"


# ---------------------------------------------------------------------------
# PerformanceTracker.record_entry
# ---------------------------------------------------------------------------


class TestRecordEntry:
    @pytest.mark.asyncio
    async def test_creates_outcome_from_assessment(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)
        assessment = _make_assessment()

        outcome = await tracker.record_entry(assessment, entry_price=150.0)

        assert outcome.company_symbol == "RELIANCE"
        assert outcome.company_name == "Reliance Industries"
        assert outcome.recommendation == "buy"
        assert outcome.confidence == 0.85
        assert outcome.timeframe == "medium_term"
        assert outcome.entry_price == 150.0
        assert outcome.is_closed is False
        assert outcome.outcome is None

    @pytest.mark.asyncio
    async def test_persists_to_repo(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)
        assessment = _make_assessment()

        outcome = await tracker.record_entry(assessment, entry_price=150.0)
        stored = await repo.get(outcome.outcome_id)

        assert stored is not None
        assert stored.outcome_id == outcome.outcome_id

    @pytest.mark.asyncio
    async def test_handles_enum_recommendation(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)
        assessment = _make_assessment(recommendation=Recommendation.SELL)

        outcome = await tracker.record_entry(assessment, entry_price=200.0)

        assert outcome.recommendation == "sell"

    @pytest.mark.asyncio
    async def test_entry_date_is_set(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)
        before = datetime.now(timezone.utc)

        outcome = await tracker.record_entry(_make_assessment(), entry_price=100.0)

        after = datetime.now(timezone.utc)
        assert before <= outcome.entry_date <= after


# ---------------------------------------------------------------------------
# PerformanceTracker.update_checkpoints
# ---------------------------------------------------------------------------


class TestUpdateCheckpoints:
    @pytest.mark.asyncio
    async def test_no_open_outcomes_returns_zero(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        count = await tracker.update_checkpoints()

        assert count == 0

    @pytest.mark.asyncio
    async def test_fills_1w_checkpoint_at_7_days(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 110.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=8),
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 1
        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_1w == 110.0
        assert updated.return_1w_pct == pytest.approx(10.0, abs=0.01)
        assert updated.is_closed is False

    @pytest.mark.asyncio
    async def test_fills_1m_checkpoint_at_30_days(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 120.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=31),
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 1
        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_1w is not None  # also filled since 31 > 7
        assert updated.price_1m == 120.0
        assert updated.return_1m_pct == pytest.approx(20.0, abs=0.01)
        assert updated.is_closed is False

    @pytest.mark.asyncio
    async def test_fills_3m_checkpoint_and_closes_at_90_days(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 108.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=91),
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 1
        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_3m == 108.0
        assert updated.return_3m_pct == pytest.approx(8.0, abs=0.01)
        assert updated.outcome == "win"
        assert updated.is_closed is True
        assert updated.closed_at is not None

    @pytest.mark.asyncio
    async def test_3m_outcome_classified_as_loss(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 90.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=91),
        )
        await repo.save(outcome)

        await tracker.update_checkpoints()

        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.outcome == "loss"

    @pytest.mark.asyncio
    async def test_3m_outcome_classified_as_neutral(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 103.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=91),
        )
        await repo.save(outcome)

        await tracker.update_checkpoints()

        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.outcome == "neutral"

    @pytest.mark.asyncio
    async def test_skips_outcome_when_price_unavailable(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()  # no prices configured
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=8),
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 0
        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_1w is None

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_checkpoint(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 999.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=31),
            price_1w=105.0,  # already filled
        )
        await repo.save(outcome)

        await tracker.update_checkpoints()

        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_1w == 105.0  # unchanged
        assert updated.price_1m == 999.0  # newly filled

    @pytest.mark.asyncio
    async def test_skips_closed_outcomes(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 200.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=91),
            is_closed=True,
            outcome="win",
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 0

    @pytest.mark.asyncio
    async def test_too_recent_outcome_not_updated(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 110.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        outcome = _make_outcome(
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=3),
        )
        await repo.save(outcome)

        count = await tracker.update_checkpoints()

        assert count == 0
        updated = await repo.get(outcome.outcome_id)
        assert updated is not None
        assert updated.price_1w is None

    @pytest.mark.asyncio
    async def test_multiple_outcomes_updated(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient(prices={"RELIANCE": 110.0, "TCS": 220.0})
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        o1 = _make_outcome(
            symbol="RELIANCE",
            entry_price=100.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=8),
        )
        o2 = _make_outcome(
            symbol="TCS",
            company_name="TCS",
            entry_price=200.0,
            entry_date=datetime.now(timezone.utc) - timedelta(days=10),
        )
        await repo.save(o1)
        await repo.save(o2)

        count = await tracker.update_checkpoints()

        assert count == 2


# ---------------------------------------------------------------------------
# PerformanceTracker.get_summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_empty_summary(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        summary = await tracker.get_summary()

        assert summary["total_recommendations"] == 0
        assert summary["open_recommendations"] == 0
        assert summary["closed_recommendations"] == 0
        assert summary["wins"] == 0
        assert summary["losses"] == 0
        assert summary["neutrals"] == 0
        assert summary["win_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_summary_with_mixed_outcomes(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        # One open outcome
        await repo.save(_make_outcome(recommendation="buy", is_closed=False))

        # Closed win (buy, +10%)
        await repo.save(
            _make_outcome(
                symbol="TCS",
                company_name="TCS",
                recommendation="buy",
                is_closed=True,
                outcome="win",
                return_3m_pct=10.0,
            )
        )

        # Closed loss (sell, -8%)
        await repo.save(
            _make_outcome(
                symbol="INFY",
                company_name="Infosys",
                recommendation="sell",
                is_closed=True,
                outcome="loss",
                return_3m_pct=-8.0,
            )
        )

        # Closed neutral (hold, +2%)
        await repo.save(
            _make_outcome(
                symbol="HDFC",
                company_name="HDFC",
                recommendation="hold",
                is_closed=True,
                outcome="neutral",
                return_3m_pct=2.0,
            )
        )

        summary = await tracker.get_summary()

        assert summary["total_recommendations"] == 4
        assert summary["open_recommendations"] == 1
        assert summary["closed_recommendations"] == 3
        assert summary["wins"] == 1
        assert summary["losses"] == 1
        assert summary["neutrals"] == 1
        assert summary["win_rate"] == pytest.approx(1 / 3, abs=0.001)
        assert summary["avg_return_buy"] == pytest.approx(10.0, abs=0.01)
        assert summary["avg_return_sell"] == pytest.approx(-8.0, abs=0.01)
        assert summary["avg_return_hold"] == pytest.approx(2.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_summary_by_recommendation_counts(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        await repo.save(_make_outcome(symbol="A", recommendation="buy"))
        await repo.save(_make_outcome(symbol="B", recommendation="buy"))
        await repo.save(_make_outcome(symbol="C", recommendation="sell"))

        summary = await tracker.get_summary()

        assert summary["by_recommendation"]["buy"] == 2
        assert summary["by_recommendation"]["sell"] == 1
        assert summary["by_recommendation"]["hold"] == 0

    @pytest.mark.asyncio
    async def test_summary_avg_return_none_when_no_closed_for_type(self) -> None:
        repo = FakePerformanceRepository()
        client = FakeStockPulseClient()
        tracker = PerformanceTracker(repo=repo, stockpulse_client=client)

        # Only open outcomes, no closed
        await repo.save(_make_outcome(recommendation="buy"))

        summary = await tracker.get_summary()

        assert summary["avg_return_buy"] is None
        assert summary["avg_return_sell"] is None
        assert summary["avg_return_hold"] is None


# ---------------------------------------------------------------------------
# FakePerformanceRepository (in-memory repo CRUD)
# ---------------------------------------------------------------------------


class TestFakePerformanceRepository:
    """Validate the in-memory repo behaves correctly, acting as a proxy
    for MongoPerformanceRepository contract tests."""

    @pytest.mark.asyncio
    async def test_save_and_get(self) -> None:
        repo = FakePerformanceRepository()
        outcome = _make_outcome()

        saved_id = await repo.save(outcome)
        retrieved = await repo.get(saved_id)

        assert retrieved is not None
        assert retrieved.outcome_id == outcome.outcome_id
        assert retrieved.entry_price == 100.0

    @pytest.mark.asyncio
    async def test_save_duplicate_raises(self) -> None:
        repo = FakePerformanceRepository()
        outcome = _make_outcome()
        await repo.save(outcome)

        with pytest.raises(ValueError, match="already exists"):
            await repo.save(outcome)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self) -> None:
        repo = FakePerformanceRepository()

        result = await repo.get("does-not-exist")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_open_returns_only_open(self) -> None:
        repo = FakePerformanceRepository()
        open_outcome = _make_outcome(symbol="OPEN")
        closed_outcome = _make_outcome(symbol="CLOSED", is_closed=True, outcome="win")
        await repo.save(open_outcome)
        await repo.save(closed_outcome)

        results = await repo.get_open()

        assert len(results) == 1
        assert results[0].company_symbol == "OPEN"

    @pytest.mark.asyncio
    async def test_get_by_company(self) -> None:
        repo = FakePerformanceRepository()
        await repo.save(_make_outcome(symbol="RELIANCE"))
        await repo.save(_make_outcome(symbol="TCS", company_name="TCS"))

        results = await repo.get_by_company("RELIANCE")

        assert len(results) == 1
        assert results[0].company_symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_update_modifies_stored_outcome(self) -> None:
        repo = FakePerformanceRepository()
        outcome = _make_outcome()
        await repo.save(outcome)

        outcome.price_1w = 105.0
        outcome.return_1w_pct = 5.0
        await repo.update(outcome)

        retrieved = await repo.get(outcome.outcome_id)
        assert retrieved is not None
        assert retrieved.price_1w == 105.0
        assert retrieved.return_1w_pct == 5.0

    @pytest.mark.asyncio
    async def test_get_all_with_limit(self) -> None:
        repo = FakePerformanceRepository()
        for sym in ["A", "B", "C", "D"]:
            await repo.save(_make_outcome(symbol=sym))

        results = await repo.get_all(limit=2)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_all_returns_everything_with_high_limit(self) -> None:
        repo = FakePerformanceRepository()
        for sym in ["A", "B", "C"]:
            await repo.save(_make_outcome(symbol=sym))

        results = await repo.get_all(limit=100)

        assert len(results) == 3
