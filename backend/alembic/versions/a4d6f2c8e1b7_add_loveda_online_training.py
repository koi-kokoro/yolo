"""Add LoveDA online training lifecycle schema.

Revision ID: a4d6f2c8e1b7
Revises: f8d2e1a9b3c5
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a4d6f2c8e1b7"
down_revision: str | None = "f8d2e1a9b3c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TASK_COLUMNS = (
    ("task_kind", "VARCHAR(32) NOT NULL DEFAULT 'semantic_segmentation'"),
    ("runner", "VARCHAR(64) NOT NULL DEFAULT 'loveda_online_worker'"),
    ("experiment", "VARCHAR(32) NOT NULL DEFAULT 'S0'"),
    ("config_snapshot", "JSON"),
    ("requested_model", "VARCHAR(100)"),
    ("dataset_key", "VARCHAR(32)"),
    ("run_name", "VARCHAR(160)"),
    ("output_dir", "VARCHAR(500)"),
    ("pid", "INTEGER"),
    ("process_group_id", "INTEGER"),
    ("exit_code", "INTEGER"),
    ("heartbeat_at", "TIMESTAMP"),
    ("stop_requested_at", "TIMESTAMP"),
    ("last_event_offset", "BIGINT NOT NULL DEFAULT 0"),
    ("best_epoch", "INTEGER"),
    ("best_miou", "DOUBLE PRECISION"),
    ("latest_miou", "DOUBLE PRECISION"),
    ("latest_pixel_accuracy", "DOUBLE PRECISION"),
    ("artifact_manifest", "JSON"),
    ("error_code", "VARCHAR(64)"),
    ("cancel_reason", "VARCHAR(500)"),
)
METRIC_COLUMNS = (
    ("train_ce_loss", "DOUBLE PRECISION"),
    ("train_dice_loss", "DOUBLE PRECISION"),
    ("val_ce_loss", "DOUBLE PRECISION"),
    ("val_dice_loss", "DOUBLE PRECISION"),
    ("miou", "DOUBLE PRECISION"),
    ("pixel_accuracy", "DOUBLE PRECISION"),
    ("elapsed_seconds", "DOUBLE PRECISION"),
    ("raw_metrics", "JSON"),
    ("recorded_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name, ddl in TASK_COLUMNS:
            op.execute(sa.text(f"ALTER TABLE training_tasks ADD COLUMN IF NOT EXISTS {name} {ddl}"))
        for name, ddl in METRIC_COLUMNS:
            op.execute(sa.text(f"ALTER TABLE training_metrics ADD COLUMN IF NOT EXISTS {name} {ddl}"))
        op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_training_tasks_run_name ON training_tasks(run_name) WHERE run_name IS NOT NULL"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_training_tasks_status_user ON training_tasks(status, user_id)"))
        op.execute(sa.text("""
            DELETE FROM training_metrics a USING training_metrics b
            WHERE a.id > b.id AND a.task_id = b.task_id AND a.epoch = b.epoch
        """))
        op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_training_metrics_task_epoch ON training_metrics(task_id, epoch)"))
        return

    inspector = sa.inspect(bind)
    task_existing = {column["name"] for column in inspector.get_columns("training_tasks")}
    metric_existing = {column["name"] for column in inspector.get_columns("training_metrics")}
    task_types = {
        "task_kind": sa.String(32), "runner": sa.String(64), "experiment": sa.String(32),
        "config_snapshot": sa.JSON(), "requested_model": sa.String(100), "dataset_key": sa.String(32),
        "run_name": sa.String(160), "output_dir": sa.String(500), "pid": sa.Integer(),
        "process_group_id": sa.Integer(), "exit_code": sa.Integer(), "heartbeat_at": sa.DateTime(),
        "stop_requested_at": sa.DateTime(), "last_event_offset": sa.BigInteger(), "best_epoch": sa.Integer(),
        "best_miou": sa.Float(), "latest_miou": sa.Float(), "latest_pixel_accuracy": sa.Float(),
        "artifact_manifest": sa.JSON(), "error_code": sa.String(64), "cancel_reason": sa.String(500),
    }
    metric_types = {
        "train_ce_loss": sa.Float(), "train_dice_loss": sa.Float(), "val_ce_loss": sa.Float(),
        "val_dice_loss": sa.Float(), "miou": sa.Float(), "pixel_accuracy": sa.Float(),
        "elapsed_seconds": sa.Float(), "raw_metrics": sa.JSON(), "recorded_at": sa.DateTime(),
    }
    task_defaults = {
        "task_kind": sa.text("'semantic_segmentation'"),
        "runner": sa.text("'loveda_online_worker'"),
        "experiment": sa.text("'S0'"),
        "last_event_offset": sa.text("0"),
    }
    with op.batch_alter_table("training_tasks") as batch:
        for name, type_ in task_types.items():
            if name not in task_existing:
                default = task_defaults.get(name)
                batch.add_column(sa.Column(name, type_, nullable=default is None, server_default=default))
    with op.batch_alter_table("training_metrics") as batch:
        for name, type_ in metric_types.items():
            if name not in metric_existing:
                default = sa.text("CURRENT_TIMESTAMP") if name == "recorded_at" else None
                batch.add_column(sa.Column(name, type_, nullable=name != "recorded_at", server_default=default))
    # Existing databases may contain duplicate legacy epoch rows. Keep the oldest
    # row before adding the ORM-declared uniqueness contract.
    # SQLite supports the equivalent correlated DELETE directly.
    op.execute(sa.text("DELETE FROM training_metrics WHERE id IN (SELECT newer.id FROM training_metrics AS newer JOIN training_metrics AS older ON newer.task_id = older.task_id AND newer.epoch = older.epoch AND newer.id > older.id)"))
    inspector = sa.inspect(bind)
    existing_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("training_metrics")}
    if ("task_id", "epoch") not in existing_unique:
        with op.batch_alter_table("training_metrics") as batch:
            batch.create_unique_constraint("uq_training_metrics_task_epoch", ["task_id", "epoch"])
    existing_indexes = {item["name"] for item in inspector.get_indexes("training_tasks")}
    with op.batch_alter_table("training_tasks") as batch:
        if "uq_training_tasks_run_name" not in existing_indexes:
            batch.create_index("uq_training_tasks_run_name", ["run_name"], unique=True)
        if "ix_training_tasks_status_user" not in existing_indexes:
            batch.create_index("ix_training_tasks_status_user", ["status", "user_id"], unique=False)


def downgrade() -> None:
    # Preserve online-training history; destructive downgrade is intentionally omitted.
    pass
