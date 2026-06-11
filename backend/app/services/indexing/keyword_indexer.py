from __future__ import annotations

import re

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, KnowledgeBase, User
from app.services.indexing.vector_indexer import INDEXED_DOCUMENT_STATUSES

FTS_TABLE = "document_chunk_fts"

DOMAIN_KEYPHRASES = (
    "电子招标投标",
    "政府采购",
    "需求标准",
    "数据检索",
    "增强功能",
    "中文检索",
    "中国纪年历法",
    "操作系统",
    "系统引导",
    "引导模式",
    "引导修复",
    "固件规范",
    "规范固件",
    "UEFI",
    "UEFI2.0",
    "财政拨款预算",
    "财政拨款收入",
    "财政拨款",
    "预算执行",
    "预算单位",
    "省级人民政府",
    "三公经费",
    "三公",
    "决算支出",
    "预算数",
    "决算数",
    "中小企业",
    "小微企业",
    "合同金额",
    "政府采购支出",
    "审计署",
    "特派员办事处",
    "工程项目",
    "项目招标",
    "暗箱操作",
    "商业贿赂",
    "投标文件",
    "拒收",
    "提示",
    "数据库",
    "经费",
    "占比",
)

QUESTION_STOPWORDS = (
    "是多少",
    "是什么",
    "有哪些",
    "哪些",
    "什么",
    "怎么",
    "如何",
    "是否",
    "包括",
    "中的",
    "中",
    "和",
    "及",
    "以及",
)


class KeywordIndexer:
    def ensure_schema(self, db: Session) -> None:
        if db.bind and db.bind.dialect.name != "sqlite":
            return
        try:
            db.execute(
                text(
                    f"""
                    create virtual table if not exists {FTS_TABLE}
                    using fts5(chunk_id unindexed, document_id unindexed, text, tokenize='trigram')
                    """
                )
            )
        except Exception:
            db.rollback()
            db.execute(
                text(
                    f"""
                    create virtual table if not exists {FTS_TABLE}
                    using fts5(chunk_id unindexed, document_id unindexed, text)
                    """
                )
            )

    def upsert(self, db: Session, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        if db.bind and db.bind.dialect.name != "sqlite":
            return
        self.ensure_schema(db)
        document_ids = {chunk.document_id for chunk in chunks}
        for document_id in document_ids:
            db.execute(text(f"delete from {FTS_TABLE} where document_id = :document_id"), {"document_id": document_id})
        for chunk in chunks:
            db.execute(
                text(f"insert into {FTS_TABLE}(chunk_id, document_id, text) values (:chunk_id, :document_id, :text)"),
                {"chunk_id": chunk.id, "document_id": chunk.document_id, "text": chunk.text},
            )

    def delete_document(self, db: Session, document_id: str) -> None:
        if db.bind and db.bind.dialect.name != "sqlite":
            return
        self.ensure_schema(db)
        db.execute(text(f"delete from {FTS_TABLE} where document_id = :document_id"), {"document_id": document_id})

    def delete_kb(self, db: Session, kb_id: str) -> None:
        document_ids = [item[0] for item in db.query(Document.id).filter(Document.kb_id == kb_id).all()]
        for document_id in document_ids:
            self.delete_document(db, document_id)

    def search(
        self,
        db: Session,
        query: str,
        kb_id: str | None = None,
        document_ids: list[str] | None = None,
        current_user: User | None = None,
        allowed_kb_ids: list[str] | None = None,
        top_k: int = 30,
    ) -> list[dict]:
        if allowed_kb_ids == []:
            return []
        if document_ids is not None and not document_ids:
            return []
        visible_ids = self._visible_chunk_ids(db, kb_id, document_ids, current_user, allowed_kb_ids)
        if not visible_ids:
            return []

        results = self._fts_search(db, query, visible_ids, top_k)
        if len(results) < top_k:
            seen = {item["chunk_id"] for item in results}
            results.extend(
                item
                for item in self._contains_search(db, query, visible_ids, top_k)
                if item["chunk_id"] not in seen
            )
        return results[:top_k]

    def _visible_chunk_ids(
        self,
        db: Session,
        kb_id: str | None,
        document_ids: list[str] | None,
        current_user: User | None,
        allowed_kb_ids: list[str] | None,
    ) -> set[str]:
        query = db.query(DocumentChunk.id).join(Document, Document.id == DocumentChunk.document_id)
        query = query.filter(Document.status.in_(INDEXED_DOCUMENT_STATUSES))
        if kb_id:
            query = query.filter(Document.kb_id == kb_id)
        elif allowed_kb_ids is not None:
            query = query.filter(Document.kb_id.in_(allowed_kb_ids))
        if document_ids is not None:
            if not document_ids:
                return set()
            query = query.filter(Document.id.in_(document_ids))
        elif current_user and current_user.role != "system_admin":
            query = query.outerjoin(KnowledgeBase, KnowledgeBase.id == Document.kb_id).filter(
                or_(
                    KnowledgeBase.visibility == "shared",
                    (KnowledgeBase.visibility == "private") & (KnowledgeBase.created_by == current_user.id),
                    Document.uploaded_by == current_user.id,
                )
            )
        return {item[0] for item in query.all()}

    def _fts_search(self, db: Session, query: str, visible_ids: set[str], top_k: int) -> list[dict]:
        if db.bind and db.bind.dialect.name != "sqlite":
            return []
        self.ensure_schema(db)
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        try:
            rows = db.execute(
                text(
                    f"""
                    select chunk_id, document_id, bm25({FTS_TABLE}) as rank
                    from {FTS_TABLE}
                    where {FTS_TABLE} match :query
                    order by rank
                    limit :limit
                    """
                ),
                {"query": fts_query, "limit": max(top_k * 4, 20)},
            ).all()
        except Exception:
            db.rollback()
            return []
        results = []
        for chunk_id, document_id, rank in rows:
            if chunk_id not in visible_ids:
                continue
            score = 1.0 / (1.0 + abs(float(rank or 0)))
            results.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "score": score,
                    "raw_score": float(rank or 0),
                    "source": "keyword",
                }
            )
            if len(results) >= top_k:
                break
        return results

    def _contains_search(self, db: Session, query: str, visible_ids: set[str], top_k: int) -> list[dict]:
        terms = _terms(query)
        if not terms:
            return []
        db_query = db.query(DocumentChunk).filter(DocumentChunk.id.in_(visible_ids))
        db_query = db_query.filter(or_(*[DocumentChunk.text.contains(term) for term in terms]))
        chunks = db_query.limit(max(top_k * 2, 20)).all()
        results = []
        for chunk in chunks:
            score = sum(chunk.text.count(term) for term in terms if term)
            results.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "score": float(score or 1),
                    "raw_score": float(score or 1),
                    "source": "keyword",
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]


