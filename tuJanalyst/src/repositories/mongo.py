"""MongoDB connection and initialization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from pymongo.errors import PyMongoError

from src.models.company import CompanyPosition
from src.models.decision import DecisionAssessment
from src.models.document import ProcessingStatus, RawDocument
from src.models.investigation import Investigation
from src.models.report import AnalysisReport
from src.models.trigger import TriggerEvent, TriggerStatus

TRIGGERS_COLLECTION = "triggers"
DOCUMENTS_COLLECTION = "documents"
INVESTIGATIONS_COLLECTION = "investigations"
ASSESSMENTS_COLLECTION = "assessments"
POSITIONS_COLLECTION = "positions"
REPORTS_COLLECTION = "reports"


async def create_mongo_client(mongodb_uri: str) -> AsyncIOMotorClient:
    """Create and validate an async MongoDB client connection."""
    try:
        client = AsyncIOMotorClient(mongodb_uri)
        await client.admin.command("ping")
        return client
    except PyMongoError as exc:
        raise RuntimeError(f"Failed to connect to MongoDB at {mongodb_uri}: {exc}") from exc


def get_database(client: AsyncIOMotorClient, database_name: str) -> AsyncIOMotorDatabase:
    """Return configured MongoDB database handle."""
    return client[database_name]


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create required MongoDB indexes for trigger and document collections."""
    try:
        await db[TRIGGERS_COLLECTION].create_index([("trigger_id", ASCENDING)], unique=True, name="uq_trigger_id")
        await db[TRIGGERS_COLLECTION].create_index([("source_url", ASCENDING)], name="idx_source_url")
        await db[TRIGGERS_COLLECTION].create_index([("status", ASCENDING)], name="idx_status")
        await db[TRIGGERS_COLLECTION].create_index([("company_symbol", ASCENDING)], name="idx_trigger_company_symbol")
        await db[TRIGGERS_COLLECTION].create_index([("created_at", ASCENDING)], name="idx_trigger_created_at")

        await db[DOCUMENTS_COLLECTION].create_index([("document_id", ASCENDING)], unique=True, name="uq_document_id")
        await db[DOCUMENTS_COLLECTION].create_index([("trigger_id", ASCENDING)], name="idx_document_trigger_id")
        await db[DOCUMENTS_COLLECTION].create_index([("company_symbol", ASCENDING)], name="idx_document_company_symbol")

        await db[INVESTIGATIONS_COLLECTION].create_index(
            [("investigation_id", ASCENDING)], unique=True, name="uq_investigation_id"
        )
        await db[INVESTIGATIONS_COLLECTION].create_index(
            [("company_symbol", ASCENDING), ("created_at", ASCENDING)],
            name="idx_investigation_company_created",
        )
        await db[INVESTIGATIONS_COLLECTION].create_index(
            [("is_significant", ASCENDING)],
            name="idx_investigation_significant",
        )

        await db[ASSESSMENTS_COLLECTION].create_index(
            [("assessment_id", ASCENDING)], unique=True, name="uq_assessment_id"
        )
        await db[ASSESSMENTS_COLLECTION].create_index(
            [("investigation_id", ASCENDING)],
            name="idx_assessment_investigation_id",
        )
        await db[ASSESSMENTS_COLLECTION].create_index(
            [("company_symbol", ASCENDING), ("created_at", ASCENDING)],
            name="idx_assessment_company_created",
        )

        await db[POSITIONS_COLLECTION].create_index(
            [("company_symbol", ASCENDING)], unique=True, name="uq_position_company_symbol"
        )

        await db[REPORTS_COLLECTION].create_index([("report_id", ASCENDING)], unique=True, name="uq_report_id")
        await db[REPORTS_COLLECTION].create_index(
            [("created_at", ASCENDING)],
            name="idx_report_created_at",
        )
        await db[REPORTS_COLLECTION].create_index(
            [("company_symbol", ASCENDING)],
            name="idx_report_company_symbol",
        )
    except PyMongoError as exc:
        raise RuntimeError(f"Failed to ensure MongoDB indexes: {exc}") from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_mongo_id(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


class MongoTriggerRepository:
    """MongoDB-backed trigger repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[TRIGGERS_COLLECTION]

    async def save(self, trigger: TriggerEvent) -> str:
        payload = trigger.model_dump()
        try:
            await self.collection.insert_one(payload)
        except DuplicateKeyError as exc:
            raise ValueError(f"Trigger with id '{trigger.trigger_id}' already exists") from exc
        return trigger.trigger_id

    async def get(self, trigger_id: str) -> TriggerEvent | None:
        document = await self.collection.find_one({"trigger_id": trigger_id})
        cleaned = _strip_mongo_id(document)
        return TriggerEvent.model_validate(cleaned) if cleaned else None

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None:
        status_value = status.value if isinstance(status, TriggerStatus) else str(status)
        await self.collection.update_one(
            {"trigger_id": trigger_id},
            {
                "$set": {
                    "status": status_value,
                    "updated_at": _utc_now(),
                },
                "$push": {
                    "status_history": {
                        "status": status_value,
                        "timestamp": _utc_now(),
                        "reason": reason,
                    }
                },
            },
        )

    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]:
        cursor = self.collection.find({"status": TriggerStatus.PENDING.value}).sort("created_at", ASCENDING).limit(limit)
        items: list[TriggerEvent] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(TriggerEvent.model_validate(cleaned))
        return items

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[TriggerEvent]:
        cursor = (
            self.collection.find({"company_symbol": company_symbol})
            .sort("created_at", ASCENDING)
            .limit(limit)
        )
        items: list[TriggerEvent] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(TriggerEvent.model_validate(cleaned))
        return items

    async def exists_by_url(self, source_url: str) -> bool:
        if not source_url:
            return False
        count = await self.collection.count_documents({"source_url": source_url}, limit=1)
        return count > 0

    async def list_recent(
        self,
        limit: int = 20,
        offset: int = 0,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[TriggerEvent]:
        query = self._build_query(
            status=status,
            company_symbol=company_symbol,
            source=source,
            since=since,
        )
        cursor = self.collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
        items: list[TriggerEvent] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(TriggerEvent.model_validate(cleaned))
        return items

    async def count(
        self,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> int:
        query = self._build_query(
            status=status,
            company_symbol=company_symbol,
            source=source,
            since=since,
        )
        return int(await self.collection.count_documents(query))

    async def counts_by_status(self, since: datetime | None = None) -> dict[str, int]:
        pipeline: list[dict[str, Any]] = []
        if since is not None:
            pipeline.append({"$match": {"created_at": {"$gte": since}}})
        pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})

        result: dict[str, int] = {}
        async for row in self.collection.aggregate(pipeline):
            status = str(row.get("_id") or "unknown")
            result[status] = int(row.get("count", 0))
        return result

    async def counts_by_source(self, since: datetime | None = None) -> dict[str, int]:
        pipeline: list[dict[str, Any]] = []
        if since is not None:
            pipeline.append({"$match": {"created_at": {"$gte": since}}})
        pipeline.append({"$group": {"_id": "$source", "count": {"$sum": 1}}})

        result: dict[str, int] = {}
        async for row in self.collection.aggregate(pipeline):
            source = str(row.get("_id") or "unknown")
            result[source] = int(row.get("count", 0))
        return result

    def _build_query(
        self,
        *,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = status.value if isinstance(status, TriggerStatus) else str(status)
        if company_symbol:
            query["company_symbol"] = company_symbol
        if source:
            query["source"] = source
        if since is not None:
            query["created_at"] = {"$gte": since}
        return query


class MongoDocumentRepository:
    """MongoDB-backed document repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[DOCUMENTS_COLLECTION]

    async def save(self, document: RawDocument) -> str:
        payload = document.model_dump()
        await self.collection.replace_one({"document_id": document.document_id}, payload, upsert=True)
        return document.document_id

    async def get(self, document_id: str) -> RawDocument | None:
        document = await self.collection.find_one({"document_id": document_id})
        cleaned = _strip_mongo_id(document)
        return RawDocument.model_validate(cleaned) if cleaned else None

    async def get_by_trigger(self, trigger_id: str) -> list[RawDocument]:
        cursor = self.collection.find({"trigger_id": trigger_id}).sort("created_at", ASCENDING)
        items: list[RawDocument] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(RawDocument.model_validate(cleaned))
        return items

    async def update_extracted_text(self, document_id: str, text: str, method: str, metadata: dict) -> None:
        await self.collection.update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "extracted_text": text,
                    "extraction_method": method,
                    "extraction_metadata": metadata,
                    "processing_status": ProcessingStatus.EXTRACTED.value,
                    "updated_at": _utc_now(),
                }
            },
        )


