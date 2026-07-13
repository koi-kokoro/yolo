"""Pure temporary-directory tests for read-only model management."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.api.model_management import router
from app.config.settings import Settings
from app.services.model_management import (
    DEPLOYED_MODEL_ID,
    ModelManagementPathError,
    ModelManagementService,
    TRAINING_MODEL_ID,
)


def test_default_training_paths_resolve_inside_src_tree() -> None:
    config = Settings(_env_file=None)
    src_dir = Path(__file__).resolve().parents[2]
    expected_root = (src_dir / "training/loveda_semantic").resolve()

    assert config.semantic_deploy_path == expected_root / "artifacts/current/deploy"
    assert config.model_management_trusted_root_path == expected_root
    assert config.MODEL_MANAGEMENT_DEPLOY_DIR == "artifacts/current/deploy"
    assert config.MODEL_MANAGEMENT_TRAINING_RUN_DIR == "runs/v2_hr1024_yolo26s_sem_full_e50_b4_m1_20260713T0336Z"
    assert src_dir.parent / "training" not in config.semantic_deploy_path.parents


def _settings(root: Path, stale_seconds: int = 300) -> Settings:
    return Settings(
        MODEL_MANAGEMENT_TRUSTED_ROOT=str(root),
        MODEL_MANAGEMENT_DEPLOY_DIR="deploy",
        MODEL_MANAGEMENT_TRAINING_RUN_DIR="run",
        MODEL_MANAGEMENT_STALE_SECONDS=stale_seconds,
        MODEL_MANAGEMENT_MAX_TEXT_BYTES=64 * 1024,
        MODEL_MANAGEMENT_MAX_CSV_ROWS=100,
    )


def _write(path: Path, content: str | bytes = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def _complete_deploy(root: Path) -> None:
    deploy = root / "deploy"
    _write(deploy / "best.pt", b"pt-placeholder")
    _write(deploy / "best_dynamic.onnx", b"onnx-placeholder")
    _write(deploy / "metadata.json", json.dumps({
        "model": "fixture",
        "best_epoch": 2,
        "unsafe_path": "C:\\private\\model.pt",
    }))
    _write(deploy / "metrics.json", json.dumps({
        "overall": {"miou": 0.61, "pixel_accuracy": 0.82},
    }))
    _write(deploy / "training_args.yaml", "epochs: 2\nbatch: 4\ndata: C:\\private\\data.yaml\n")
    _write(deploy / "export_status.json", json.dumps({
        "success": True,
        "onnx_checker": "passed",
        "path": "C:\\private\\best_dynamic.onnx",
    }))
    _write(deploy / "SHA256SUMS.txt", f"{'a' * 64}  best.pt\n{'b' * 64}  best_dynamic.onnx\n")


def _active_run(root: Path, csv_content: str | None = None) -> None:
    run = root / "run"
    _write(run / "args.yaml", "epochs: 3\nbatch: 1\nimgsz: 1024\nmodel: yolo.pt\n")
    _write(run / "results.csv", csv_content or (
        "epoch,metrics/mIoU,metrics/pixel_acc,train/ce_loss,train/dice_loss,val/ce_loss,val/dice_loss\n"
        "1,0.40,0.60,1.0,0.8,0.9,0.7\n"
        "2,0.55,0.70,0.8,0.6,0.7,0.5\n"
    ))
    _write(run / "weights" / "best.pt", b"best-placeholder")
    _write(run / "weights" / "last.pt", b"last-placeholder")


def test_deployed_and_training_models_are_unified_without_binary_loading(tmp_path: Path) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path)
    service = ModelManagementService(_settings(tmp_path))

    deployed, training = service.models()

    assert deployed["id"] == DEPLOYED_MODEL_ID
    assert deployed["deployment_status"] == "deployed"
    assert deployed["best_miou"] == pytest.approx(0.61)
    assert deployed["metadata"]["unsafe_path"] == "model.pt"
    assert deployed["export_status"]["path"] == "best_dynamic.onnx"
    assert next(item for item in deployed["artifacts"] if item["name"] == "best.pt")["declared_sha256"] == "a" * 64
    assert training["id"] == TRAINING_MODEL_ID
    assert training["lifecycle_status"] == "training"
    assert training["epochs_recorded"] == 2
    assert training["current_epoch"] == 2
    assert training["progress"] == pytest.approx(200 / 3)
    assert training["latest_miou"] == pytest.approx(0.55)


def test_csv_snapshot_ignores_incomplete_tail_nonfinite_and_bad_width(tmp_path: Path) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path, (
        "epoch,metrics/mIoU,metrics/pixel_acc,train/ce_loss,train/dice_loss,val/ce_loss,val/dice_loss\n"
        "1,0.40,0.60,1,1,1,1\n"
        "2,NaN,Inf,1,1,1,1\n"
        "2,0.52,0.68,1,1,1,1\n"
        "3,0.70\n"
        "4,0.80,0.90,1"
    ))
    model = ModelManagementService(_settings(tmp_path)).training_model()

    assert [point["epoch"] for point in model["training_curve"]] == [1, 2]
    assert model["training_curve"][1]["miou"] == pytest.approx(0.52)
    assert model["best_miou"] == pytest.approx(0.52)
    assert any("不完整尾行" in warning for warning in model["warnings"])
    assert any("字段数不匹配" in warning for warning in model["warnings"])
    assert any("非有限指标" in warning for warning in model["warnings"])


def test_csv_nonfinite_only_epoch_is_not_counted_as_progress(tmp_path: Path) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path, (
        "epoch,metrics/mIoU,metrics/pixel_acc,train/ce_loss,train/dice_loss,val/ce_loss,val/dice_loss\n"
        "1,0.40,0.60,1,1,1,1\n"
        "2,NaN,0.70,1,1,1,1\n"
    ))

    model = ModelManagementService(_settings(tmp_path)).training_model()

    assert [point["epoch"] for point in model["training_curve"]] == [1]
    assert model["epochs_recorded"] == 1
    assert model["current_epoch"] == 1
    assert model["progress"] == pytest.approx(100 / 3)
    assert model["latest_miou"] == pytest.approx(0.40)


def test_stale_is_annotation_only(tmp_path: Path) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    for path in (tmp_path / "run").rglob("*"):
        if path.is_file():
            os.utime(path, (old.timestamp(), old.timestamp()))

    model = ModelManagementService(
        _settings(tmp_path, stale_seconds=60),
        now_provider=lambda: datetime.now(timezone.utc),
    ).training_model()

    assert model["lifecycle_status"] == "training"
    assert model["stale"] is True
    assert any("未查询或控制训练进程" in warning for warning in model["warnings"])


def test_report_has_status_priority_and_completed_epoch_without_report_is_finalizing(tmp_path: Path) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path, (
        "epoch,metrics/mIoU,metrics/pixel_acc,train/ce_loss,train/dice_loss,val/ce_loss,val/dice_loss\n"
        "1,0.40,0.60,1,1,1,1\n2,0.50,0.70,1,1,1,1\n3,0.60,0.80,1,1,1,1\n"
    ))
    service = ModelManagementService(_settings(tmp_path))
    assert service.training_model()["lifecycle_status"] == "finalizing"

    _write(tmp_path / "run" / "experiment_report.json", json.dumps({
        "status": "completed",
        "best_miou": 0.65,
        "save_dir": "C:\\private\\run",
    }))
    completed = service.training_model()
    assert completed["lifecycle_status"] == "completed"
    assert completed["stale"] is False
    assert completed["report"]["save_dir"] == "run"


def test_configured_directory_cannot_escape_trusted_root(tmp_path: Path) -> None:
    config = _settings(tmp_path)
    config.MODEL_MANAGEMENT_TRAINING_RUN_DIR = "../escaped"
    with pytest.raises(ModelManagementPathError):
        ModelManagementService(config)


def test_api_contract_is_bearer_protected_and_get_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _complete_deploy(tmp_path)
    _active_run(tmp_path)
    service = ModelManagementService(_settings(tmp_path))
    monkeypatch.setattr("app.api.model_management.model_management_service", service)

    api = FastAPI()
    api.include_router(router)
    client = TestClient(api)
    assert client.get("/api/model-management/models").status_code == 401

    api.dependency_overrides[get_current_user] = lambda: object()
    overview = client.get("/api/model-management/overview")
    listing = client.get("/api/model-management/models")
    detail = client.get(f"/api/model-management/models/{TRAINING_MODEL_ID}")

    assert overview.status_code == 200
    assert overview.json()["total"] == 2
    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["items"]} == {DEPLOYED_MODEL_ID, TRAINING_MODEL_ID}
    assert detail.status_code == 200
    assert detail.json()["source_type"] == "training_run"
    assert client.post("/api/model-management/models").status_code == 405
    assert client.get("/api/model-management/models/unknown").status_code == 404
    serialized = json.dumps(listing.json())
    assert str(tmp_path) not in serialized
