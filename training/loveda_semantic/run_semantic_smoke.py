"""Run bounded semantic overfit/full-smoke training and emit machine-readable reports."""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"


def is_oom(error: BaseException) -> bool:
    text = str(error).lower()
    return isinstance(error, torch.cuda.OutOfMemoryError) or "out of memory" in text or "cuda error: out of memory" in text


def read_results(csv_path: Path) -> dict:
    if not csv_path.is_file():
        return {"error": "results.csv missing"}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"error": "results.csv empty"}
    keys = list(rows[0])
    loss_keys = [key for key in keys if "loss" in key.lower()]
    metric_keys = [key for key in keys if key not in loss_keys and key.strip() not in {"epoch", "time"}]
    def values(row: dict, selected: list[str]) -> dict:
        return {key.strip(): float(row[key]) for key in selected if row.get(key, "").strip()}
    return {
        "epochs_recorded": len(rows), "columns": [key.strip() for key in keys],
        "start_loss": values(rows[0], loss_keys), "final_loss": values(rows[-1], loss_keys),
        "final_metrics": values(rows[-1], metric_keys),
    }


def run(mode: str, data: Path, epochs: int, imgsz: int, workers: int, seed: int) -> dict:
    name = f"{mode}_e{epochs}_i{imgsz}"
    common = dict(model="yolo26n-sem.pt", data=str(data.resolve()), epochs=epochs, imgsz=imgsz,
                  device=0, workers=workers, amp=True, seed=seed, deterministic=True,
                  project=str(RUNS.resolve()), name=name, exist_ok=False, plots=True, verbose=True)
    if mode == "overfit":
        common.update(patience=epochs, cache="ram", close_mosaic=0)
    attempts = []
    started = time.perf_counter()
    result = None
    chosen_batch = None
    for batch in (2, 1):
        try:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            attempt_start = time.perf_counter()
            result = YOLO("yolo26n-sem.pt").train(batch=batch, **{key: value for key, value in common.items() if key != "model"})
            attempts.append({"batch": batch, "status": "ok", "seconds": time.perf_counter() - attempt_start})
            chosen_batch = batch
            break
        except Exception as error:
            attempts.append({"batch": batch, "status": "oom" if is_oom(error) else "error", "error": repr(error)})
            if not is_oom(error) or batch == 1:
                raise
    save_dir = Path(result.save_dir)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "mode": mode, "data": str(data.resolve()),
        "parameters": {**common, "batch": chosen_batch}, "attempts": attempts,
        "elapsed_seconds": time.perf_counter() - started,
        "peak_cuda_bytes": torch.cuda.max_memory_allocated(),
        "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
        "save_dir": str(save_dir.resolve()), "best_weight": str((save_dir / "weights" / "best.pt").resolve()),
        "last_weight": str((save_dir / "weights" / "last.pt").resolve()),
        "results": read_results(save_dir / "results.csv"),
    }
    report_path = save_dir / "smoke_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("SMOKE_REPORT=" + json.dumps(report, ensure_ascii=False, default=str))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("overfit", "full"))
    parser.add_argument("--data", type=Path)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=26)
    args = parser.parse_args()
    data = args.data or ROOT / ("loveda7_smoke.yaml" if args.mode == "overfit" else "loveda7.yaml")
    epochs = args.epochs or (20 if args.mode == "overfit" else 3)
    run(args.mode, data, epochs, args.imgsz, args.workers, args.seed)


if __name__ == "__main__":
    # Required on Windows if workers is later raised above zero.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
