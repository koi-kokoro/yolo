"""Protocol parser tests; no Ultralytics model is loaded."""
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "online_training_worker.py"
spec = importlib.util.spec_from_file_location("online_training_worker", MODULE_PATH)
worker = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(worker)


def test_csv_events_is_incremental_and_tolerates_partial_tail(tmp_path: Path):
    path = tmp_path / "results.csv"
    path.write_text(
        "epoch,metrics/mIoU,metrics/pixel_acc,train/ce_loss,train/dice_loss,val/ce_loss,val/dice_loss,lr/pg0,time\n"
        "1,0.4,0.6,1,0.8,0.9,0.7,0.01,12\n"
        "2,0.5,0.7,0.9,0.7,0.8,0.6,0.009",
        encoding="utf-8",
    )
    seen = set()
    first = worker.csv_events(path, 3, seen)
    assert [item["epoch"] for item in first] == [1]
    assert first[0]["miou"] == pytest.approx(0.4)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(",20\n")
    second = worker.csv_events(path, 3, seen)
    assert [item["epoch"] for item in second] == [2]
    assert worker.csv_events(path, 3, seen) == []


def test_csv_events_skips_nonfinite_and_bad_width(tmp_path: Path):
    path = tmp_path / "results.csv"
    path.write_text(
        "epoch,metrics/mIoU,metrics/pixel_acc\n"
        "1,NaN,Inf\n"
        "2,0.6\n"
        "3,0.7,0.8\n",
        encoding="utf-8",
    )
    rows = worker.csv_events(path, 3, set())
    assert [row["epoch"] for row in rows] == [3]


def test_materialize_data_yaml_resolves_portable_dataset_root(tmp_path: Path):
    root = MODULE_PATH.parent
    source = root / "test_runtime_data.yaml"
    dataset = root / "data" / "loveda_smoke_subset"
    destination = tmp_path / "data.runtime.yaml"
    source.write_text(
        "path: data/loveda_smoke_subset\ntrain: images/train\nval: images/val\nnames: {0: background}\n",
        encoding="utf-8",
    )
    try:
        result = worker.materialize_data_yaml(source, destination)
        text = result.read_text(encoding="utf-8")
        assert str(dataset.resolve()).replace("\\", "\\\\") in text or str(dataset.resolve()) in text
    finally:
        source.unlink(missing_ok=True)


def test_worker_declares_semantic_task_and_flat_artifact_names():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'YOLO(args.model, task="semantic")' in source
    assert 'artifact_names = [Path(name).name' in source
