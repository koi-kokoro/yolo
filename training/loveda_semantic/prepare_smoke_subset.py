"""Create a deterministic, isolated LoveDA semantic subset with broad label coverage."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = TOOL_DIR / "data/loveda_yolo_semantic"
DEFAULT_OUTPUT = TOOL_DIR / "data/loveda_smoke_subset"
LABELS = tuple(range(7)) + (255,)
REGIONS = ("Urban", "Rural")
NAMES = ("background", "building", "road", "water", "barren", "forest", "agricultural")


def candidates(source: Path, split: str) -> list[dict]:
    rows = []
    for region in REGIONS:
        for mask_path in sorted((source / "masks" / split / region).glob("*.png")):
            image_path = source / "images" / split / region / mask_path.name
            if not image_path.is_file():
                continue
            values, counts = np.unique(np.asarray(Image.open(mask_path)), return_counts=True)
            pixels = {int(value): int(count) for value, count in zip(values, counts)}
            rows.append({"region": region, "stem": mask_path.stem, "image": image_path, "mask": mask_path, "pixels": pixels})
    return rows


def choose(rows: list[dict], count: int) -> list[dict]:
    """Greedy deterministic set cover, then favor rare-label pixel diversity."""
    selected: list[dict] = []
    remaining = list(rows)
    uncovered = set(LABELS)
    totals = {label: sum(row["pixels"].get(label, 0) for row in rows) or 1 for label in LABELS}
    while remaining and len(selected) < count:
        def score(row: dict) -> tuple[float, int, str]:
            present = set(row["pixels"])
            cover = len(present & uncovered)
            rarity = sum(row["pixels"].get(label, 0) / totals[label] for label in LABELS)
            region_bonus = 0.01 if not any(item["region"] == row["region"] for item in selected) else 0.0
            return cover * 1000 + rarity + region_bonus, len(present), f"{row['region']}/{row['stem']}"
        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)
        uncovered -= set(best["pixels"])
    return selected


def materialize(source: Path, output: Path, train_count: int, val_count: int) -> dict:
    if output.exists():
        shutil.rmtree(output)
    manifest = {"source": str(source.resolve()), "selection": "deterministic greedy label set cover", "splits": {}}
    for split, count in (("train", train_count), ("val", val_count)):
        picked = choose(candidates(source, split), count)
        manifest["splits"][split] = []
        for row in picked:
            for kind in ("image", "mask"):
                destination = output / ("images" if kind == "image" else "masks") / split / row["region"] / f"{row['stem']}.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row[kind], destination)
            manifest["splits"][split].append({"region": row["region"], "stem": row["stem"], "labels": sorted(row["pixels"]), "pixels": row["pixels"]})
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    yaml = [f"path: {output.resolve().as_posix()}", "train: images/train", "val: images/val", "", "names:"]
    yaml.extend(f"  {index}: {name}" for index, name in enumerate(NAMES))
    (output.parent.parent / "loveda7_smoke.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--train-count", type=int, default=8)
    parser.add_argument("--val-count", type=int, default=4)
    args = parser.parse_args()
    report = materialize(args.source, args.output, args.train_count, args.val_count)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
