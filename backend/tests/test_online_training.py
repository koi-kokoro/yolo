"""Online training tests use fake processes and temporary files only."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.api.auth import get_current_user
from app.config.settings import Settings
from app.database.session import Base
from app.entity.db_models import DetectionScene, TrainingMetric, TrainingTask, User
from app.entity.schemas import TrainingTaskCreate
from app.training.training_process import TrainingProcessAdapter
from app.training.training_service import TrainingService, TrainingServiceError


class FakeProcess:
    def __init__(self, pid=4242):
        self.pid = pid
        self.returncode = None
        self.signals = []
    def poll(self): return self.returncode
    def send_signal(self, value): self.signals.append(value); self.returncode = 0
    def kill(self): self.returncode = -9


class FakePopen:
    def __init__(self): self.calls = []; self.processes = []
    def __call__(self, **kwargs):
        self.calls.append(kwargs); process = FakeProcess(4242 + len(self.calls)); self.processes.append(process); return process


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user1 = User(username="u1x", email="u1@example.com", hashed_password="x")
    user2 = User(username="u2x", email="u2@example.com", hashed_password="x")
    scene = DetectionScene(name="loveda_semantic", display_name="LoveDA", category="semantic", class_names=[])
    session.add_all([user1, user2, scene]); session.commit()
    yield session, user1, user2, scene
    session.close(); Base.metadata.drop_all(engine)


def setup_service(tmp_path: Path, **overrides):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "worker.py").write_text("", encoding="utf-8")
    (tmp_path / "full.yaml").write_text("path: .", encoding="utf-8")
    (tmp_path / "smoke.yaml").write_text("path: .", encoding="utf-8")
    values = dict(
        ONLINE_TRAINING_ENABLED=True, ONLINE_TRAINING_TRUSTED_ROOT=str(tmp_path),
        ONLINE_TRAINING_WORKER="worker.py", ONLINE_TRAINING_OUTPUT_ROOT="runs",
        ONLINE_TRAINING_FULL_YAML="full.yaml", ONLINE_TRAINING_SMOKE_YAML="smoke.yaml",
        ONLINE_TRAINING_ALLOWED_MODELS="safe.pt", ONLINE_TRAINING_ALLOWED_DEVICES="cpu,0",
        ONLINE_TRAINING_USER_ACTIVE_LIMIT=1, ONLINE_TRAINING_GLOBAL_ACTIVE_LIMIT=2,
        ONLINE_TRAINING_STOP_GRACE_SECONDS=0,
    )
    values.update(overrides)
    fake = FakePopen(); adapter = TrainingProcessAdapter(fake)
    return TrainingService(Settings(_env_file=None, **values), adapter), fake


def request(**kwargs):
    values = dict(model="safe.pt", dataset_key="smoke", experiment="S0", device="cpu", epochs=2, batch_size=1, patience=2)
    values.update(kwargs)
    return TrainingTaskCreate(**values)


def test_spawn_uses_argument_array_shell_false_and_no_injection(tmp_path, db):
    session, user, _, _ = db; service, fake = setup_service(tmp_path)
    task = service.create_task(session, user.id, request())
    call = fake.calls[0]
    assert call["shell"] is False and isinstance(call["args"], list)
    assert call["args"][1] == str((tmp_path / "worker.py").resolve())
    assert task.pid == 4243
    with pytest.raises(TrainingServiceError):
        service.create_task(session, user.id, request(model="safe.pt;calc.exe"))


def test_disabled_limits_and_user_isolation(tmp_path, db):
    session, user1, user2, _ = db
    disabled, _ = setup_service(tmp_path, ONLINE_TRAINING_ENABLED=False)
    with pytest.raises(TrainingServiceError) as error:
        disabled.create_task(session, user1.id, request())
    assert error.value.status_code == 503
    with pytest.raises(TrainingServiceError) as error:
        disabled.list_tasks(session, user1.id)
    assert error.value.status_code == 503
    service, _ = setup_service(tmp_path)
    task = service.create_task(session, user1.id, request())
    with pytest.raises(TrainingServiceError) as error:
        service.get_task(session, task.id, user2.id)
    assert error.value.status_code == 404
    with pytest.raises(TrainingServiceError) as error:
        service.create_task(session, user1.id, request())
    assert error.value.status_code == 409


def test_jsonl_upsert_incomplete_tail_artifact_escape_and_stop(tmp_path, db):
    session, user, _, _ = db; service, fake = setup_service(tmp_path)
    task = service.create_task(session, user.id, request())
    events = Path(task.output_dir) / "events.jsonl"
    row = {"type":"epoch_end","epoch":1,"epochs":2,"miou":0.5,"pixel_accuracy":0.7,"train_ce_loss":1.0}
    events.write_text(json.dumps(row) + "\n" + json.dumps({**row, "miou":0.6}) + "\n" + '{"type":"epoch_end"', encoding="utf-8")
    metrics = service.metrics(session, task.id, user.id, 0)
    assert len(metrics) == 1 and metrics[0].miou == pytest.approx(0.6)
    offset = task.last_event_offset
    service.get_task(session, task.id, user.id)
    assert task.last_event_offset == offset
    with pytest.raises(TrainingServiceError): service.artifact(session, task.id, user.id, "../best.pt")
    stopped = service.stop(session, task.id, user.id)
    assert Path(task.output_dir, "stop.requested").is_file()
    assert stopped.status == "cancelled"


    run_dir = Path(task.output_dir) / "run" / "weights"
    run_dir.mkdir(parents=True)
    (run_dir / "best.pt").write_bytes(b"weights")
    assert service.artifact(session, task.id, user.id, "best.pt") == run_dir / "best.pt"


def test_reconcile_same_event_twice_upserts_one_metric(tmp_path, db):
    session, user, _, scene = db
    service, _ = setup_service(tmp_path)
    output = tmp_path / "runs" / ("online_" + "b" * 32)
    output.mkdir(parents=True)
    task = TrainingTask(
        user_id=user.id, scene_id=scene.id, task_uuid="b" * 32, status="running",
        model_name="safe.pt", epochs=2, img_size=512, batch_size=1, device="cpu",
        output_dir=str(output), run_name=output.name, last_event_offset=0,
    )
    session.add(task)
    session.commit()
    event = {"type": "epoch_end", "epoch": 1, "miou": 0.55, "pixel_accuracy": 0.75}
    (output / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    service.reconcile(session, task)
    consumed_offset = session.get(TrainingTask, task.id).last_event_offset
    # Deliberately replay the same complete event to verify database-level idempotency.
    session.query(TrainingTask).filter(TrainingTask.id == task.id).update({"last_event_offset": 0})
    session.commit()
    service.reconcile(session, task)

    assert session.query(TrainingMetric).filter_by(task_id=task.id, epoch=1).count() == 1
    assert session.get(TrainingTask, task.id).last_event_offset == consumed_offset


def test_two_sessions_concurrently_reconcile_one_event(tmp_path):
    database = tmp_path / "concurrent.sqlite3"
    engine = create_engine(
        f"sqlite:///{database}", connect_args={"check_same_thread": False, "timeout": 10}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed = factory()
    user = User(username="concurrent", email="concurrent@example.com", hashed_password="x")
    scene = DetectionScene(name="loveda_semantic", display_name="LoveDA", category="semantic", class_names=[])
    seed.add_all([user, scene])
    seed.commit()
    output = tmp_path / "runs" / ("online_" + "c" * 32)
    output.mkdir(parents=True)
    task = TrainingTask(
        user_id=user.id, scene_id=scene.id, task_uuid="c" * 32, status="running",
        model_name="safe.pt", epochs=2, img_size=512, batch_size=1, device="cpu",
        output_dir=str(output), run_name=output.name, last_event_offset=0,
    )
    seed.add(task)
    seed.commit()
    task_id = task.id
    event = {"type": "epoch_end", "epoch": 1, "miou": 0.65, "pixel_accuracy": 0.8}
    event_bytes = (json.dumps(event) + "\n").encode()
    (output / "events.jsonl").write_bytes(event_bytes)
    service, _ = setup_service(tmp_path)
    seed.close()

    def reconcile_in_independent_session():
        session = factory()
        try:
            stale_task = session.get(TrainingTask, task_id)
            return service.reconcile(session, stale_task).last_event_offset
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            offsets = list(pool.map(lambda _: reconcile_in_independent_session(), range(2)))
        verify = factory()
        assert verify.query(TrainingMetric).filter_by(task_id=task_id, epoch=1).count() == 1
        final_offset = verify.get(TrainingTask, task_id).last_event_offset
        assert final_offset == len(event_bytes)
        assert all(offset <= final_offset for offset in offsets)
        verify.close()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_postgresql_reconcile_lock_and_upsert_sql_compile():
    lock_sql = str(
        select(TrainingTask).where(TrainingTask.id == 1).with_for_update().compile(
            dialect=postgresql.dialect()
        )
    )
    table = TrainingMetric.__table__
    statement = postgresql.insert(table).values(task_id=1, epoch=1, miou=0.5)
    upsert_sql = str(statement.on_conflict_do_update(
        index_elements=[table.c.task_id, table.c.epoch], set_={"miou": 0.5}
    ).compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in lock_sql
    assert "ON CONFLICT (task_id, epoch) DO UPDATE" in upsert_sql


def test_api_contract_uses_auth_and_fake_subprocess(
    tmp_path, client, db_session, monkeypatch
):
    import app.api.training as training_api

    user = User(username="api-user", email="api@example.com", hashed_password="x")
    scene = DetectionScene(
        name="loveda_semantic",
        display_name="LoveDA",
        category="semantic",
        class_names=[],
    )
    db_session.add_all([user, scene])
    db_session.commit()

    assert client.get("/api/training/tasks").status_code in {401, 403}
    client.app.dependency_overrides[get_current_user] = lambda: user
    service, _fake = setup_service(tmp_path)
    monkeypatch.setattr(training_api, "training_service", service)

    created = client.post("/api/training/tasks", json=request().model_dump())
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["status"] == "starting"

    listed = client.get("/api/training/tasks")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == task_id
    assert client.get(f"/api/training/tasks/{task_id}").status_code == 200

    task = db_session.get(TrainingTask, task_id)
    event = {
        "type": "epoch_end",
        "epoch": 1,
        "epochs": 2,
        "miou": 0.5,
        "pixel_accuracy": 0.7,
    }
    Path(task.output_dir, "events.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )
    metrics = client.get(f"/api/training/tasks/{task_id}/metrics?after_epoch=0")
    assert metrics.status_code == 200
    assert metrics.json()["metrics"][0]["epoch"] == 1

    weights = Path(task.output_dir, "run", "weights", "best.pt")
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"weights")
    artifact = client.get(f"/api/training/tasks/{task_id}/artifacts/best.pt")
    assert artifact.status_code == 200
    assert artifact.content == b"weights"

    stopped = client.post(f"/api/training/tasks/{task_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelled"

    disabled, _ = setup_service(tmp_path / "disabled", ONLINE_TRAINING_ENABLED=False)
    monkeypatch.setattr(training_api, "training_service", disabled)
    assert client.get("/api/training/tasks").status_code == 503


def test_recovery_marks_interrupted_without_signalling_unknown_pid(tmp_path, db):
    session, user, _, scene = db; service, fake = setup_service(tmp_path)
    output = tmp_path / "runs" / ("online_" + "a" * 32); output.mkdir(parents=True)
    task = TrainingTask(user_id=user.id, scene_id=scene.id, task_uuid="a"*32, status="running", model_name="safe.pt", epochs=2, img_size=512, batch_size=1, device="cpu", output_dir=str(output), run_name=output.name, pid=99999)
    session.add(task); session.commit()
    assert service.recover_active(session) == 1
    assert task.status == "interrupted" and fake.calls == []
