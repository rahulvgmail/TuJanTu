"""Tests for text extraction across supported document types."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.models.document import DocumentType, ProcessingStatus, RawDocument
from src.pipeline.layer1_triggers.text_extractor import TextExtractor


class InMemoryDocumentRepo:
    """Minimal document repository used by extractor tests."""

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
        document.processing_status = ProcessingStatus.EXTRACTED
        self.items[document_id] = document


class InMemoryVectorRepo:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict[str, Any]] = []

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        if self.should_fail:
            raise RuntimeError("vector store unavailable")
        self.calls.append({"document_id": document_id, "text": text, "metadata": metadata})
        return f"vec-{document_id}"

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        del query, n_results, where
        return []

    async def delete_document(self, document_id: str) -> None:
        del document_id


class _FakePDFPage:
    def __init__(self, text: str, tables: list[list[list[Any]]]):
        self._text = text
        self._tables = tables

    def extract_text(self) -> str:
        return self._text

    def extract_tables(self):
        return self._tables


class _FakePDF:
    def __init__(self, pages: list[_FakePDFPage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_extract_pdf_with_table_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    repo = InMemoryDocumentRepo()
    document = RawDocument(
        trigger_id="trigger-1",
        source_url="https://example.test/sample.pdf",
        file_path=str(file_path),
        document_type=DocumentType.PDF,
    )
    await repo.save(document)

    fake_pdf = _FakePDF(
        pages=[
            _FakePDFPage(
                text="Revenue increased 20%",
                tables=[[["Metric", "Value"], ["Revenue", "1200"]]],
            )
        ]
    )
    monkeypatch.setattr(
        "src.pipeline.layer1_triggers.text_extractor.pdfplumber.open",
        lambda _: fake_pdf,
    )

    extractor = TextExtractor(repo)
    extracted = await extractor.extract(document.document_id)

    assert extracted is not None
    assert extracted.processing_status == ProcessingStatus.EXTRACTED.value
    assert extracted.extraction_method == "pdfplumber"
    assert "[TABLE]" in (extracted.extracted_text or "")
    assert extracted.extraction_metadata["page_count"] == 1
    assert extracted.extraction_metadata["table_count"] == 1


@pytest.mark.asyncio
async def test_extract_html_removes_script_and_footer(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.html"
    file_path.write_text(
        """
<html>
  <body>
    <nav>navigation</nav>
    <h1>Order Win</h1>
    <p>Company won a major order.</p>
    <script>alert("x")</script>
    <footer>footer content</footer>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    repo = InMemoryDocumentRepo()
    document = RawDocument(
        trigger_id="trigger-2",
        source_url="https://example.test/sample.html",
        file_path=str(file_path),
        document_type=DocumentType.HTML,
    )
    await repo.save(document)

    extractor = TextExtractor(repo)
    extracted = await extractor.extract(document.document_id)

    assert extracted is not None
    assert extracted.processing_status == ProcessingStatus.EXTRACTED.value
    assert extracted.extraction_method == "beautifulsoup"
    text = extracted.extracted_text or ""
    assert "Order Win" in text
    assert "major order" in text
    assert "navigation" not in text
    assert "footer content" not in text


@pytest.mark.asyncio
async def test_extract_missing_file_sets_error() -> None:
    repo = InMemoryDocumentRepo()
    document = RawDocument(
        trigger_id="trigger-3",
        source_url="https://example.test/missing.pdf",
        file_path="/tmp/definitely-missing-file-12345.pdf",
        document_type=DocumentType.PDF,
    )
    await repo.save(document)

    extractor = TextExtractor(repo)
    result = await extractor.extract(document.document_id)

    assert result is not None
    assert result.processing_status == ProcessingStatus.ERROR.value
    assert result.processing_errors


@pytest.mark.asyncio
async def test_extract_embeds_text_and_marks_document_complete(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Quarterly results and order book growth", encoding="utf-8")

    repo = InMemoryDocumentRepo()
    vector_repo = InMemoryVectorRepo()
    document = RawDocument(
        trigger_id="trigger-4",
        source_url="https://example.test/sample.txt",
        file_path=str(file_path),
        document_type=DocumentType.TEXT,
        company_symbol="INOXWIND",
    )
    await repo.save(document)

    extractor = TextExtractor(repo, vector_repo=vector_repo)
    extracted = await extractor.extract(document.document_id)

    assert extracted is not None
    assert extracted.processing_status == ProcessingStatus.COMPLETE.value
    assert extracted.vector_id == f"vec-{document.document_id}"
    assert extracted.extracted_text is not None
    assert len(vector_repo.calls) == 1
    assert vector_repo.calls[0]["metadata"]["company_symbol"] == "INOXWIND"
    assert vector_repo.calls[0]["metadata"]["trigger_id"] == "trigger-4"


@pytest.mark.asyncio
async def test_extract_handles_embedding_failure_without_losing_text(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Material update for investors", encoding="utf-8")

    repo = InMemoryDocumentRepo()
    vector_repo = InMemoryVectorRepo(should_fail=True)
    document = RawDocument(
        trigger_id="trigger-5",
        source_url="https://example.test/sample.txt",
        file_path=str(file_path),
        document_type=DocumentType.TEXT,
    )
    await repo.save(document)

    extractor = TextExtractor(repo, vector_repo=vector_repo)
    extracted = await extractor.extract(document.document_id)

    assert extracted is not None
    assert extracted.extracted_text == "Material update for investors"
    assert extracted.processing_status == ProcessingStatus.ERROR.value
    assert any("Embedding error:" in message for message in extracted.processing_errors)
