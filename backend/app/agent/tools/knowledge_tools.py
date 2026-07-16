"""LoveDA 知识检索薄工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from app.rag.retriever import rag_retriever


@tool
def retrieve_loveda_knowledge(query: str) -> str:
    """检索 LoveDA 七类、遥感语义分割与 IoU 相关知识。"""
    hits = rag_retriever.retrieve(query)
    return json.dumps(
        {
            "hits": [
                {"content": item.content, "source": item.source, "score": item.score}
                for item in hits
            ]
        },
        ensure_ascii=False,
    )
