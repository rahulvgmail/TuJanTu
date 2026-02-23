"""Repository interfaces and concrete data access helpers."""

from src.repositories.base import (
    AssessmentRepository,
    DocumentRepository,
    InvestigationRepository,
    PositionRepository,
    ReportRepository,
    TriggerRepository,
    VectorRepository,
)
from src.repositories.mongo import (
    MongoAssessmentRepository,
    MongoDocumentRepository,
    MongoInvestigationRepository,
    MongoPositionRepository,
    MongoReportRepository,
    MongoTriggerRepository,
    create_mongo_client,
    ensure_indexes,
    get_database,
)
from src.repositories.vector import ChromaVectorRepository

__all__ = [
    "AssessmentRepository",
    "DocumentRepository",
    "InvestigationRepository",
    "MongoAssessmentRepository",
    "MongoDocumentRepository",
    "MongoInvestigationRepository",
    "MongoPositionRepository",
    "MongoReportRepository",
    "MongoTriggerRepository",
    "ChromaVectorRepository",
    "PositionRepository",
    "ReportRepository",
    "TriggerRepository",
    "VectorRepository",
    "create_mongo_client",
    "ensure_indexes",
    "get_database",
]
