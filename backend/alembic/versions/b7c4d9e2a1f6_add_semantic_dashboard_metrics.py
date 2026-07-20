"""Add semantic dashboard proxy metrics to detection tasks.

Revision ID: b7c4d9e2a1f6
Revises: d11a6e2c4f90
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b7c4d9e2a1f6"
down_revision: str | None = "d11a6e2c4f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "detection_tasks",
        sa.Column("semantic_metrics", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("detection_tasks", "semantic_metrics")
