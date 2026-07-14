"""Safely synchronize the current semantic runtime artifact into ModelVersion.

The command verifies metadata.json and SHA256SUMS.txt against the actual ONNX file,
then transactionally inserts/updates the exact runtime identity and makes it the
single default semantic model. It never modifies deployment artifacts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Support the documented direct invocation: python tools/sync_semantic_runtime_registry.py
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import settings
from app.database.session import SessionLocal
from app.entity.db_models import DetectionScene, ModelVersion


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def declared_sha256(sums_path: Path, filename: str) -> str:
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    raise RuntimeError(f"SHA256SUMS.txt 未登记 {filename}")


def sync() -> tuple[int, str, str]:
    deploy_dir = settings.semantic_deploy_path.resolve()
    metadata_path = deploy_dir / "metadata.json"
    sums_path = deploy_dir / "SHA256SUMS.txt"
    onnx_path = deploy_dir / "best_dynamic.onnx"
    for path in (metadata_path, sums_path, onnx_path):
        if not path.is_file():
            raise RuntimeError(f"部署产物不存在: {path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_name = str(metadata.get("model") or "").strip()
    version = str(metadata.get("version") or "").strip()
    if not model_name or not version:
        raise RuntimeError("metadata.json 缺少 model/version")

    actual_sha = sha256_file(onnx_path)
    expected_sha = declared_sha256(sums_path, onnx_path.name)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"ONNX SHA256 校验失败: expected={expected_sha}, actual={actual_sha}"
        )

    db = SessionLocal()
    try:
        scene = (
            db.query(DetectionScene)
            .filter(DetectionScene.name == "loveda_semantic")
            .with_for_update()
            .first()
        )
        if scene is None:
            raise RuntimeError("LoveDA 语义场景不存在；请先执行 Alembic 迁移")

        record = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.scene_id == scene.id,
                ModelVersion.version == version,
            )
            .with_for_update()
            .first()
        )
        if record is None:
            record = ModelVersion(scene_id=scene.id, version=version)
            db.add(record)

        record.model_name = model_name
        record.model_type = "onnx"
        record.status = "active"
        record.model_path = str(onnx_path)
        record.is_default = True
        record.task_kind = "semantic_segmentation"
        record.runtime = "onnxruntime"
        record.artifact_sha256 = actual_sha
        record.file_size = onnx_path.stat().st_size
        record.description = "由 current/deploy metadata 与实际 ONNX SHA256 同步的运行时登记"
        record.model_metadata = {
            "metadata": metadata,
            "deploy_dir": str(deploy_dir),
            "source": "current/deploy",
            "sha256_verified": True,
        }
        db.flush()
        db.query(ModelVersion).filter(
            ModelVersion.scene_id == scene.id,
            ModelVersion.task_kind == "semantic_segmentation",
            ModelVersion.id != record.id,
        ).update({"is_default": False}, synchronize_session=False)
        db.commit()
        db.refresh(record)
        return record.id, model_name, version
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    model_id, model_name, version = sync()
    print(f"semantic registry synchronized: id={model_id}, model={model_name}, version={version}")
