"""可复现的 LoveDA YOLO26 Semantic V2 短程筛选与结果汇总入口。"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import platform
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import torch
from ultralytics import YOLO

from run_semantic_baseline import is_oom, read_epoch_metrics, to_serializable

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "loveda7.yaml"
RUNS = ROOT / "runs"
MODEL = "yolo26n-sem.pt"
ALLOWED_MODELS = {"yolo26n-sem.pt", "yolo26s-sem.pt"}
SEED = 26
PRESETS = {
    "S0": {"imgsz": 512, "mosaic": 1.0},
    "S1": {"imgsz": 640, "mosaic": 1.0},
    "S2": {"imgsz": 768, "mosaic": 1.0},
    "M0": {"imgsz": None, "mosaic": 0.0},
    "custom": {"imgsz": None, "mosaic": None},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def environment() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in ("torch", "ultralytics", "numpy"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    cuda = torch.cuda.is_available()
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cuda_available": cuda,
        "cuda_version": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if cuda else None,
        "gpu_total_memory_bytes": torch.cuda.get_device_properties(0).total_memory if cuda else None,
        "packages": packages,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="LoveDA Semantic V2 严格单变量短程训练/汇总（默认不覆盖任何 run）")
    sub = result.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train", help="启动短程探测或最多 50 epoch 的正式实验")
    train.add_argument("--experiment", choices=PRESETS, required=True, help="S0/S1/S2 为锁定预设；M0 测最佳分辨率的 mosaic=0；custom 不锁定")
    train.add_argument("--model", default=MODEL, choices=sorted(ALLOWED_MODELS), help="已核实可加载的官方 YOLO26 Semantic 权重")
    train.add_argument("--data", type=Path, default=DATA, help="数据 YAML；正式训练默认 loveda7.yaml，短冒烟可显式使用子集")
    train.add_argument("--imgsz", type=int, default=None)
    train.add_argument("--batch", type=int, default=4)
    train.add_argument("--epochs", type=int, default=15)
    train.add_argument("--patience", type=int, default=15)
    train.add_argument("--mosaic", type=float, default=None)
    train.add_argument("--name", default=None, help="run 名；省略时生成含 UTC 时间的唯一名称")
    train.add_argument("--oom-fallback", action=argparse.BooleanOptionalAction, default=True,
                       help="CUDA OOM 时严格按初始 batch 逐级回退至 1；每次尝试使用独立 run 名")
    summary = sub.add_parser("summarize", help="汇总 V2 run 的 experiment_report.json")
    summary.add_argument("--runs-dir", type=Path, default=RUNS)
    summary.add_argument("--output", type=Path, default=ROOT / "reports/v2_shortlist_summary.csv")
    return result


def resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    preset = PRESETS[args.experiment]
    imgsz = preset["imgsz"] if preset["imgsz"] is not None else args.imgsz
    mosaic = preset["mosaic"] if preset["mosaic"] is not None else args.mosaic
    if imgsz is None or mosaic is None:
        raise ValueError(f"{args.experiment} 必须显式提供 " + ("--imgsz" if imgsz is None else "--mosaic"))
    if args.imgsz is not None and preset["imgsz"] is not None and args.imgsz != preset["imgsz"]:
        raise ValueError(f"{args.experiment} 锁定 imgsz={preset['imgsz']}，拒绝不一致参数")
    if args.mosaic is not None and preset["mosaic"] is not None and args.mosaic != preset["mosaic"]:
        raise ValueError(f"{args.experiment} 锁定 mosaic={preset['mosaic']}，拒绝不一致参数")
    if min(imgsz, args.batch, args.epochs, args.patience) <= 0 or not 0.0 <= mosaic <= 1.0:
        raise ValueError("imgsz/batch/epochs/patience 必须为正数，mosaic 必须在 0..1")
    if args.epochs > 50:
        raise ValueError("V2 训练入口禁止 epochs > 50")
    if args.batch > 4:
        raise ValueError("为保持严格回退链，--batch 必须在 1..4")
    data = args.data.resolve()
    if not data.is_file():
        raise FileNotFoundError(f"数据配置不存在: {data}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = args.name or f"v2_{args.experiment.lower()}_e{args.epochs}_i{imgsz}_b{args.batch}_m{mosaic:g}_{stamp}"
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("--name 必须是单个安全目录名")
    return {"experiment": args.experiment, "model": args.model, "data": str(data), "imgsz": imgsz,
            "batch": args.batch, "epochs": args.epochs, "patience": args.patience, "mosaic": mosaic,
            "name": name, "oom_fallback": args.oom_fallback, "seed": SEED, "device": 0,
            "workers": 0, "amp": True, "deterministic": True, "pretrained": True, "resume": False}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=to_serializable), encoding="utf-8")


def train_attempt(config: dict[str, Any], batch: int, name: str, attempt: int) -> dict[str, Any]:
    run_dir = RUNS / name
    if run_dir.exists():
        raise FileExistsError(f"拒绝覆盖现有 run: {run_dir}")
    started_at = utc_now()
    started = time.perf_counter()
    torch.cuda.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    launch = {**config, "batch": batch, "name": name, "attempt": attempt, "started_at": started_at, "environment": environment()}
    try:
        metrics = YOLO(config["model"]).train(
            data=config["data"], epochs=config["epochs"], imgsz=config["imgsz"], batch=batch,
            amp=True, device=0, workers=0, seed=SEED, deterministic=True, patience=config["patience"],
            mosaic=config["mosaic"], project=str(RUNS.resolve()), name=name, exist_ok=False,
            pretrained=True, resume=False, plots=True, verbose=True,
        )
    except Exception as error:
        elapsed = time.perf_counter() - started
        run_dir.mkdir(parents=True, exist_ok=True)
        failure = {**launch, "status": "oom" if is_oom(error) else "failed", "ended_at": utc_now(),
                   "elapsed_seconds": elapsed, "error": repr(error),
                   "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None,
                   "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved() if torch.cuda.is_available() else None}
        write_json(run_dir / "experiment_report.json", failure)
        raise
    actual_dir = Path(metrics.save_dir).resolve()
    rows = read_epoch_metrics(actual_dir / "results.csv")
    if not rows:
        raise RuntimeError("训练结束但 results.csv 中没有 epoch 指标")
    key = "metrics/mIoU"
    best = max(rows, key=lambda row: row.get(key, float("-inf")))
    report = {**launch, "status": "completed" if len(rows) == config["epochs"] else "early_stopped",
              "ended_at": utc_now(), "elapsed_seconds": time.perf_counter() - started, "epochs_recorded": len(rows),
              "best_epoch": int(best["epoch"]), "best_miou": best.get(key),
              "best_pixel_accuracy": best.get("metrics/pixel_acc"), "final_miou": rows[-1].get(key),
              "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None,
              "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved() if torch.cuda.is_available() else None,
              "save_dir": str(actual_dir), "best_weight": str((actual_dir / "weights/best.pt").resolve())}
    write_json(actual_dir / "experiment_report.json", report)
    return report


def run_train(args: argparse.Namespace) -> None:
    config = resolve_config(args)
    launch_path = ROOT / "reports/v2_launches" / f"{config['name']}.json"
    batches = list(range(config["batch"], 0, -1)) if config["oom_fallback"] else [config["batch"]]
    launch = {"status": "planned", "created_at": utc_now(), "batch_chain": batches, **config, "environment": environment()}
    write_json(launch_path, launch)
    failures = []
    for attempt, batch in enumerate(batches, start=1):
        attempt_name = config["name"] if attempt == 1 else f"{config['name']}_oom_retry_b{batch}"
        try:
            report = train_attempt(config, batch, attempt_name, attempt)
            write_json(launch_path, {**launch, "status": "completed", "selected_batch": batch,
                                     "selected_run": attempt_name, "failures": failures, "updated_at": utc_now()})
            print("V2_REPORT=" + json.dumps(report, ensure_ascii=False, default=to_serializable))
            return
        except Exception as error:
            failure = {"attempt": attempt, "batch": batch, "name": attempt_name,
                       "status": "oom" if is_oom(error) else "failed", "error": repr(error), "recorded_at": utc_now()}
            failures.append(failure)
            write_json(launch_path, {**launch, "status": failure["status"], "failures": failures, "updated_at": utc_now()})
            if not is_oom(error) or attempt == len(batches):
                raise
            write_json(RUNS / attempt_name / "oom_retry_decision.json",
                       {"rule": "仅 CUDA OOM 触发严格 batch 4→3→2→1 回退；其余核心参数不变；每次使用独立 run",
                        **failure, "next_batch": batches[attempt]})
            torch.cuda.empty_cache()


def summarize(args: argparse.Namespace) -> None:
    records = []
    for path in sorted(args.runs_dir.glob("v2_*/experiment_report.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        records.append({key: item.get(key) for key in ("experiment", "name", "status", "imgsz", "batch", "epochs", "patience", "mosaic", "best_epoch", "best_miou", "best_pixel_accuracy", "final_miou", "elapsed_seconds", "peak_cuda_allocated_bytes", "peak_cuda_reserved_bytes", "best_weight")})
    records.sort(key=lambda row: (row["best_miou"] is not None, row["best_miou"] or float("-inf")), reverse=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(records[0]) if records else ["experiment", "name", "status", "imgsz", "batch", "epochs", "patience", "mosaic", "best_epoch", "best_miou", "best_pixel_accuracy", "final_miou", "elapsed_seconds", "peak_cuda_allocated_bytes", "peak_cuda_reserved_bytes", "best_weight"]
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(records)
    print(json.dumps({"experiments": len(records), "output": str(args.output.resolve()), "ranking": records}, ensure_ascii=False, indent=2))


def main() -> None:
    args = parser().parse_args()
    run_train(args) if args.command == "train" else summarize(args)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
