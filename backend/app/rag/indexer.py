"""可信目录知识文档加载、分块和显式 pgvector 索引。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import text

from app.config.settings import settings
from app.database.session import SessionLocal
from app.rag.retriever import EmbeddingService

_ALLOWED_SUFFIXES = {".md", ".txt"}


def load_documents(root: Path | None = None) -> list[tuple[str, str]]:
    trusted = (root or settings.rag_document_path).resolve()
    documents: list[tuple[str, str]] = []
    if not trusted.is_dir():
        return documents
    for path in trusted.rglob("*"):
        resolved = path.resolve()
        if not resolved.is_file() or resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
            continue
        if trusted not in resolved.parents:
            continue
        documents.append((resolved.relative_to(trusted).as_posix(), resolved.read_text("utf-8")))
    return documents


def chunk_text(value: str) -> list[str]:
    size = settings.RAG_CHUNK_SIZE
    overlap = min(settings.RAG_CHUNK_OVERLAP, size - 1)
    normalized = "\n".join(line.strip() for line in value.splitlines() if line.strip())
    return [normalized[pos : pos + size] for pos in range(0, len(normalized), size - overlap) if normalized[pos : pos + size]]


def build_index() -> int:
    """显式调用；幂等 upsert，不由应用启动钩子触发。"""
    embedder = EmbeddingService()
    db = SessionLocal()
    count = 0
    try:
        for source, document in load_documents():
            for ordinal, chunk in enumerate(chunk_text(document)):
                chunk_id = hashlib.sha256(f"{source}:{ordinal}:{chunk}".encode()).hexdigest()
                vector = embedder.embed(chunk)
                literal = "[" + ",".join(f"{float(item):.8f}" for item in vector) + "]"
                db.execute(
                    text(
                        "INSERT INTO knowledge_embeddings (chunk_id, source, content, embedding) "
                        "VALUES (:chunk_id, :source, :content, CAST(:embedding AS vector)) "
                        "ON CONFLICT (chunk_id) DO UPDATE SET source=EXCLUDED.source, content=EXCLUDED.content, embedding=EXCLUDED.embedding"
                    ),
                    {"chunk_id": chunk_id, "source": source, "content": chunk, "embedding": literal},
                )
                count += 1
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
