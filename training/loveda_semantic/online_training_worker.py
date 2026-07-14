"""Fixed LoveDA online-training worker.

The backend exclusively launches this file with an argument array.  The worker owns
Ultralytics and emits an append-only JSONL protocol; it never writes the database.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

TERMINAL_EVENTS = {
    "training_completed", "training_early_stopped", "training_cancelled", "training_failed"
}
_stop = threading.Event()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(path: Path, event_type: str, **payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "recorded_at": utc_now(), **payload}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def csv_events(path: Path, epochs: int, seen: set[int]) -> list[dict[str, Any]]:
    """Read only newline-terminated, full-width rows; safe during concurrent writes."""
    if not path.is_file():
        return []
    data = path.read_bytes()
    if not data.endswith((b"\n", b"\r")):
        data = data[: max(data.rfind(b"\n"), data.rfind(b"\r")) + 1]
    if not data:
        return []
    lines = data.decode("utf-8-sig", errors="replace").splitlines()
    if len(lines) < 2:
        return []
    reader = csv.DictReader(lines)
    expected = len(reader.fieldnames or [])
    events = []
    for row in reader:
        if None in row or len(row) != expected or any(value is None for value in row.values()):
            continue
        clean = {(key or "").strip(): (value or "").strip() for key, value in row.items()}
        try:
            epoch = int(float(clean.get("epoch", "0")))
        except ValueError:
            continue
        # Ultralytics versions differ between 0-based and 1-based CSVs.
        if epoch == 0:
            epoch = 1
        if epoch in seen:
            continue
        metrics = {
            "train_ce_loss": safe_float(clean.get("train/ce_loss")),
            "train_dice_loss": safe_float(clean.get("train/dice_loss")),
            "val_ce_loss": safe_float(clean.get("val/ce_loss")),
            "val_dice_loss": safe_float(clean.get("val/dice_loss")),
            "miou": safe_float(clean.get("metrics/mIoU")),
            "pixel_accuracy": safe_float(clean.get("metrics/pixel_acc")),
            "lr": safe_float(clean.get("lr/pg0") or clean.get("lr")),
            "elapsed_seconds": safe_float(clean.get("time")),
        }
        if metrics["miou"] is None and all(value is None for value in metrics.values()):
            continue
        seen.add(epoch)
        events.append({"epoch": epoch, "epochs": epochs, **metrics, "raw_metrics": clean})
    return events


def materialize_data_yaml(source: Path, destination: Path) -> Path:
    """Write a portable runtime YAML whose dataset root is absolute and trusted."""
    source = source.resolve()
    root = Path(__file__).resolve().parent
    if root not in source.parents or not source.is_file():
        raise ValueError("data YAML escapes trusted worker root")
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(key in payload for key in ("path", "train", "val", "names")):
        raise ValueError("invalid semantic dataset YAML")
    configured = Path(str(payload["path"]))
    dataset_root = configured.resolve() if configured.is_absolute() else (source.parent / configured).resolve()
    if root not in dataset_root.parents or not dataset_root.is_dir():
        raise ValueError("semantic dataset root is missing or untrusted")
    payload["path"] = str(dataset_root)
    destination.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destination


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--task-uuid", required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--model", required=True)
    result.add_argument("--data", type=Path, required=True)
    result.add_argument("--experiment", required=True)
    result.add_argument("--device", required=True)
    result.add_argument("--epochs", type=int, required=True)
    result.add_argument("--batch", type=int, required=True)
    result.add_argument("--imgsz", type=int, required=True)
    result.add_argument("--patience", type=int, required=True)
    result.add_argument("--mosaic", type=float, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    root = Path(__file__).resolve().parent
    output = args.output_dir.resolve()
    if root not in output.parents or output == root:
        raise ValueError("output-dir escapes trusted worker root")
    events = output / "events.jsonl"
    stop_file = output / "stop.requested"
    # The backend creates the directory first to attach the fixed train.log.
    output.mkdir(parents=True, exist_ok=True)
    unexpected = [item for item in output.iterdir() if item.name != "train.log"]
    if unexpected:
        raise FileExistsError("output-dir is not an empty allocated run directory")

    def request_stop(_signum=None, _frame=None):
        _stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)
    append_event(events, "process_started", pid=os.getpid(), task_uuid=args.task_uuid)

    heartbeat_done = threading.Event()
    def heartbeat() -> None:
        while not heartbeat_done.wait(5):
            if stop_file.exists():
                _stop.set()
            append_event(events, "heartbeat", pid=os.getpid())
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()

    try:
        runtime_data = materialize_data_yaml(args.data, output / "data.runtime.yaml")
        append_event(events, "training_started", epochs=args.epochs)
        from ultralytics import YOLO
        model = YOLO(args.model, task="semantic")
        if getattr(model, "task", None) != "semantic":
            raise RuntimeError(f"expected semantic model, got task={getattr(model, 'task', None)!r}")
        def epoch_callback(trainer):
            if stop_file.exists() or _stop.is_set():
                trainer.stop = True
                append_event(events, "stop_acknowledged")
            save_dir = Path(trainer.save_dir)
            for item in csv_events(save_dir / "results.csv", args.epochs, seen):
                append_event(events, "epoch_end", **item)
        seen: set[int] = set()
        model.add_callback("on_fit_epoch_end", epoch_callback)
        result = model.train(
            data=str(runtime_data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
            device=args.device, workers=0, patience=args.patience, mosaic=args.mosaic,
            project=str(output), name="run", exist_ok=False, pretrained=True, resume=False,
            plots=True, verbose=True,
        )
        run_dir = Path(result.save_dir)
        for item in csv_events(run_dir / "results.csv", args.epochs, seen):
            append_event(events, "epoch_end", **item)
        if _stop.is_set() or stop_file.exists():
            append_event(events, "training_cancelled", reason="stop_requested")
        else:
            artifact_names = [Path(name).name for name in ("weights/best.pt", "weights/last.pt", "results.csv", "args.yaml") if (run_dir / name).is_file()]
            append_event(events, "artifact_ready", artifacts=artifact_names)
            event = "training_completed" if len(seen) >= args.epochs else "training_early_stopped"
            append_event(events, event, epochs_recorded=len(seen))
        return 0
    except BaseException as exc:
        event = "training_cancelled" if _stop.is_set() or stop_file.exists() else "training_failed"
        append_event(events, event, error_code=type(exc).__name__, message=str(exc)[:2000])
        return 130 if event == "training_cancelled" else 1
    finally:
        heartbeat_done.set()
        heartbeat_thread.join(timeout=1)


if __name__ == "__main__":
    raise SystemExit(main())