class MongoInvestigationRepository:
    """MongoDB-backed investigation repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[INVESTIGATIONS_COLLECTION]
        self.assessments_collection = db[ASSESSMENTS_COLLECTION]

    async def save(self, investigation: Investigation) -> str:
        payload = investigation.model_dump()
        await self.collection.replace_one(
            {"investigation_id": investigation.investigation_id},
            payload,
            upsert=True,
        )
        return investigation.investigation_id

    async def get(self, investigation_id: str) -> Investigation | None:
        document = await self.collection.find_one({"investigation_id": investigation_id})
        cleaned = _strip_mongo_id(document)
        return Investigation.model_validate(cleaned) if cleaned else None

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[Investigation]:
        cursor = (
            self.collection.find({"company_symbol": company_symbol})
            .sort("created_at", -1)
            .limit(limit)
        )
        items: list[Investigation] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(Investigation.model_validate(cleaned))
        return items

    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]:
        changed_ids: list[str] = []
        cursor = self.assessments_collection.find(
            {"company_symbol": company_symbol, "recommendation_changed": True},
            {"investigation_id": 1, "_id": 0},
        )
        async for row in cursor:
            investigation_id = row.get("investigation_id")
            if isinstance(investigation_id, str) and investigation_id:
                changed_ids.append(investigation_id)

        query: dict[str, Any] = {
            "company_symbol": company_symbol,
            "is_significant": True,
        }
        if changed_ids:
            query["investigation_id"] = {"$nin": changed_ids}

        cursor = self.collection.find(query).sort("created_at", -1)
        items: list[Investigation] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(Investigation.model_validate(cleaned))
        return items


class MongoAssessmentRepository:
    """MongoDB-backed decision assessment repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[ASSESSMENTS_COLLECTION]

    async def save(self, assessment: DecisionAssessment) -> str:
        payload = assessment.model_dump()
        await self.collection.replace_one(
            {"assessment_id": assessment.assessment_id},
            payload,
            upsert=True,
        )
        return assessment.assessment_id

    async def get(self, assessment_id: str) -> DecisionAssessment | None:
        document = await self.collection.find_one({"assessment_id": assessment_id})
        cleaned = _strip_mongo_id(document)
        return DecisionAssessment.model_validate(cleaned) if cleaned else None

    async def get_by_company(self, company_symbol: str, limit: int = 10) -> list[DecisionAssessment]:
        cursor = (
            self.collection.find({"company_symbol": company_symbol})
            .sort("created_at", -1)
            .limit(limit)
        )
        items: list[DecisionAssessment] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(DecisionAssessment.model_validate(cleaned))
        return items


