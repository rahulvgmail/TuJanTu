"""Tests for ChromaVectorRepository behavior."""

from __future__ import annotations

from math import sqrt
from typing import Any

import pytest

from src.repositories.vector import ChromaVectorRepository


class _FakeEmbedder:
    def encode(self, text: str) -> list[float]:
        alpha_sum = sum(ord(char) for char in text.lower() if char.isalpha())
        return [float(alpha_sum), float(len(text))]


class _FakeCollection:
    def __init__(self):
        self.store: dict[str, dict[str, Any]] = {}

    def add(self, ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]) -> None:
        for index, item_id in enumerate(ids):
            self.store[item_id] = {
                "embedding": embeddings[index],
                "document": documents[index],
                "metadata": metadatas[index],
            }

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict | None = None,
        include: list[str] | None = None,
    ) -> dict[str, list[list[Any]]]:
        del include
        query_vector = query_embeddings[0]
        candidates = []
        for item_id, payload in self.store.items():
            metadata = payload["metadata"]
            if where and any(metadata.get(key) != value for key, value in where.items()):
                continue
            embedding = payload["embedding"]
            distance = sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(query_vector, embedding)))
            candidates.append((distance, item_id, payload))

        candidates.sort(key=lambda row: row[0])
        top = candidates[:n_results]
        return {
            "ids": [[row[1] for row in top]],
            "documents": [[row[2]["document"] for row in top]],
            "metadatas": [[row[2]["metadata"] for row in top]],
            "distances": [[row[0] for row in top]],
        }

    def delete(self, ids: list[str] | None = None, where: dict | None = None) -> None:
        if ids is not None:
            for item_id in ids:
                self.store.pop(item_id, None)
            return

        if where is None:
            return

        to_delete = [
            item_id
            for item_id, payload in self.store.items()
            if all(payload["metadata"].get(key) == value for key, value in where.items())
        ]
        for item_id in to_delete:
            self.store.pop(item_id, None)

    def get(self, where: dict | None = None, include: list[str] | None = None) -> dict[str, list[str]]:
        del include
        if where is None:
            return {"ids": list(self.store)}

        filtered = [
            item_id
            for item_id, payload in self.store.items()
            if all(payload["metadata"].get(key) == value for key, value in where.items())
        ]
        return {"ids": filtered}


class _FakeClient:
    def __init__(self):
        self.collections: dict[str, _FakeCollection] = {}

    def get_or_create_collection(self, name: str, metadata: dict | None = None) -> _FakeCollection:
        del metadata
        if name not in self.collections:
            self.collections[name] = _FakeCollection()
        return self.collections[name]


@pytest.fixture
def fake_client() -> _FakeClient:
    return _FakeClient()


def _build_repo(fake_client: _FakeClient) -> ChromaVectorRepository:
    return ChromaVectorRepository(
        persist_dir="unused",
        client=fake_client,
        embedder=_FakeEmbedder(),
    )


@pytest.mark.asyncio
async def test_vector_add_and_search_returns_result(fake_client: _FakeClient) -> None:
    repo = _build_repo(fake_client)
    await repo.add_document(
        document_id="doc-1",
        text="Inox Wind announced strong quarterly results with rising revenue.",
        metadata={"company_symbol": "INOXWIND"},
    )

    results = await repo.search("quarterly results revenue", n_results=3)

    assert len(results) == 1
    assert results[0]["id"] == "doc-1_chunk_0"
    assert results[0]["metadata"]["company_symbol"] == "INOXWIND"


@pytest.mark.asyncio
async def test_vector_search_honors_metadata_filter(fake_client: _FakeClient) -> None:
    repo = _build_repo(fake_client)
    await repo.add_document(
        document_id="inox-doc",
        text="Inox Wind order wins and margin expansion.",
        metadata={"company_symbol": "INOXWIND"},
    )
    await repo.add_document(
        document_id="bhel-doc",
        text="BHEL signs thermal project contract.",
        metadata={"company_symbol": "BHEL"},
    )

    results = await repo.search("contract wins", n_results=5, where={"company_symbol": "BHEL"})

    assert len(results) == 1
    assert results[0]["metadata"]["company_symbol"] == "BHEL"
    assert results[0]["metadata"]["document_id"] == "bhel-doc"


@pytest.mark.asyncio
async def test_vector_add_long_document_creates_multiple_chunks(fake_client: _FakeClient) -> None:
    repo = _build_repo(fake_client)
    long_text = "A" * 10500

    await repo.add_document(
        document_id="long-doc",
        text=long_text,
        metadata={"company_symbol": "INOXWIND"},
    )

    chunk_ids = [item_id for item_id in fake_client.collections["documents"].store if item_id.startswith("long-doc_")]
    assert len(chunk_ids) >= 10


@pytest.mark.asyncio
async def test_vector_data_is_available_after_repository_reinit(fake_client: _FakeClient) -> None:
    repo_one = _build_repo(fake_client)
    await repo_one.add_document(
        document_id="doc-persist",
        text="Persistent vector data for Inox Wind.",
        metadata={"company_symbol": "INOXWIND"},
    )

    repo_two = _build_repo(fake_client)
    results = await repo_two.search("Inox Wind data", n_results=2)

    assert len(results) == 1
    assert results[0]["metadata"]["document_id"] == "doc-persist"


@pytest.mark.asyncio
async def test_vector_delete_document_removes_all_chunks(fake_client: _FakeClient) -> None:
    repo = _build_repo(fake_client)
    await repo.add_document(
        document_id="delete-me",
        text="B" * 2500,
        metadata={"company_symbol": "SIEMENS"},
    )
    before = await repo.search("BBBB", n_results=10, where={"document_id": "delete-me"})
    assert before

    await repo.delete_document("delete-me")
    after = await repo.search("BBBB", n_results=10, where={"document_id": "delete-me"})

    assert after == []


def test_vector_chunk_configuration_validation(fake_client: _FakeClient) -> None:
    with pytest.raises(ValueError):
        ChromaVectorRepository(
            persist_dir="unused",
            client=fake_client,
            embedder=_FakeEmbedder(),
            chunk_size=1000,
            chunk_overlap=1000,
        )
