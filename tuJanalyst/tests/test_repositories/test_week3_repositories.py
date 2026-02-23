"""Tests for Week 3+ Mongo repository implementations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from src.models.company import CompanyPosition
from src.models.decision import DecisionAssessment, Recommendation
from src.models.investigation import Investigation
from src.models.report import AnalysisReport
from src.repositories.mongo import (
    MongoAssessmentRepository,
    MongoInvestigationRepository,
    MongoPositionRepository,
    MongoReportRepository,
)


@pytest.fixture
def mock_db():
    client = AsyncMongoMockClient()
    return client["test_week3_db"]


@pytest.mark.asyncio
async def test_investigation_repository_save_get_and_company_queries(mock_db) -> None:
    repo = MongoInvestigationRepository(mock_db)
    now = datetime.now(timezone.utc)
    inv1 = Investigation(
        trigger_id="t1",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        created_at=now - timedelta(days=1),
    )
    inv2 = Investigation(
        trigger_id="t2",
        company_symbol="INOXWIND",
        company_name="Inox Wind Limited",
        created_at=now,
    )
    await repo.save(inv1)
    await repo.save(inv2)

    loaded = await repo.get(inv1.investigation_id)
    assert loaded is not None
    assert loaded.trigger_id == "t1"

    company_items = await repo.get_by_company("INOXWIND", limit=10)
    assert len(company_items) == 2
    assert company_items[0].investigation_id == inv2.investigation_id


@pytest.mark.asyncio
async def test_investigation_repository_get_past_inconclusive(mock_db) -> None:
    inv_repo = MongoInvestigationRepository(mock_db)
    assess_repo = MongoAssessmentRepository(mock_db)

    kept = Investigation(
        trigger_id="k1",
        company_symbol="ABB",
        company_name="ABB India Limited",
        is_significant=True,
    )
    changed = Investigation(
        trigger_id="c1",
        company_symbol="ABB",
        company_name="ABB India Limited",
        is_significant=True,
    )
    not_significant = Investigation(
        trigger_id="n1",
        company_symbol="ABB",
        company_name="ABB India Limited",
        is_significant=False,
    )
    for item in [kept, changed, not_significant]:
        await inv_repo.save(item)

    assessment = DecisionAssessment(
        investigation_id=changed.investigation_id,
        trigger_id=changed.trigger_id,
        company_symbol="ABB",
        company_name="ABB India Limited",
        recommendation_changed=True,
        new_recommendation=Recommendation.BUY,
    )
    await assess_repo.save(assessment)

    inconclusive = await inv_repo.get_past_inconclusive("ABB")
    ids = {item.investigation_id for item in inconclusive}

    assert kept.investigation_id in ids
    assert changed.investigation_id not in ids
    assert not_significant.investigation_id not in ids


@pytest.mark.asyncio
async def test_assessment_repository_save_get_and_get_by_company(mock_db) -> None:
    repo = MongoAssessmentRepository(mock_db)
    a1 = DecisionAssessment(
        investigation_id="i1",
        trigger_id="t1",
        company_symbol="BHEL",
        company_name="BHEL",
        recommendation_changed=True,
        new_recommendation=Recommendation.BUY,
    )
    a2 = DecisionAssessment(
        investigation_id="i2",
        trigger_id="t2",
        company_symbol="BHEL",
        company_name="BHEL",
    )
    await repo.save(a1)
    await repo.save(a2)

    loaded = await repo.get(a1.assessment_id)
    assert loaded is not None
    assert loaded.investigation_id == "i1"

    items = await repo.get_by_company("BHEL", limit=10)
    assert len(items) == 2


@pytest.mark.asyncio
async def test_position_repository_upsert_and_get(mock_db) -> None:
    repo = MongoPositionRepository(mock_db)
    position = CompanyPosition(
        company_symbol="SIEMENS",
        company_name="Siemens Limited",
        current_recommendation=Recommendation.HOLD,
        recommendation_basis="Baseline",
        total_investigations=1,
    )
    await repo.upsert_position(position)

    loaded = await repo.get_position("SIEMENS")
    assert loaded is not None
    assert loaded.current_recommendation == Recommendation.HOLD.value

    position.current_recommendation = Recommendation.BUY
    position.total_investigations = 2
    await repo.upsert_position(position)
    loaded_again = await repo.get_position("SIEMENS")
    assert loaded_again is not None
    assert loaded_again.current_recommendation == Recommendation.BUY.value
    assert loaded_again.total_investigations == 2
    positions = await repo.list_positions(limit=10)
    assert positions
    assert positions[0].company_symbol == "SIEMENS"


@pytest.mark.asyncio
async def test_report_repository_save_get_recent_and_update_feedback(mock_db) -> None:
    repo = MongoReportRepository(mock_db)
    r1 = AnalysisReport(
        assessment_id="a1",
        investigation_id="i1",
        trigger_id="t1",
        company_symbol="SUZLON",
        company_name="Suzlon Energy Limited",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    r2 = AnalysisReport(
        assessment_id="a2",
        investigation_id="i2",
        trigger_id="t2",
        company_symbol="SUZLON",
        company_name="Suzlon Energy Limited",
        created_at=datetime.now(timezone.utc),
    )
    await repo.save(r1)
    await repo.save(r2)

    loaded = await repo.get(r1.report_id)
    assert loaded is not None
    assert loaded.company_symbol == "SUZLON"

    recent = await repo.get_recent(limit=2)
    assert len(recent) == 2
    assert recent[0].report_id == r2.report_id

    await repo.update_feedback(r1.report_id, rating=5, comment="Useful", by="analyst")
    updated = await repo.get(r1.report_id)
    assert updated is not None
    assert updated.feedback_rating == 5
    assert updated.feedback_comment == "Useful"
    assert updated.feedback_by == "analyst"
    assert updated.feedback_at is not None