class MongoPositionRepository:
    """MongoDB-backed current company-position repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[POSITIONS_COLLECTION]

    async def get_position(self, company_symbol: str) -> CompanyPosition | None:
        document = await self.collection.find_one({"company_symbol": company_symbol})
        cleaned = _strip_mongo_id(document)
        return CompanyPosition.model_validate(cleaned) if cleaned else None

    async def list_positions(self, limit: int = 200) -> list[CompanyPosition]:
        cursor = self.collection.find({}).sort("updated_at", -1).limit(limit)
        items: list[CompanyPosition] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(CompanyPosition.model_validate(cleaned))
        return items

    async def upsert_position(self, position: CompanyPosition) -> None:
        payload = position.model_dump()
        await self.collection.replace_one(
            {"company_symbol": position.company_symbol},
            payload,
            upsert=True,
        )


class MongoReportRepository:
    """MongoDB-backed analysis report repository."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db[REPORTS_COLLECTION]

    async def save(self, report: AnalysisReport) -> str:
        payload = report.model_dump()
        await self.collection.replace_one({"report_id": report.report_id}, payload, upsert=True)
        return report.report_id

    async def get(self, report_id: str) -> AnalysisReport | None:
        document = await self.collection.find_one({"report_id": report_id})
        cleaned = _strip_mongo_id(document)
        return AnalysisReport.model_validate(cleaned) if cleaned else None

    async def get_recent(self, limit: int = 20) -> list[AnalysisReport]:
        cursor = self.collection.find({}).sort("created_at", -1).limit(limit)
        items: list[AnalysisReport] = []
        async for document in cursor:
            cleaned = _strip_mongo_id(document)
            if cleaned:
                items.append(AnalysisReport.model_validate(cleaned))
        return items

    async def update_feedback(
        self,
        report_id: str,
        rating: int | None = None,
        comment: str | None = None,
        by: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"feedback_at": _utc_now()}
        if rating is not None:
            payload["feedback_rating"] = rating
        if comment is not None:
            payload["feedback_comment"] = comment
        if by is not None:
            payload["feedback_by"] = by
        await self.collection.update_one({"report_id": report_id}, {"$set": payload})
