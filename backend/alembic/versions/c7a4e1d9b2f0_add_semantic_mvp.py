"""Add semantic segmentation MVP tables and model metadata.

Revision ID: c7a4e1d9b2f0
Revises: 9befde7d4334
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa

revision: str = "c7a4e1d9b2f0"
down_revision: str | None = "9befde7d4334"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASSES = ["background", "building", "road", "water", "barren", "forest", "agricultural"]
CLASSES_CN = {"background": "背景", "building": "建筑", "road": "道路", "water": "水体", "barren": "裸地", "forest": "森林", "agricultural": "农田"}


def upgrade() -> None:
    op.add_column("model_versions", sa.Column("task_kind", sa.String(32), nullable=False, server_default="detection"))
    op.add_column("model_versions", sa.Column("runtime", sa.String(32), nullable=True))
    op.add_column("model_versions", sa.Column("artifact_sha256", sa.String(64), nullable=True))
    op.add_column("model_versions", sa.Column("metadata", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_model_versions_scene_version", "model_versions", ["scene_id", "version"])

    op.create_table(
        "semantic_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_uuid", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_object_key", sa.String(500), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_content_type", sa.String(100), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_tasks_task_uuid", "semantic_tasks", ["task_uuid"], unique=True)
    op.create_index("ix_semantic_tasks_user_id", "semantic_tasks", ["user_id"])
    op.create_index("ix_semantic_tasks_status", "semantic_tasks", ["status"])
    op.create_index("ix_semantic_tasks_user_created", "semantic_tasks", ["user_id", "created_at"])
    op.create_table(
        "semantic_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("index_mask_object_key", sa.String(500), nullable=False),
        sa.Column("color_mask_object_key", sa.String(500), nullable=False),
        sa.Column("overlay_object_key", sa.String(500), nullable=False),
        sa.Column("class_statistics", sa.JSON(), nullable=False),
        sa.Column("inference_metadata", sa.JSON(), nullable=False),
        sa.Column("inference_time_ms", sa.Integer(), nullable=False),
        sa.Column("total_time_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["semantic_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )

    conn = op.get_bind()
    scene_id = conn.execute(sa.text("SELECT id FROM detection_scenes WHERE name=:name"), {"name": "loveda_semantic"}).scalar()
    if scene_id is None:
        result = conn.execute(sa.text("""INSERT INTO detection_scenes
            (name, display_name, description, category, class_names, class_names_cn, is_active, created_at, updated_at)
            VALUES (:name, :display, :description, :category, :classes, :classes_cn, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id"""), {"name": "loveda_semantic", "display": "LoveDA 语义分割", "description": "LoveDA 七类土地覆盖语义分割", "category": "semantic_segmentation", "classes": json.dumps(CLASSES), "classes_cn": json.dumps(CLASSES_CN, ensure_ascii=False)})
        scene_id = result.scalar()
    existing = conn.execute(sa.text("SELECT id FROM model_versions WHERE scene_id=:scene_id AND version=:version"), {"scene_id": scene_id, "version": "baseline-e50-i512-b2"}).scalar()
    if existing is None:
        conn.execute(sa.text("""INSERT INTO model_versions
            (scene_id, version, model_name, model_type, status, model_path, is_default, task_kind, runtime, artifact_sha256, created_at)
            VALUES (:scene_id, :version, :name, 'onnx', 'active', :path, true, 'semantic_segmentation', 'onnxruntime', :sha, CURRENT_TIMESTAMP)"""), {"scene_id": scene_id, "version": "baseline-e50-i512-b2", "name": "YOLO26n Semantic", "path": "training/loveda_semantic/artifacts/baseline_e50_i512_b2/deploy/best_dynamic.onnx", "sha": "a5f7c887c20d628aabc2b8a834f6f376d4919687ebc7d2bc97f51fb9e413ba90"})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM model_versions WHERE task_kind='semantic_segmentation' AND version='baseline-e50-i512-b2'"))
    conn.execute(sa.text("DELETE FROM detection_scenes WHERE name='loveda_semantic' AND NOT EXISTS (SELECT 1 FROM model_versions WHERE model_versions.scene_id=detection_scenes.id)"))
    op.drop_table("semantic_results")
    op.drop_index("ix_semantic_tasks_user_created", table_name="semantic_tasks")
    op.drop_index("ix_semantic_tasks_status", table_name="semantic_tasks")
    op.drop_index("ix_semantic_tasks_user_id", table_name="semantic_tasks")
    op.drop_index("ix_semantic_tasks_task_uuid", table_name="semantic_tasks")
    op.drop_table("semantic_tasks")
    op.drop_constraint("uq_model_versions_scene_version", "model_versions", type_="unique")
    op.drop_column("model_versions", "metadata")
    op.drop_column("model_versions", "artifact_sha256")
    op.drop_column("model_versions", "runtime")
    op.drop_column("model_versions", "task_kind")
