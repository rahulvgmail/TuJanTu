"""ChromaDB-backed vector repository for semantic search."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


class ChromaVectorRepository:
    """Store and query document chunks using ChromaDB embeddings."""

    def __init__(
        self,
        persist_dir: str | Path,
        embedding_model: str = "all-MiniLM-L6-v2",
        *,
        collection_name: str = "documents",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        client: Any | None = None,
        collection: Any | None = None,
        embedder: Any | None = None,
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.persist_dir = Path(persist_dir)
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._client = client or self._create_client(self.persist_dir)
        self._collection = collection or self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = embedder or self._create_embedder(embedding_model)

    @staticmethod
    def _create_client(persist_dir: Path) -> Any:
        persist_dir.mkdir(parents=True, exist_ok=True)
        try:
            import chromadb
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("ChromaDB is unavailable in this runtime") from exc
        return chromadb.PersistentClient(path=str(persist_dir))

    @staticmethod
    def _create_embedder(embedding_model: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("sentence-transformers is unavailable in this runtime") from exc
        return SentenceTransformer(embedding_model)

    async def add_document(self, document_id: str, text: str, metadata: dict) -> str:
        chunks = self._chunk_text(text)
        clean_metadata = self._sanitize_metadata(metadata)
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{chunk_index}"
            chunk_metadata = dict(clean_metadata)
            chunk_metadata["document_id"] = document_id
            chunk_metadata["chunk_index"] = chunk_index
            self._collection.add(
                ids=[chunk_id],
                embeddings=[self._encode(chunk)],
                documents=[chunk],
                metadatas=[chunk_metadata],
            )
        return document_id

    async def search(self, query: str, n_results: int = 5, where: dict | None = None) -> list[dict]:
        where_clause = where or None
        results = self._collection.query(
            query_embeddings=[self._encode(query)],
            n_results=n_results,
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])
        documents = results.get("documents", [[]])
        metadatas = results.get("metadatas", [[]])
        distances = results.get("distances", [[]])
        if not ids or not ids[0]:
            return []

        rows: list[dict] = []
        for index, chunk_id in enumerate(ids[0]):
            rows.append(
                {
                    "id": chunk_id,
                    "text": documents[0][index],
                    "metadata": metadatas[0][index],
                    "distance": distances[0][index],
                }
            )
        return rows

    async def delete_document(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
            return
        except Exception:  # noqa: BLE001
            pass

        matches = self._collection.get(where={"document_id": document_id}, include=[])
        ids = matches.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)

    def _encode(self, text: str) -> list[float]:
        raw_vector = self._embedder.encode(text)
        vector = raw_vector.tolist() if hasattr(raw_vector, "tolist") else raw_vector
        return [float(value) for value in vector]

    def _chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        chunks: list[str] = []
        step = self.chunk_size - self.chunk_overlap
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += step

        return chunks

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        clean: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if value is None:
                continue

            if isinstance(value, bool | int | float | str):
                clean[str(key)] = value
                continue

            if hasattr(value, "value"):
                clean[str(key)] = str(getattr(value, "value"))
                continue

            if isinstance(value, datetime | date):
                clean[str(key)] = value.isoformat()
                continue

            clean[str(key)] = str(value)

        return clean
