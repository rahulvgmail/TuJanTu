"""Document download component for Layer 1 trigger ingestion."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.models.document import DocumentType, ProcessingStatus, RawDocument
from src.repositories.base import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentFetcher:
    """Download and persist files linked from exchange announcements."""

    def __init__(
        self,
        doc_repo: DocumentRepository,
        download_dir: str = "./data/documents",
        max_size_mb: int = 50,
        session: httpx.AsyncClient | None = None,
    ):
        self.doc_repo = doc_repo
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.session = session or httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
            },
        )

    async def fetch(self, trigger_id: str, url: str, company_symbol: str | None = None) -> RawDocument:
        """Download a linked file and persist metadata/content status."""
        document = RawDocument(
            trigger_id=trigger_id,
            source_url=url,
            company_symbol=company_symbol,
            processing_status=ProcessingStatus.DOWNLOADING,
        )
        await self.doc_repo.save(document)

        try:
            response = await self.session.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            document.content_type = content_type
            document.document_type = self._detect_type(url=url, content_type=content_type)
            document.file_size_bytes = len(response.content)

            if document.file_size_bytes > self.max_size_bytes:
                document.processing_status = ProcessingStatus.ERROR
                document.processing_errors.append(
                    f"File too large: {document.file_size_bytes} bytes (limit={self.max_size_bytes})"
                )
                await self.doc_repo.save(document)
                logger.warning(
                    "Rejected oversized file: url=%s size=%s limit=%s",
                    url,
                    document.file_size_bytes,
                    self.max_size_bytes,
                )
                return document

            extension = self._type_to_extension(document.document_type)
            file_path = self.download_dir / f"{document.document_id}.{extension}"
            file_path.write_bytes(response.content)

            document.file_path = str(file_path)
            document.processing_status = ProcessingStatus.DOWNLOADED
            await self.doc_repo.save(document)
            logger.info("Downloaded document: url=%s document_id=%s", url, document.document_id)
            return document

        except Exception as exc:  # noqa: BLE001
            document.processing_status = ProcessingStatus.ERROR
            document.processing_errors.append(str(exc))
            await self.doc_repo.save(document)
            logger.error("Document download failed: url=%s error=%s", url, exc)
            return document

    async def close(self) -> None:
        """Close underlying HTTP session."""
        await self.session.aclose()

    def _detect_type(self, url: str, content_type: str) -> DocumentType:
        lowered_ct = content_type.lower()
        path = urlparse(url).path.lower()

        if lowered_ct.startswith("application/pdf") or path.endswith(".pdf"):
            return DocumentType.PDF
        if "text/html" in lowered_ct or path.endswith(".html") or path.endswith(".htm"):
            return DocumentType.HTML
        if "spreadsheet" in lowered_ct or path.endswith(".xlsx") or path.endswith(".xls"):
            return DocumentType.EXCEL
        if lowered_ct.startswith("text/plain") or path.endswith(".txt"):
            return DocumentType.TEXT
        return DocumentType.UNKNOWN

    def _type_to_extension(self, document_type: DocumentType) -> str:
        if document_type == DocumentType.PDF:
            return "pdf"
        if document_type == DocumentType.HTML:
            return "html"
        if document_type == DocumentType.EXCEL:
            return "xlsx"
        if document_type == DocumentType.TEXT:
            return "txt"
        return "bin"

