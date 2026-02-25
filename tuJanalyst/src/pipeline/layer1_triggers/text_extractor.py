"""Text extraction for downloaded documents."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from src.models.document import DocumentType, ProcessingStatus, RawDocument
from src.repositories.base import DocumentRepository, VectorRepository

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extract text from PDF, HTML, and plaintext documents."""

    def __init__(
        self,
        doc_repo: DocumentRepository,
        vector_repo: VectorRepository | None = None,
        extraction_timeout_seconds: float | None = 60.0,
    ):
        if extraction_timeout_seconds is not None and extraction_timeout_seconds <= 0:
            raise ValueError("extraction_timeout_seconds must be > 0 or None")
        self.doc_repo = doc_repo
        self.vector_repo = vector_repo
        self.extraction_timeout_seconds = extraction_timeout_seconds

    async def extract(self, document_id: str) -> RawDocument | None:
        """Extract text for a stored RawDocument and persist extraction output."""
        document = await self.doc_repo.get(document_id)
        if document is None:
            logger.error("Document not found for extraction: %s", document_id)
            return None

        try:
            document.processing_status = ProcessingStatus.EXTRACTING
            await self.doc_repo.save(document)

            if not document.file_path:
                raise ValueError("Document has no file_path")

            path = Path(document.file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {document.file_path}")

            effective_type = self._resolve_document_type(document, path)
            extraction_task = asyncio.to_thread(self._extract_by_type, effective_type, path)
            if self.extraction_timeout_seconds is not None:
                try:
                    text, method, metadata = await asyncio.wait_for(
                        extraction_task,
                        timeout=self.extraction_timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"Text extraction exceeded {self.extraction_timeout_seconds:g}s timeout."
                    ) from exc
            else:
                text, method, metadata = await extraction_task

            await self.doc_repo.update_extracted_text(
                document_id=document.document_id,
                text=text,
                method=method,
                metadata=metadata,
            )
            updated = await self.doc_repo.get(document_id)
            if updated and self.vector_repo is not None and updated.extracted_text:
                await self._embed_document(updated)
                updated = await self.doc_repo.get(document_id)
            return updated

        except Exception as exc:  # noqa: BLE001
            document.processing_status = ProcessingStatus.ERROR
            document.processing_errors.append(str(exc))
            await self.doc_repo.save(document)
            logger.error("Text extraction failed: document_id=%s error=%s", document_id, exc)
            return document

    def _extract_by_type(self, document_type: DocumentType, path: Path) -> tuple[str, str, dict]:
        if document_type == DocumentType.PDF:
            return self._extract_pdf(path)
        if document_type == DocumentType.HTML:
            return self._extract_html(path)
        return self._extract_text(path)

    def _resolve_document_type(self, document: RawDocument, path: Path) -> DocumentType:
        if document.document_type != DocumentType.UNKNOWN.value:
            if isinstance(document.document_type, str):
                return DocumentType(document.document_type)
            return document.document_type

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return DocumentType.PDF
        if suffix in {".html", ".htm"}:
            return DocumentType.HTML
        if suffix in {".txt", ".md"}:
            return DocumentType.TEXT
        return DocumentType.UNKNOWN

    def _extract_pdf(self, path: Path) -> tuple[str, str, dict]:
        text_parts: list[str] = []
        table_count = 0
        page_count = 0

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[PAGE {index}]\n{page_text.strip()}")

                tables = page.extract_tables() or []
                for table in tables:
                    table_count += 1
                    rows: list[str] = []
                    for row in table or []:
                        safe_cells = [str(cell).strip() if cell is not None else "" for cell in row]
                        rows.append(" | ".join(safe_cells))
                    table_text = "\n".join(rows).strip()
                    if table_text:
                        text_parts.append(f"[TABLE]\n{table_text}\n[/TABLE]")

        extracted_text = "\n\n".join(part for part in text_parts if part).strip()
        metadata = {"page_count": page_count, "table_count": table_count}
        return extracted_text, "pdfplumber", metadata

    def _extract_html(self, path: Path) -> tuple[str, str, dict]:
        raw_html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(raw_html, "lxml")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
        extracted_text = "\n".join(lines)
        metadata = {"char_count": len(extracted_text)}
        return extracted_text, "beautifulsoup", metadata

    def _extract_text(self, path: Path) -> tuple[str, str, dict]:
        extracted_text = path.read_text(encoding="utf-8", errors="ignore").strip()
        metadata = {"char_count": len(extracted_text)}
        return extracted_text, "plain_text", metadata

    async def _embed_document(self, document: RawDocument) -> None:
        if self.vector_repo is None:
            return

        metadata = {
            "company_symbol": document.company_symbol,
            "trigger_id": document.trigger_id,
            "document_type": str(document.document_type),
            "source": document.source_url,
        }
        try:
            document.processing_status = ProcessingStatus.EMBEDDING
            await self.doc_repo.save(document)
            vector_id = await self.vector_repo.add_document(
                document_id=document.document_id,
                text=document.extracted_text or "",
                metadata=metadata,
            )
            document.vector_id = vector_id
            document.processing_status = ProcessingStatus.COMPLETE
            await self.doc_repo.save(document)
        except Exception as exc:  # noqa: BLE001
            document.processing_status = ProcessingStatus.ERROR
            document.processing_errors.append(f"Embedding error: {exc}")
            await self.doc_repo.save(document)
            logger.warning("Document embedding failed: document_id=%s error=%s", document.document_id, exc)
