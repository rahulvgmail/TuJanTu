"""Tests for document download and metadata handling."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.models.document import DocumentType, RawDocument
from src.pipeline.layer1_triggers.document_fetcher import DocumentFetcher


class InMemoryDocumentRepo:
    """Minimal document repository for fetcher tests."""

    def __init__(self) -> None:
        self.items: dict[str, RawDocument] = {}

    async def save(self, document: RawDocument) -> str:
        self.items[document.document_id] = document
        return document.document_id

    async def get(self, document_id: str) -> RawDocument | None:
        return self.items.get(document_id)

    async def get_by_trigger(self, trigger_id: str) -> list[RawDocument]:
        return [doc for doc in self.items.values() if doc.trigger_id == trigger_id]

    async def update_extracted_text(self, document_id: str, text: str, method: str, metadata: dict) -> None:
        document = self.items[document_id]
        document.extracted_text = text
        document.extraction_method = method
        document.extraction_metadata = metadata


@pytest.mark.asyncio
async def test_fetch_pdf_success(tmp_path: Path) -> None:
    url = "https://example.test/announcement.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        return httpx.Response(
            200,
            content=b"%PDF-1.7 sample content",
            headers={"content-type": "application/pdf"},
        )

    repo = InMemoryDocumentRepo()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = DocumentFetcher(
            doc_repo=repo,
            download_dir=str(tmp_path),
            session=session,
            max_size_mb=1,
        )
        document = await fetcher.fetch(trigger_id="trigger-1", url=url, company_symbol="INOXWIND")

    assert document.processing_status == "downloaded"
    assert document.document_type == DocumentType.PDF.value
    assert document.file_size_bytes == len(b"%PDF-1.7 sample content")
    assert document.file_path is not None
    assert Path(document.file_path).exists()
    assert repo.items[document.document_id].processing_status == "downloaded"


@pytest.mark.asyncio
async def test_fetch_html_success(tmp_path: Path) -> None:
    url = "https://example.test/announcement.html"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>ok</body></html>", headers={"content-type": "text/html"})

    repo = InMemoryDocumentRepo()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = DocumentFetcher(doc_repo=repo, download_dir=str(tmp_path), session=session, max_size_mb=1)
        document = await fetcher.fetch(trigger_id="trigger-2", url=url)

    assert document.processing_status == "downloaded"
    assert document.document_type == DocumentType.HTML.value
    assert document.file_path is not None
    assert Path(document.file_path).suffix == ".html"


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_files(tmp_path: Path) -> None:
    url = "https://example.test/large.pdf"
    payload = b"x" * (2 * 1024 * 1024)  # 2MB

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/pdf"})

    repo = InMemoryDocumentRepo()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = DocumentFetcher(doc_repo=repo, download_dir=str(tmp_path), session=session, max_size_mb=1)
        document = await fetcher.fetch(trigger_id="trigger-3", url=url)

    assert document.processing_status == "error"
    assert document.file_path is None
    assert document.processing_errors
    assert "File too large" in document.processing_errors[0]


@pytest.mark.asyncio
async def test_fetch_handles_http_error(tmp_path: Path) -> None:
    url = "https://example.test/missing.pdf"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    repo = InMemoryDocumentRepo()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        fetcher = DocumentFetcher(doc_repo=repo, download_dir=str(tmp_path), session=session, max_size_mb=1)
        document = await fetcher.fetch(trigger_id="trigger-4", url=url)

    assert document.processing_status == "error"
    assert document.file_path is None
    assert document.processing_errors