def keyword_search(
    db: Session,
    query: str,
    kb_id: str | None = None,
    document_ids: list[str] | None = None,
    current_user: User | None = None,
    allowed_kb_ids: list[str] | None = None,
    top_k: int = 30,
) -> list[dict]:
    return keyword_indexer.search(
        db,
        query,
        kb_id=kb_id,
        document_ids=document_ids,
        current_user=current_user,
        allowed_kb_ids=allowed_kb_ids,
        top_k=top_k,
    )


def _terms(query: str) -> list[str]:
    normalized = re.sub(r"[，。！？；、,.!?;:：()\[\]【】\"'“”\s]+", " ", query.strip())
    candidates: list[str] = []
    for raw in normalized.split(" "):
        candidates.extend(_searchable_terms_from_token(raw))
    stripped_query = query.strip()
    if stripped_query and not any(stopword in stripped_query for stopword in QUESTION_STOPWORDS):
        candidates.append(stripped_query)
    return list(dict.fromkeys(term for term in candidates if term))


def _searchable_terms_from_token(token: str) -> list[str]:
    terms = []
    token = token.strip()
    if not token:
        return terms
    cleaned = token
    for stopword in QUESTION_STOPWORDS:
        cleaned = cleaned.replace(stopword, " ")
    for value in re.findall(r"[A-Za-z]+(?:[A-Za-z0-9_-]+)?|\d+(?:\.\d+)?%?", token):
        terms.append(value)
    for phrase in DOMAIN_KEYPHRASES:
        if phrase in token:
            terms.append(phrase)
    for part in cleaned.split():
        if 2 <= len(part) <= 12:
            terms.append(part)
    return terms


def _fts_query(query: str) -> str:
    terms = _terms(query)
    quoted = [f'"{_escape_fts_term(term)}"' for term in terms if term.strip()]
    return " OR ".join(quoted)


def _escape_fts_term(term: str) -> str:
    return term.replace('"', " ")


keyword_indexer = KeywordIndexer()
