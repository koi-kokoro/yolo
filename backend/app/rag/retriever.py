"""pgvector 优先、本地可信文档兜底的知识检索器。"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import text

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    source: str
    score: float


class EmbeddingService:
    """通过 OpenAI 兼容接口调用已配置的 RAG embedding 服务。"""

    _PROVIDERS = {"deepseek", "qwen", "openai"}

    def _resolve_provider(self) -> tuple[str, str, str]:
        """返回 provider、API key 和 base URL，不把聊天模型用于 embedding。"""
        configured = settings.RAG_EMBEDDING_PROVIDER.strip().lower()
        if configured != "auto" and configured not in self._PROVIDERS:
            raise RuntimeError(f"不支持的 embedding provider: {configured}")

        if configured == "auto":
            # A custom RAG key/base URL is an explicit endpoint selection even when
            # the provider remains auto; partial custom configuration is rejected.
            if settings.RAG_EMBEDDING_API_KEY or settings.RAG_EMBEDDING_BASE_URL:
                provider = "custom"
                api_key = settings.RAG_EMBEDDING_API_KEY.strip()
                base_url = settings.RAG_EMBEDDING_BASE_URL.strip()
            elif settings.QWEN_API_KEY:
                provider, api_key, base_url = "qwen", settings.QWEN_API_KEY, settings.QWEN_BASE_URL
            elif settings.OPENAI_API_KEY:
                provider, api_key, base_url = "openai", settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL
            elif settings.DEEPSEEK_API_KEY:
                provider, api_key, base_url = "deepseek", settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL
            else:
                raise RuntimeError("embedding 服务未配置 API key")
        else:
            provider = configured
            provider_settings = {
                "deepseek": (settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL),
                "qwen": (settings.QWEN_API_KEY, settings.QWEN_BASE_URL),
                "openai": (settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL),
            }
            fallback_key, fallback_base_url = provider_settings[provider]
            api_key = settings.RAG_EMBEDDING_API_KEY.strip() or fallback_key
            base_url = settings.RAG_EMBEDDING_BASE_URL.strip() or fallback_base_url

        if not api_key:
            raise RuntimeError(f"embedding provider {provider} 未配置 API key")
        if not base_url:
            raise RuntimeError(f"embedding provider {provider} 未配置 base URL")
        return provider, api_key, base_url

    def embed(self, value: str) -> list[float]:
        _, api_key, base_url = self._resolve_provider()
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.embeddings.create(model=settings.RAG_EMBEDDING_MODEL, input=value)
        try:
            vector = response.data[0].embedding
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise RuntimeError("embedding 服务返回了无效向量") from exc
        if len(vector) != settings.RAG_EMBEDDING_DIMENSION:
            raise RuntimeError("embedding 维度与配置不一致")
        return vector


def _terms(value: str) -> list[str]:
    """生成中英文词项与中文字符 n-gram，不依赖外部分词服务。"""
    lowered = value.lower()
    words = re.findall(r"[a-z0-9_]+", lowered)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    grams: list[str] = []
    for run in chinese_runs:
        grams.extend(run[index : index + size] for size in (2, 3) for index in range(len(run) - size + 1))
    return words + grams


class LocalDocumentRetriever:
    """请求内扫描小型可信知识目录，以 BM25 风格词频分数检索文档分块。"""

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        # 延迟导入避免 indexer 对 EmbeddingService 的模块级依赖形成循环。
        from app.rag.indexer import chunk_text, load_documents

        query_terms = Counter(_terms(query))
        if not query_terms:
            return []
        chunks = [
            (source, chunk)
            for source, document in load_documents()
            for chunk in chunk_text(document)
        ]
        if not chunks:
            logger.warning("Local RAG fallback unavailable: trusted document directory is empty")
            return []

        tokenized = [(source, chunk, Counter(_terms(chunk))) for source, chunk in chunks]
        document_frequency = Counter(
            term for term in query_terms for _, _, terms in tokenized if term in terms
        )
        average_length = sum(sum(terms.values()) for _, _, terms in tokenized) / len(tokenized)
        scored: list[RetrievedChunk] = []
        for source, chunk, terms in tokenized:
            length = max(1, sum(terms.values()))
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = terms.get(term, 0)
                if not frequency:
                    continue
                inverse_frequency = math.log(1 + (len(chunks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                normalized = frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / max(average_length, 1)))
                score += inverse_frequency * normalized * min(query_frequency, 2)
            if score > 0:
                scored.append(RetrievedChunk(chunk, source, score))
        scored.sort(key=lambda item: item.score, reverse=True)
        limit = max(1, min(top_k or settings.RAG_TOP_K, 10))
        logger.info("Local RAG fallback completed: documents=%d chunks=%d hits=%d", len({item[0] for item in chunks}), len(chunks), min(len(scored), limit))
        return scored[:limit]


class PgVectorRetriever:
    def __init__(self, embed: Callable[[str], list[float]] | None = None) -> None:
        self.embed = embed or EmbeddingService().embed

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """知识表/扩展/网络故障统一降级为空结果，不影响其他 Agent。"""
        try:
            vector = self.embed(query)
            limit = max(1, min(top_k or settings.RAG_TOP_K, 10))
            literal = "[" + ",".join(f"{float(item):.8f}" for item in vector) + "]"
            db = SessionLocal()
            try:
                rows = db.execute(
                    text(
                        "SELECT content, source, 1 - (embedding <=> CAST(:embedding AS vector)) AS score "
                        "FROM knowledge_embeddings ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"
                    ),
                    {"embedding": literal, "limit": limit},
                ).mappings().all()
                return [
                    RetrievedChunk(str(row["content"]), str(row["source"]), float(row["score"]))
                    for row in rows
                    if float(row["score"]) > 0
                ]
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Vector RAG unavailable; local fallback may be used: %s", type(exc).__name__)
            return []


class HybridRetriever:
    """向量检索成功且有命中时优先，否则自动使用本地文档检索。"""

    def __init__(
        self,
        vector: PgVectorRetriever | None = None,
        local: LocalDocumentRetriever | None = None,
    ) -> None:
        self.vector = vector or PgVectorRetriever()
        self.local = local or LocalDocumentRetriever()

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        vector_hits = self.vector.retrieve(query, top_k)
        if vector_hits:
            logger.info("RAG retrieval source=pgvector hits=%d", len(vector_hits))
            return vector_hits
        local_hits = self.local.retrieve(query, top_k)
        logger.info("RAG retrieval source=local hits=%d", len(local_hits))
        return local_hits


rag_retriever = HybridRetriever()
