"""LoveDA semantic online-training lifecycle and JSONL reconciliation service."""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import case, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings, settings
from app.core.logger import get_logger
from app.entity.db_models import DetectionScene, TrainingMetric, TrainingTask
from app.training.training_process import TrainingProcessAdapter, training_process

logger = get_logger(__name__)
ACTIVE = ("pending", "starting", "running", "stopping")
TERMINAL = ("completed", "early_stopped", "cancelled", "failed", "interrupted")
RUN_RE = re.compile(r"^online_[0-9a-f]{32}$")
ARTIFACTS = {"best.pt", "last.pt", "results.csv", "args.yaml", "train.log", "events.jsonl"}
EVENT_STATUS = {
    "process_started": "starting", "training_started": "running",
    "stop_acknowledged": "stopping", "training_completed": "completed",
    "training_early_stopped": "early_stopped", "training_cancelled": "cancelled",
    "training_failed": "failed",
}


class TrainingServiceError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class TrainingService:
    def __init__(self, config: Settings = settings, process: TrainingProcessAdapter = training_process):
        self.config = config
        self.process = process

    def ensure_enabled(self) -> None:
        if not self.config.ONLINE_TRAINING_ENABLED:
            raise TrainingServiceError(503, "在线训练功能未启用")

    def _paths(self) -> tuple[Path, Path, Path]:
        root = self.config.online_training_trusted_root_path
        worker = self.config.online_training_worker_path
        output_root = self.config.online_training_output_root_path
        if root not in worker.parents or root not in output_root.parents:
            raise TrainingServiceError(500, "在线训练路径配置越过可信根")
        if not worker.is_file():
            raise TrainingServiceError(503, "在线训练 worker 不存在")
        return root, worker, output_root

    def _owned(self, db: Session, task_id: int, user_id: int) -> TrainingTask:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id, TrainingTask.user_id == user_id).first()
        if task is None:
            raise TrainingServiceError(404, "训练任务不存在")
        return task

    def _dataset(self, root: Path, key: str) -> Path:
        name = self.config.ONLINE_TRAINING_SMOKE_YAML if key == "smoke" else self.config.ONLINE_TRAINING_FULL_YAML
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            raise TrainingServiceError(400, "数据集配置无效或不存在")
        return path

    def create_task(self, db: Session, user_id: int, request: Any) -> TrainingTask:
        self.ensure_enabled()
        root, worker, output_root = self._paths()
        if request.model not in self.config.online_training_allowed_models:
            raise TrainingServiceError(400, "模型不在白名单")
        if request.device not in self.config.online_training_allowed_devices:
            raise TrainingServiceError(400, "设备不在白名单")
        epochs = request.epochs or self.config.ONLINE_TRAINING_DEFAULT_EPOCHS
        if epochs > self.config.ONLINE_TRAINING_MAX_EPOCHS:
            raise TrainingServiceError(400, "epochs 超过上限")
        if epochs < 10 and request.dataset_key != "smoke" and not self.config.ONLINE_TRAINING_ALLOW_SMALL_EPOCHS:
            raise TrainingServiceError(400, "小 epoch 仅允许 smoke 数据集")
        global_active = db.query(TrainingTask).filter(TrainingTask.status.in_(ACTIVE)).count()
        user_active = db.query(TrainingTask).filter(TrainingTask.user_id == user_id, TrainingTask.status.in_(ACTIVE)).count()
        if global_active >= self.config.ONLINE_TRAINING_GLOBAL_ACTIVE_LIMIT:
            raise TrainingServiceError(409, "已达到全局活跃训练任务上限")
        if user_active >= self.config.ONLINE_TRAINING_USER_ACTIVE_LIMIT:
            raise TrainingServiceError(409, "已达到用户活跃训练任务上限")
        scene = db.query(DetectionScene).filter(DetectionScene.name == "loveda_semantic").first()
        if scene is None:
            raise TrainingServiceError(503, "LoveDA 语义场景尚未初始化")
        data = self._dataset(root, request.dataset_key)
        task_uuid = uuid.uuid4().hex
        run_name = f"online_{task_uuid}"
        output = (output_root / run_name).resolve()
        if output_root not in output.parents or not RUN_RE.fullmatch(run_name):
            raise TrainingServiceError(500, "生成的 run 路径无效")
        presets = {"S0": (512, 1.0), "S1": (640, 1.0), "S2": (768, 1.0)}
        preset = presets.get(request.experiment)
        imgsz = preset[0] if preset else (request.img_size or 512)
        mosaic = preset[1] if preset else (request.mosaic if request.mosaic is not None else 0.0)
        snapshot = {
            "model": request.model, "dataset_key": request.dataset_key, "experiment": request.experiment,
            "device": request.device, "epochs": epochs, "batch": request.batch_size,
            "imgsz": imgsz, "patience": request.patience, "mosaic": mosaic,
        }
        task = TrainingTask(
            user_id=user_id, scene_id=scene.id, task_uuid=task_uuid, status="starting",
            task_kind="semantic_segmentation", runner="loveda_online_worker", experiment=request.experiment,
            config_snapshot=snapshot, requested_model=request.model, dataset_key=request.dataset_key,
            run_name=run_name, output_dir=str(output), model_name=request.model, epochs=epochs,
            img_size=imgsz, batch_size=request.batch_size, device=request.device, optimizer="auto", lr0=0,
            dataset_path=None, data_yaml=None, last_event_offset=0,
        )
        db.add(task)
        try:
            db.commit(); db.refresh(task)
        except IntegrityError:
            db.rollback()
            raise TrainingServiceError(409, "训练任务创建冲突") from None
        python = self.config.ONLINE_TRAINING_PYTHON or sys.executable
        argv = [python, str(worker), "--task-uuid", task_uuid, "--output-dir", str(output),
                "--model", request.model, "--data", str(data), "--experiment", request.experiment,
                "--device", request.device, "--epochs", str(epochs), "--batch", str(request.batch_size),
                "--imgsz", str(imgsz), "--patience", str(request.patience), "--mosaic", str(mosaic)]
        try:
            process = self.process.spawn(argv, root, output / "train.log")
            task.pid = process.pid
            task.process_group_id = process.pid
            task.heartbeat_at = datetime.now()
            db.commit(); db.refresh(task)
        except Exception as exc:
            task.status = "failed"; task.error_code = "spawn_failed"; task.error_message = str(exc)[:2000]
            task.completed_at = datetime.now(); db.commit()
            raise TrainingServiceError(500, "训练进程启动失败") from exc
        return task

    def reconcile(self, db: Session, task: TrainingTask) -> TrainingTask:
        task_id = task.id
        try:
            # Re-query inside this session. PostgreSQL serializes all reconcilers for the
            # task until the event offset and every derived field are committed together.
            query = db.query(TrainingTask).filter(TrainingTask.id == task_id)
            if db.get_bind().dialect.name == "postgresql":
                query = query.with_for_update()
            locked_task = query.populate_existing().one()
            output = Path(locked_task.output_dir or "")
            events = output / "events.jsonl"
            if events.is_file():
                start_offset = locked_task.last_event_offset or 0
                with events.open("rb") as handle:
                    handle.seek(start_offset)
                    data = handle.read()
                complete = data[: data.rfind(b"\n") + 1] if b"\n" in data else b""
                for line in complete.splitlines():
                    try:
                        event = json.loads(line.decode("utf-8"))
                        self._apply_event(db, locked_task, event)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
                        logger.warning("Ignoring malformed training event for task %s: %s", task_id, exc)
                next_offset = start_offset + len(complete)
                db.execute(
                    update(TrainingTask)
                    .where(TrainingTask.id == task_id)
                    .values(last_event_offset=case(
                        (TrainingTask.last_event_offset < next_offset, next_offset),
                        else_=TrainingTask.last_event_offset,
                    ))
                )
            if locked_task.pid and self.process.owns(locked_task.pid):
                code = self.process.poll(locked_task.pid)
                if code is not None:
                    locked_task.exit_code = code
                    self.process.forget(locked_task.pid)
                    if locked_task.status not in TERMINAL:
                        locked_task.status = "cancelled" if locked_task.stop_requested_at else "failed"
                        locked_task.error_code = "worker_exit_without_terminal_event"
                        locked_task.completed_at = datetime.now()
            db.commit()
            db.refresh(locked_task)
            return locked_task
        except Exception:
            db.rollback()
            raise

    def _upsert_metric(self, db: Session, values: dict[str, Any]) -> None:
        dialect = db.get_bind().dialect.name
        table = TrainingMetric.__table__
        update_values = {key: value for key, value in values.items() if key not in ("task_id", "epoch")}
        if dialect == "postgresql":
            statement = postgresql_insert(table).values(**values)
            db.execute(statement.on_conflict_do_update(
                index_elements=[table.c.task_id, table.c.epoch], set_=update_values
            ))
            return
        if dialect == "sqlite":
            statement = sqlite_insert(table).values(**values)
            db.execute(statement.on_conflict_do_update(
                index_elements=[table.c.task_id, table.c.epoch], set_=update_values
            ))
            return

        predicate = (table.c.task_id == values["task_id"]) & (table.c.epoch == values["epoch"])
        if db.execute(update(table).where(predicate).values(**update_values)).rowcount:
            return
        try:
            with db.begin_nested():
                db.execute(table.insert().values(**values))
        except IntegrityError:
            # The savepoint contains a concurrent unique violation, so the outer
            # reconciliation transaction remains usable.
            db.execute(update(table).where(predicate).values(**update_values))

    def _apply_event(self, db: Session, task: TrainingTask, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind in EVENT_STATUS:
            task.status = EVENT_STATUS[kind]
        if kind == "training_started" and task.started_at is None:
            task.started_at = datetime.now()
        if kind == "heartbeat":
            task.heartbeat_at = datetime.now()
        if kind == "epoch_end":
            epoch = int(event["epoch"])
            values = {
                "task_id": task.id,
                "epoch": epoch,
                **{name: event.get(name) for name in (
                    "train_ce_loss", "train_dice_loss", "val_ce_loss", "val_dice_loss",
                    "miou", "pixel_accuracy", "lr", "elapsed_seconds",
                )},
                "raw_metrics": event.get("raw_metrics") or event,
                "recorded_at": datetime.now(),
            }
            self._upsert_metric(db, values)
            task.current_epoch = max(task.current_epoch or 0, epoch)
            task.progress = min(100, int(task.current_epoch * 100 / max(task.epochs, 1)))
            task.latest_miou = event.get("miou")
            task.latest_pixel_accuracy = event.get("pixel_accuracy")
            if event.get("miou") is not None and (task.best_miou is None or event["miou"] > task.best_miou):
                task.best_miou = event["miou"]; task.best_epoch = epoch
        if kind == "artifact_ready":
            task.artifact_manifest = [name for name in event.get("artifacts", []) if Path(name).name in ARTIFACTS]
        if kind in ("training_completed", "training_early_stopped", "training_cancelled", "training_failed"):
            task.completed_at = datetime.now()
            if kind in ("training_completed", "training_early_stopped"):
                task.progress = 100
            task.error_code = event.get("error_code")
            task.error_message = event.get("message")

    def get_task(self, db: Session, task_id: int, user_id: int) -> TrainingTask:
        self.ensure_enabled()
        return self.reconcile(db, self._owned(db, task_id, user_id))

    def list_tasks(self, db: Session, user_id: int, limit: int = 50) -> list[TrainingTask]:
        self.ensure_enabled()
        tasks = db.query(TrainingTask).filter(TrainingTask.user_id == user_id).order_by(TrainingTask.created_at.desc()).limit(limit).all()
        return [self.reconcile(db, task) for task in tasks]

    def metrics(self, db: Session, task_id: int, user_id: int, after_epoch: int) -> list[TrainingMetric]:
        task = self.get_task(db, task_id, user_id)
        return db.query(TrainingMetric).filter(TrainingMetric.task_id == task.id, TrainingMetric.epoch > after_epoch).order_by(TrainingMetric.epoch).all()

    def stop(self, db: Session, task_id: int, user_id: int, reason: str = "user_requested") -> TrainingTask:
        task = self.get_task(db, task_id, user_id)
        if task.status not in ACTIVE:
            raise TrainingServiceError(409, f"任务状态 {task.status} 不可停止")
        output = Path(task.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "stop.requested").write_text(reason, encoding="utf-8")
        task.status = "stopping"; task.stop_requested_at = datetime.now(); task.cancel_reason = reason
        db.commit()
        if task.pid and self.process.owns(task.pid):
            self.process.graceful_stop(task.pid)
            deadline = time.monotonic() + self.config.ONLINE_TRAINING_STOP_GRACE_SECONDS
            while time.monotonic() < deadline and self.process.poll(task.pid) is None:
                time.sleep(min(0.1, self.config.ONLINE_TRAINING_POLL_SECONDS))
            if self.process.poll(task.pid) is None:
                self.process.force_stop(task.pid)
        return self.reconcile(db, task)

    def artifact(self, db: Session, task_id: int, user_id: int, name: str) -> Path:
        task = self.get_task(db, task_id, user_id)
        if name not in ARTIFACTS or Path(name).name != name:
            raise TrainingServiceError(404, "产物不存在")
        output = Path(task.output_dir).resolve()
        candidates = [output / name, output / "run" / name, output / "run" / "weights" / name]
        for candidate in candidates:
            resolved = candidate.resolve()
            if output in resolved.parents and resolved.is_file():
                return resolved
        raise TrainingServiceError(404, "产物不存在")

    def recover_active(self, db: Session) -> int:
        tasks = db.query(TrainingTask).filter(TrainingTask.status.in_(ACTIVE)).all()
        interrupted = 0
        for task in tasks:
            self.reconcile(db, task)
            if task.status in ACTIVE:
                # After restart no Popen handle is trusted. Reconcile files, then mark only;
                # never signal a possibly reused PID.
                task.status = "interrupted"; task.error_code = "backend_restarted"
                task.error_message = "后端重启后无法安全验证并接管训练进程"
                task.completed_at = datetime.now(); interrupted += 1
        db.commit()
        return interrupted


training_service = TrainingService()
