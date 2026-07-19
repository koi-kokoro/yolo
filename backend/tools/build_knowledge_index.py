"""显式构建 Day 11 LoveDA pgvector 知识索引。"""

from app.rag.indexer import build_index


if __name__ == "__main__":
    print(f"indexed_chunks={build_index()}")
