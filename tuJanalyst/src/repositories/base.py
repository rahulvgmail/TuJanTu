"""Repository protocol definitions for the data access layer."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.models.company import CompanyPosition
from src.models.decision import DecisionAssessment
from src.models.document import RawDocument
from src.models.investigation import Investigation
from src.models.report import AnalysisReport
from src.models.trigger import TriggerEvent, TriggerStatus


class TriggerRepository(Protocol):
    """Data access contract for trigger entities."""

    async def save(self, trigger: TriggerEvent) -> str: ...

    async def get(self, trigger_id: str) -> TriggerEvent | None: ...

    async def update_status(self, trigger_id: str, status: TriggerStatus, reason: str = "") -> None: ...

    async def get_pending(self, limit: int = 50) -> list[TriggerEvent]: ...

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[TriggerEvent]: ...

    async def exists_by_url(self, source_url: str) -> bool: ...

    async def list_recent(
        self,
        limit: int = 20,
        offset: int = 0,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[TriggerEvent]: ...

    async def count(
        self,
        status: TriggerStatus | None = None,
        company_symbol: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> int: ...

    async def counts_by_status(self, since: datetime | None = None) -> dict[str, int]: ...

    async def counts_by_source(self, since: datetime | None = None) -> dict[str, int]: ...


class DocumentRepository(Protocol):
    """Data access contract for raw/processed documents."""

    async def save(self, document: RawDocument) -> str: ...

    async def get(self, document_id: str) -> RawDocument | None: ...

    async def get_by_trigger(self, trigger_id: str) -> list[RawDocument]: ...

    async def update_extracted_text(self, document_id: str, text: str, method: str, metadata: dict) -> None: ...


class VectorRepository(Protocol):
    """Data access contract for semantic embeddings storage."""

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str: ...

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]: ...

    async def delete_document(self, document_id: str) -> None: ...


class InvestigationRepository(Protocol):
    """Data access contract for Layer 3 investigations."""

    async def save(self, investigation: Investigation) -> str: ...

    async def get(self, investigation_id: str) -> Investigation | None: ...

    async def get_by_company(self, company_symbol: str, limit: int = 20) -> list[Investigation]: ...

    async def get_past_inconclusive(self, company_symbol: str) -> list[Investigation]: ...


class AssessmentRepository(Protocol):
    """Data access contract for Layer 4 assessments."""

    async def save(self, assessment: DecisionAssessment) -> str: ...

    async def get(self, assessment_id: str) -> DecisionAssessment | None: ...

    async def get_by_company(self, company_symbol: str, limit: int = 10) -> list[DecisionAssessment]: ...


class PositionRepository(Protocol):
    """Data access contract for current company positions."""

    async def get_position(self, company_symbol: str) -> CompanyPosition | None: ...

    async def list_positions(self, limit: int = 200) -> list[CompanyPosition]: ...

    async def upsert_position(self, position: CompanyPosition) -> None: ...


class ReportRepository(Protocol):
    """Data access contract for generated analysis reports."""

    async def save(self, report: AnalysisReport) -> str: ...

    async def get(self, report_id: str) -> AnalysisReport | None: ...

    async def get_recent(self, limit: int = 20) -> list[AnalysisReport]: ...

    async def update_feedback(
        self,
        report_id: str,
        rating: int | None = None,
        comment: str | None = None,
        by: str | None = None,
    ) -> None: ...
