"""API tests for shared notes endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.api.notes import router


class _FakeVectorRepo:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, object]] = []
        self.delete_calls: list[str] = []

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        self.add_calls.append({"document_id": document_id, "text": text, "metadata": metadata})
        return document_id

    async def delete_document(self, document_id: str) -> None:
        self.delete_calls.append(document_id)


def _build_app(*, with_vector_repo: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.mongo_db = AsyncMongoMockClient()["test_db"]
    if with_vector_repo:
        app.state.vector_repo = _FakeVectorRepo()
    return app


def test_create_and_list_notes_with_company_and_tag_filters() -> None:
    app = _build_app()
    client = TestClient(app)

    first = client.post(
        "/api/v1/notes",
        json={
            "company_symbol": "suzlon",
            "company_name": "Suzlon Energy",
            "content": "Management commentary implies stronger execution next quarter.",
            "tags": ["Thesis", "Risk", "risk"],
            "created_by": "analyst-1",
        },
    )
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["company_symbol"] == "SUZLON"
    assert first_payload["tags"] == ["thesis", "risk"]

    second = client.post(
        "/api/v1/notes",
        json={
            "company_symbol": "bhel",
            "content": "Need to monitor margin guidance.",
            "tags": ["monitor"],
        },
    )
    assert second.status_code == 201

    company_filtered = client.get("/api/v1/notes", params={"company": "suzlon"})
    assert company_filtered.status_code == 200
    company_payload = company_filtered.json()
    assert company_payload["total"] == 1
    assert company_payload["items"][0]["company_symbol"] == "SUZLON"

    tag_filtered = client.get("/api/v1/notes", params={"tag": "monitor"})
    assert tag_filtered.status_code == 200
    tag_payload = tag_filtered.json()
    assert tag_payload["total"] == 1
    assert tag_payload["items"][0]["company_symbol"] == "BHEL"


def test_update_note_reindexes_content_when_vector_repo_is_available() -> None:
    app = _build_app(with_vector_repo=True)
    client = TestClient(app)

    created = client.post(
        "/api/v1/notes",
        json={
            "company_symbol": "inoxwind",
            "content": "Initial note",
            "tags": ["watch"],
        },
    )
    assert created.status_code == 201
    note_id = created.json()["note_id"]

    updated = client.put(
        f"/api/v1/notes/{note_id}",
        json={
            "content": "Updated investment thesis",
            "tags": ["thesis", "watch"],
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["content"] == "Updated investment thesis"
    assert payload["tags"] == ["thesis", "watch"]

    vector_repo = app.state.vector_repo
    assert len(vector_repo.add_calls) == 2
    assert len(vector_repo.delete_calls) == 2
    assert vector_repo.add_calls[-1]["document_id"] == note_id


def test_delete_note_removes_note_and_index_entry() -> None:
    app = _build_app(with_vector_repo=True)
    client = TestClient(app)

    created = client.post(
        "/api/v1/notes",
        json={
            "company_symbol": "ABB",
            "content": "Delete me",
        },
    )
    assert created.status_code == 201
    note_id = created.json()["note_id"]

    deleted = client.delete(f"/api/v1/notes/{note_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"note_id": note_id, "deleted": True}

    missing = client.get(f"/api/v1/notes/{note_id}")
    assert missing.status_code == 404

    vector_repo = app.state.vector_repo
    assert note_id in vector_repo.delete_calls
