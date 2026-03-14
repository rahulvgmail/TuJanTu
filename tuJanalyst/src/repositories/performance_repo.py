"""MongoDB repository for recommendation outcome tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from src.models.performance import RecommendationOutcome

RECOMMENDATION_OUTCOMES_COLLECTION = "recommendation_outcomes"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _strip_mongo_id(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


class MongoPerformanceRepository:
    """MongoDB-backed repository for recommendation outcomes."""

    COLLECTION = RECOMMENDATION_OUTCOMES_COLLECTION

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db[self.COLLECTION]

    async def save(self, outcome: RecommendationOutcome) -> str:
        """Persist a new recommendation outcome."""
        payload = outcome.model_dump()
        try:
            await self.collection.insert_one(payload)
        except DuplicateKeyError as exc:
            raise ValueError(f"Outcome with id '{outcome.outcome_id}' already exists") from exc
        return outcome.outcome_id

    async def get(self, outcome_id: str) -> RecommendationOutcome | None:
        """Retrieve a single outcome by its ID."""
        document = await self.collection.find_one({"outcome_id": outcome_id})
        cleaned = _strip_mongo_id(document)
        return RecommendationOutcome.model_validate(cleaned) if cleaned else None

    async def get_open(self) -> list[RecommendationOutcome]:
        """Return all outcomes that are not yet closed."""
        cursor = self.collection.find({"is_closed": False}).sort("entry_date", ASCENDING)
        items: list[RecommendationOutcome] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(RecommendationOutcome.model_validate(cleaned))
        return items

    async def get_by_company(self, symbol: str) -> list[RecommendationOutcome]:
        """Return all outcomes for a specific company symbol."""
        cursor = self.collection.find({"company_symbol": symbol}).sort("entry_date", -1)
        items: list[RecommendationOutcome] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(RecommendationOutcome.model_validate(cleaned))
        return items

    async def update(self, outcome: RecommendationOutcome) -> None:
        """Update an existing outcome document."""
        outcome.updated_at = _utc_now()
        payload = outcome.model_dump()
        payload.pop("_id", None)
        await self.collection.replace_one(
            {"outcome_id": outcome.outcome_id},
            payload,
        )

    async def get_all(self, limit: int = 100) -> list[RecommendationOutcome]:
        """Return all outcomes, most recent first."""
        cursor = self.collection.find().sort("created_at", -1).limit(limit)
        items: list[RecommendationOutcome] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(RecommendationOutcome.model_validate(cleaned))
        return items

    async def ensure_indexes(self) -> None:
        """Create required indexes for the recommendation_outcomes collection."""
        await self.collection.create_index(
            [("outcome_id", ASCENDING)],
            unique=True,
            name="uq_outcome_id",
        )
        await self.collection.create_index(
            [("company_symbol", ASCENDING)],
            name="idx_outcome_company_symbol",
        )
        await self.collection.create_index(
            [("is_closed", ASCENDING)],
            name="idx_outcome_is_closed",
        )
        await self.collection.create_index(
            [("assessment_id", ASCENDING)],
            name="idx_outcome_assessment_id",
        )
