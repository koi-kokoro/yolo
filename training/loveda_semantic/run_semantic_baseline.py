"""Train the reproducible LoveDA YOLO26n Semantic 50-epoch baseline."""
from __future__ import annotations

import csv
import json
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "loveda7.yaml"
RUNS = ROOT / "runs"
MODEL = "yolo26n-sem.pt"
CLASS_NAMES = ["background", "building", "road", "water", "barren", "forest", "agricultural"]
BASE_NAME = "baseline_e50_i512_b2"


def is_oom(error: BaseException) -> bool:
    text = str(error).lower()
    return isinstance(error, torch.cuda.OutOfMemoryError) or "out of memory" in text


def read_epoch_metrics(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append({key.strip(): float(value) for key, value in row.items() if value and value.strip()})
    return parsed


def to_serializable(value: Any) -> Any:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, Path):
        return str(value.resolve())
    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_serializable(item) for item in value]
    return value


def extract_class_iou(metrics: Any) -> dict[str, float] | None:
    candidates: list[Any] = []
    for owner in (metrics, getattr(metrics, "semantic", None), getattr(metrics, "seg", None)):
        if owner is None:
            continue
        for attr in ("class_iou", "iou_per_class", "per_class_iou", "ious"):
            value = getattr(owner, attr, None)
            if value is not None:
                candidates.append(value)
    confusion = getattr(metrics, "confusion_matrix", None)
    matrix = getattr(confusion, "matrix", None)
    if matrix is not None:
        matrix = np.asarray(to_serializable(matrix), dtype=np.float64)
        if matrix.ndim == 2 and matrix.shape[0] >= len(CLASS_NAMES) and matrix.shape[1] >= len(CLASS_NAMES):
            matrix = matrix[: len(CLASS_NAMES), : len(CLASS_NAMES)]
            denominator = matrix.sum(0) + matrix.sum(1) - np.diag(matrix)
            candidates.append(np.divide(np.diag(matrix), denominator, out=np.zeros_like(denominator), where=denominator > 0))
    for candidate in candidates:
        values = np.asarray(to_serializable(candidate), dtype=np.float64).reshape(-1)
        if values.size >= len(CLASS_NAMES):
            return {name: float(values[index]) for index, name in enumerate(CLASS_NAMES)}
    return None


def train_once(batch: int, name: str) -> dict[str, Any]:
    save_dir = RUNS / name
    if save_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {save_dir}")

    torch.cuda.empty_cache()
    # The installed PyTorch build rejects an explicit CUDA index before lazy CUDA initialization.
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = YOLO(MODEL)
    train_metrics = model.train(
        data=str(DATA.resolve()),
        epochs=50,
        imgsz=512,
        batch=batch,
        amp=True,
        device=0,
        workers=0,
        seed=26,
        deterministic=True,
        patience=10,
        project=str(RUNS.resolve()),
        name=name,
        exist_ok=False,
        pretrained=True,
        resume=False,
        plots=True,
        verbose=True,
    )
    elapsed = time.perf_counter() - started
    actual_dir = Path(train_metrics.save_dir).resolve()
    epochs = read_epoch_metrics(actual_dir / "results.csv")
    if not epochs:
        raise RuntimeError("Training completed without epoch metrics")

    miou_key = "metrics/mIoU"
    pixel_key = "metrics/pixel_acc"
    best_row = max(epochs, key=lambda row: row.get(miou_key, float("-inf")))
    final_row = epochs[-1]

    # Revalidate best.pt so the report can retain validator-only per-class IoU data.
    best_path = actual_dir / "weights" / "best.pt"
    val_metrics = YOLO(str(best_path)).val(
        data=str(DATA.resolve()), imgsz=512, batch=batch, device=0, workers=0,
        plots=True, project=str(actual_dir), name="best_validation", exist_ok=True,
    )
    class_iou = extract_class_iou(val_metrics)
    val_results = to_serializable(getattr(val_metrics, "results_dict", {}))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed" if len(epochs) == 50 else "early_stopped",
        "parameters": {
            "model": MODEL, "data": str(DATA.resolve()), "epochs": 50, "imgsz": 512,
            "batch": batch, "amp": True, "device": 0, "workers": 0, "seed": 26,
            "deterministic": True, "patience": 10, "pretrained": True, "resume": False,
        },
        "elapsed_seconds": elapsed,
        "epochs_recorded": len(epochs),
        "epoch_metrics": epochs,
        "best_epoch": int(best_row["epoch"]),
        "best_miou": best_row.get(miou_key),
        "best_pixel_accuracy": best_row.get(pixel_key),
        "final_epoch": int(final_row["epoch"]),
        "final_miou": final_row.get(miou_key),
        "final_pixel_accuracy": final_row.get(pixel_key),
        "best_validation_results": val_results,
        "per_class_iou": class_iou,
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
        "save_dir": str(actual_dir),
        "best_weight": str(best_path.resolve()),
        "last_weight": str((actual_dir / "weights" / "last.pt").resolve()),
    }
    (actual_dir / "baseline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("BASELINE_REPORT=" + json.dumps(report, ensure_ascii=False))
    return report


def main() -> None:
    try:
        train_once(batch=2, name=BASE_NAME)
    except Exception as error:
        if not is_oom(error):
            raise
        failure_dir = RUNS / BASE_NAME
        failure_record = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "oom",
            "batch": 2,
            "error": repr(error),
        }
        failure_dir.mkdir(parents=True, exist_ok=True)
        (failure_dir / "oom_failure.json").write_text(
            json.dumps(failure_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        torch.cuda.empty_cache()
        train_once(batch=1, name="baseline_e50_i512_b1_oom_retry")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
