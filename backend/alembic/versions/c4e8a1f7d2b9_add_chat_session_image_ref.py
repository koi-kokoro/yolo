"""add safe chat session image reference

Revision ID: c4e8a1f7d2b9
Revises: b7c4d9e2a1f6
"""

from alembic import op
import sqlalchemy as sa

revision: str = "c4e8a1f7d2b9"
down_revision: str | None = "b7c4d9e2a1f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "last_image_ref",
            sa.String(length=64),
            nullable=True,
            comment="最近聊天图片的安全引用",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "last_image_ref")
