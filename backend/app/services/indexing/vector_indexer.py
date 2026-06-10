from __future__ import annotations

from math import sqrt
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Document, DocumentChunk, KnowledgeBase, User

INDEXED_DOCUMENT_STATUSES = {"indexed", "need_review"}


class VectorIndexer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._memory: dict[str, tuple[list[float], dict]] = {}
        self._qdrant_available: bool | None = None

    def upsert(self, vectors: list[list[float]], chunks: list[DocumentChunk]) -> None:
        payloads = []
        for vector, chunk in zip(vectors, chunks, strict=False):
            point_id = chunk.qdrant_point_id or _stable_point_id(chunk.id)
            chunk.qdrant_point_id = point_id
            chunk.embedding_json = [float(value) for value in vector]
            payload = self._payload_for_chunk(chunk)
            payloads.append(payload)
            self._memory[point_id] = (chunk.embedding_json, payload)
        self._try_qdrant_upsert(vectors, chunks, payloads)

    def search(
        self,
        query_vector: list[float],
        db: Session,
        top_k: int = 30,
        kb_id: str | None = None,
        document_ids: list[str] | None = None,
        current_user: User | None = None,
        allowed_kb_ids: list[str] | None = None,
    ) -> list[dict]:
        if allowed_kb_ids == []:
            return []
        if document_ids is not None and not document_ids:
            return []

        qdrant_results = self._try_qdrant_search(query_vector, top_k, kb_id, allowed_kb_ids, document_ids)
        if qdrant_results:
            return self._filter_results(db, qdrant_results, top_k, kb_id, document_ids, current_user, allowed_kb_ids)

        memory_results = self._search_memory(query_vector, db, top_k, kb_id, document_ids, current_user, allowed_kb_ids)
        if memory_results:
            return memory_results

        return self._search_persisted_vectors(
            query_vector,
            db,
            top_k,
            kb_id,
            document_ids,
            current_user,
            allowed_kb_ids,
        )

    def delete_document(self, document_id: str) -> None:
        for point_id, (_, payload) in list(self._memory.items()):
            if payload.get("document_id") == document_id:
                self._memory.pop(point_id, None)
        self._try_qdrant_delete(document_id=document_id)

    def delete_kb(self, kb_id: str) -> None:
        for point_id, (_, payload) in list(self._memory.items()):
            if payload.get("kb_id") == kb_id:
                self._memory.pop(point_id, None)
        self._try_qdrant_delete(kb_id=kb_id)

    def status(self) -> dict:
        return {
            "backend": "qdrant+db-fallback",
            "qdrant_url": self.settings.qdrant_url,
            "collection": self.settings.qdrant_collection,
            "qdrant_available": bool(self._qdrant_available),
            "memory_points": len(self._memory),
        }

    def _payload_for_chunk(self, chunk: DocumentChunk) -> dict:
        document = getattr(chunk, "document", None)
        metadata = chunk.metadata_json or {}
        kb_id = chunk.kb_id or (document.kb_id if document else None)
        visibility = document.visibility if document else metadata.get("visibility")
        owner_user_id = document.uploaded_by if document else metadata.get("owner_user_id")
        return {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "kb_id": kb_id,
            "visibility": visibility,
            "owner_user_id": owner_user_id,
            "chunk_type": chunk.chunk_type or metadata.get("chunk_type") or "paragraph",
            "page_number": metadata.get("page_number"),
            "sheet_name": metadata.get("sheet_name"),
            "heading_path": metadata.get("heading_path"),
            "content_hash": chunk.content_hash or metadata.get("content_hash", ""),
            "embed_model": self.settings.embed_model,
        }

    def _search_memory(
        self,
        query_vector: list[float],
        db: Session,
        top_k: int,
        kb_id: str | None,
        document_ids: list[str] | None,
        current_user: User | None,
        allowed_kb_ids: list[str] | None,
    ) -> list[dict]:
        allowed_chunk_ids = set(
            self._visible_chunk_query(
                db,
                kb_id=kb_id,
                document_ids=document_ids,
                current_user=current_user,
                allowed_kb_ids=allowed_kb_ids,
            )
            .with_entities(DocumentChunk.id)
            .all()
        )
        allowed_chunk_ids = {item[0] for item in allowed_chunk_ids}
        results = []
        for point_id, (vector, payload) in self._memory.items():
            if payload["chunk_id"] not in allowed_chunk_ids:
                continue
            results.append(
                {
                    "chunk_id": payload["chunk_id"],
                    "document_id": payload["document_id"],
                    "score": _cosine(query_vector, vector),
                    "raw_score": _cosine(query_vector, vector),
                    "point_id": point_id,
                    "source": "vector",
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]

    def _search_persisted_vectors(
        self,
        query_vector: list[float],
        db: Session,
        top_k: int,
        kb_id: str | None,
        document_ids: list[str] | None,
        current_user: User | None,
        allowed_kb_ids: list[str] | None,
    ) -> list[dict]:
        chunks = (
            self._visible_chunk_query(
                db,
                kb_id=kb_id,
                document_ids=document_ids,
                current_user=current_user,
                allowed_kb_ids=allowed_kb_ids,
            )
            .filter(DocumentChunk.embedding_json.is_not(None))
            .all()
        )
        results = []
        for chunk in chunks:
            vector = chunk.embedding_json or []
            if not vector:
                continue
            score = _cosine(query_vector, vector)
            results.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "score": score,
                    "raw_score": score,
                    "point_id": chunk.qdrant_point_id,
                    "source": "vector",
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]

    def _filter_results(
        self,
        db: Session,
        results: list[dict],
        top_k: int,
        kb_id: str | None,
        document_ids: list[str] | None,
        current_user: User | None,
        allowed_kb_ids: list[str] | None,
    ) -> list[dict]:
        visible_ids = {
            item[0]
            for item in self._visible_chunk_query(
                db,
                kb_id=kb_id,
                document_ids=document_ids,
                current_user=current_user,
                allowed_kb_ids=allowed_kb_ids,
            )
            .with_entities(DocumentChunk.id)
            .all()
        }
        return [item for item in results if item["chunk_id"] in visible_ids][:top_k]

    def _visible_chunk_query(
        self,
        db: Session,
        kb_id: str | None,
        document_ids: list[str] | None,
        current_user: User | None,
        allowed_kb_ids: list[str] | None,
    ):
        query = db.query(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
        query = query.filter(Document.status.in_(INDEXED_DOCUMENT_STATUSES))
        if kb_id:
            query = query.filter(Document.kb_id == kb_id)
        elif allowed_kb_ids is not None:
            query = query.filter(Document.kb_id.in_(allowed_kb_ids))
        if document_ids is not None:
            if not document_ids:
                return query.filter(False)
            query = query.filter(Document.id.in_(document_ids))
        elif current_user and current_user.role != "system_admin":
            query = query.outerjoin(KnowledgeBase, KnowledgeBase.id == Document.kb_id).filter(
                or_(
                    KnowledgeBase.visibility == "shared",
                    (KnowledgeBase.visibility == "private") & (KnowledgeBase.created_by == current_user.id),
                    Document.uploaded_by == current_user.id,
                )
            )
        return query

    def _try_qdrant_upsert(self, vectors: list[list[float]], chunks: list[DocumentChunk], payloads: list[dict]) -> None:
        if not vectors:
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models

            client = QdrantClient(url=self.settings.qdrant_url, timeout=3, check_compatibility=False)
            self._ensure_qdrant_collection(client, len(vectors[0]), models)
            points = [
                models.PointStruct(
                    id=chunk.qdrant_point_id or _stable_point_id(chunk.id),
                    vector=[float(value) for value in vector],
                    payload=payload,
                )
                for vector, chunk, payload in zip(vectors, chunks, payloads, strict=False)
            ]
            client.upsert(collection_name=self.settings.qdrant_collection, points=points)
            self._qdrant_available = True
        except Exception:
            self._qdrant_available = False

    def _try_qdrant_search(
        self,
        query_vector: list[float],
        top_k: int,
        kb_id: str | None,
        allowed_kb_ids: list[str] | None,
        document_ids: list[str] | None,
    ) -> list[dict]:
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=self.settings.qdrant_url, timeout=3, check_compatibility=False)
            query_filter = self._qdrant_filter(kb_id, allowed_kb_ids, document_ids)
            points = client.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=[float(value) for value in query_vector],
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            self._qdrant_available = True
            return [
                {
                    "chunk_id": point.payload.get("chunk_id"),
                    "document_id": point.payload.get("document_id"),
                    "score": float(point.score),
                    "raw_score": float(point.score),
                    "point_id": str(point.id),
                    "source": "vector",
                }
                for point in points
                if point.payload and point.payload.get("chunk_id")
            ]
        except Exception:
            self._qdrant_available = False
            return []

    def _qdrant_filter(self, kb_id: str | None, allowed_kb_ids: list[str] | None, document_ids: list[str] | None):
        try:
            from qdrant_client.http import models

            conditions = []
            if kb_id:
                conditions.append(models.FieldCondition(key="kb_id", match=models.MatchValue(value=kb_id)))
            elif allowed_kb_ids:
                conditions.append(models.FieldCondition(key="kb_id", match=models.MatchAny(any=allowed_kb_ids)))
            if document_ids is not None:
                if not document_ids:
                    conditions.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=["__none__"])))
                else:
                    conditions.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids)))
            if conditions:
                return models.Filter(must=conditions)
        except Exception:
            return None
        return None

    def _ensure_qdrant_collection(self, client, vector_size: int, models) -> None:
        existing = {collection.name for collection in client.get_collections().collections}
        if self.settings.qdrant_collection in existing:
            return
        client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    def _try_qdrant_delete(self, document_id: str | None = None, kb_id: str | None = None) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models

            conditions = []
            if document_id:
                conditions.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)))
            if kb_id:
                conditions.append(models.FieldCondition(key="kb_id", match=models.MatchValue(value=kb_id)))
            if not conditions:
                return
            QdrantClient(url=self.settings.qdrant_url, timeout=3, check_compatibility=False).delete(
                collection_name=self.settings.qdrant_collection,
                points_selector=models.FilterSelector(filter=models.Filter(must=conditions)),
            )
            self._qdrant_available = True
        except Exception:
            self._qdrant_available = False


def _stable_point_id(chunk_id: str) -> str:
    try:
        return str(UUID(chunk_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, chunk_id))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sqrt(sum(x * x for x in a)) or 1.0
    norm_b = sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


vector_indexer = VectorIndexer()
