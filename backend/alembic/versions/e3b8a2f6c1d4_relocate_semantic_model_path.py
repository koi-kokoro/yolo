"""Relocate the semantic baseline model metadata to src/training.

Revision ID: e3b8a2f6c1d4
Revises: c7a4e1d9b2f0
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e3b8a2f6c1d4"
down_revision: str | None = "c7a4e1d9b2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCENE_NAME = "loveda_semantic"
VERSION = "baseline-e50-i512-b2"
OLD_PATH = "training/loveda_semantic/artifacts/baseline_e50_i512_b2/deploy/best_dynamic.onnx"
NEW_PATH = "src/training/loveda_semantic/artifacts/baseline_e50_i512_b2/deploy/best_dynamic.onnx"


def _update_model_path(source_path: str, destination_path: str) -> None:
    op.get_bind().execute(
        sa.text(
            """UPDATE model_versions
               SET model_path = :destination_path
               WHERE version = :version
                 AND task_kind = 'semantic_segmentation'
                 AND model_path = :source_path
                 AND scene_id IN (
                     SELECT id FROM detection_scenes WHERE name = :scene_name
                 )"""
        ),
        {
            "destination_path": destination_path,
            "version": VERSION,
            "source_path": source_path,
            "scene_name": SCENE_NAME,
        },
    )


def upgrade() -> None:
    _update_model_path(OLD_PATH, NEW_PATH)


def downgrade() -> None:
    _update_model_path(NEW_PATH, OLD_PATH)
