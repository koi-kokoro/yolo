"""Ensure semantic MVP schema idempotent.

Revision ID: f8d2e1a9b3c5
Revises: e3b8a2f6c1d4
Create Date: 2026-07-14 09:44:45.011393

This is a repair migration.  It idempotently adds the semantic segmentation
MVP schema (columns, tables, seed scene/version) that older databases may be
missing because their alembic_version pointed to a revision that no longer
exists in this repository.  Fresh databases already have this schema from
revision c7a4e1d9b2f0, so this migration will be a no-op for them.
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa


revision: str = "f8d2e1a9b3c5"
down_revision: str | None = "e3b8a2f6c1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CLASSES = [
    "background",
    "building",
    "road",
    "water",
    "barren",
    "forest",
    "agricultural",
]
CLASSES_CN = {
    "background": "背景",
    "building": "建筑",
    "road": "道路",
    "water": "水体",
    "barren": "裸地",
    "forest": "森林",
    "agricultural": "农田",
}


def upgrade() -> None:
    conn = op.get_bind()

    # Add model_versions columns if missing.
    op.execute(
        sa.text(
            "ALTER TABLE model_versions "
            "ADD COLUMN IF NOT EXISTS task_kind VARCHAR(32) NOT NULL DEFAULT 'detection'"
        )
    )
    op.execute(
        sa.text("ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS runtime VARCHAR(32)")
    )
    op.execute(
        sa.text(
            "ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS artifact_sha256 VARCHAR(64)"
        )
    )
    op.execute(sa.text("ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS metadata JSON"))

    # Add unique constraint on (scene_id, version) if missing.
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_model_versions_scene_version'
                      AND conrelid = 'model_versions'::regclass
                ) THEN
                    ALTER TABLE model_versions
                    ADD CONSTRAINT uq_model_versions_scene_version UNIQUE (scene_id, version);
                END IF;
            END $$;
            """
        )
    )

    # Create semantic_tasks table if missing.
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS semantic_tasks (
                id SERIAL PRIMARY KEY,
                task_uuid VARCHAR(36) NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                model_version_id INTEGER NOT NULL REFERENCES model_versions(id),
                status VARCHAR(20) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                source_object_key VARCHAR(500) NOT NULL,
                source_sha256 VARCHAR(64) NOT NULL,
                source_content_type VARCHAR(100) NOT NULL,
                image_width INTEGER NOT NULL,
                image_height INTEGER NOT NULL,
                error_code VARCHAR(64),
                error_message TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_semantic_tasks_task_uuid ON semantic_tasks(task_uuid)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_semantic_tasks_user_id ON semantic_tasks(user_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_semantic_tasks_status ON semantic_tasks(status)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_semantic_tasks_user_created ON semantic_tasks(user_id, created_at)"
        )
    )

    # Create semantic_results table if missing.
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS semantic_results (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL UNIQUE REFERENCES semantic_tasks(id),
                index_mask_object_key VARCHAR(500) NOT NULL,
                color_mask_object_key VARCHAR(500) NOT NULL,
                overlay_object_key VARCHAR(500) NOT NULL,
                class_statistics JSON NOT NULL,
                inference_metadata JSON NOT NULL,
                inference_time_ms INTEGER NOT NULL,
                total_time_ms INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    # Seed the LoveDA semantic scene if missing.
    conn.execute(
        sa.text(
            """
            INSERT INTO detection_scenes
                (name, display_name, description, category, class_names, class_names_cn, is_active, created_at, updated_at)
            VALUES
                (:name, :display, :description, :category, :classes, :classes_cn, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {
            "name": "loveda_semantic",
            "display": "LoveDA 语义分割",
            "description": "LoveDA 七类土地覆盖语义分割",
            "category": "semantic_segmentation",
            "classes": json.dumps(CLASSES),
            "classes_cn": json.dumps(CLASSES_CN, ensure_ascii=False),
        },
    )

    # Seed the baseline semantic model version if missing.
    conn.execute(
        sa.text(
            """
            INSERT INTO model_versions
                (scene_id, version, model_name, model_type, status, model_path, is_default,
                 task_kind, runtime, artifact_sha256, created_at)
            SELECT
                ds.id,
                :version,
                :model_name,
                'onnx',
                'active',
                :model_path,
                true,
                'semantic_segmentation',
                'onnxruntime',
                :sha,
                CURRENT_TIMESTAMP
            FROM detection_scenes ds
            WHERE ds.name = :scene_name
            ON CONFLICT (scene_id, version) DO NOTHING
            """
        ),
        {
            "scene_name": "loveda_semantic",
            "version": "baseline-e50-i512-b2",
            "model_name": "YOLO26n Semantic",
            "model_path": "training/loveda_semantic/artifacts/baseline_e50_i512_b2/deploy/best_dynamic.onnx",
            "sha": "3a074b683f89c0c7a153efc6e9cdf81ac840e0b324cfefc3abc9f8022805d24c",
        },
    )


def downgrade() -> None:
    """No-op: this repair migration may share state with c7a4e1d9b2f0, so a
    safe reversible downgrade is not defined.  Reset the database from a backup
    if you need to undo this migration.
    """
    pass
