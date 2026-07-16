"""Add Day 11 pgvector knowledge embeddings.

Revision ID: d11a6e2c4f90
Revises: a4d6f2c8e1b7
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d11a6e2c4f90"
down_revision: str | None = "a4d6f2c8e1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """CREATE TABLE knowledge_embeddings (
            id BIGSERIAL PRIMARY KEY,
            chunk_id VARCHAR(64) NOT NULL UNIQUE,
            source VARCHAR(500) NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    op.create_index("ix_knowledge_embeddings_source", "knowledge_embeddings", ["source"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_embeddings_source", table_name="knowledge_embeddings")
    op.drop_table("knowledge_embeddings")
