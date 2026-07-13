"""Perform a full source/converted LoveDA semantic dataset audit and write JSON."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from common import REGIONS, VALID_SOURCE_LABELS, VALID_TARGET_LABELS, parse_splits, source_pairs

TOOL_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = TOOL_DIR.parents[2]
DEFAULT_SOURCE = WORKSPACE_DIR / "02 项目资源/数据集/archive"
DEFAULT_CONVERTED = TOOL_DIR / "data/loveda_yolo_semantic"
DEFAULT_REPORT = TOOL_DIR / "reports/audit.json"


def inspect(path: Path, expected_labels: frozenset[int] | None) -> tuple[dict, Counter[int]]:
    info: dict = {"path": str(path), "ok": False}
    counts: Counter[int] = Counter()
    try:
        with Image.open(path) as image:
            image.load()
            array = np.asarray(image)
            info.update({"mode": image.mode, "size": list(image.size), "dtype": str(array.dtype), "shape": list(array.shape)})
        if expected_labels is not None:
            values, frequencies = np.unique(array, return_counts=True)
            labels = {int(value) for value in values}
            counts.update({int(value): int(count) for value, count in zip(values, frequencies)})
            info["labels"] = sorted(labels)
            info["unexpected_labels"] = sorted(labels - expected_labels)
            info["ok"] = array.ndim == 2 and array.dtype == np.uint8 and not info["unexpected_labels"]
        else:
            info["ok"] = array.ndim in (2, 3) and array.dtype == np.uint8
    except Exception as error:  # audit must report every broken file rather than stop
        info["error"] = f"{type(error).__name__}: {error}"
    return info, counts


def audit(source_root: Path, converted_root: Path, splits: tuple[str, ...]) -> dict:
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root.resolve()),
        "converted_root": str(converted_root.resolve()),
        "splits": {},
        "source_label_pixels": Counter(),
        "converted_label_pixels": Counter(),
        "issues": [],
    }
    for split in splits:
        split_report = {"regions": {}}
        for region in REGIONS:
            source_images, source_masks = source_pairs(source_root, split, region)
            converted_images = {p.stem: p for p in sorted((converted_root / "images" / split / region).glob("*.png"))}
            converted_masks_dir = converted_root / "masks" / split / region
            converted_masks = {p.stem: p for p in sorted(converted_masks_dir.glob("*.png"))} if converted_masks_dir.is_dir() else {}
            expected = set(source_images)
            region_report = {
                "source_images": len(source_images), "source_masks": len(source_masks),
                "converted_images": len(converted_images), "converted_masks": len(converted_masks),
                "missing_source_masks": sorted(expected - set(source_masks)) if split != "test" else [],
                "orphan_source_masks": sorted(set(source_masks) - expected),
                "missing_converted_images": sorted(expected - set(converted_images)),
                "extra_converted_images": sorted(set(converted_images) - expected),
                "missing_converted_masks": sorted(expected - set(converted_masks)) if split != "test" else [],
                "extra_converted_masks": sorted(set(converted_masks) - expected),
                "bad_files": [], "size_mismatches": [],
            }
            for category, index, labels in (("source_image", source_images, None), ("source_mask", source_masks, VALID_SOURCE_LABELS), ("converted_image", converted_images, None), ("converted_mask", converted_masks, VALID_TARGET_LABELS)):
                for stem, path in index.items():
                    info, counts = inspect(path, labels)
                    if category == "source_mask": report["source_label_pixels"].update(counts)
                    if category == "converted_mask": report["converted_label_pixels"].update(counts)
                    if not info["ok"]:
                        region_report["bad_files"].append({"category": category, "stem": stem, **info})
            for stem in sorted(expected & set(source_masks)):
                image_info, _ = inspect(source_images[stem], None)
                mask_info, _ = inspect(source_masks[stem], VALID_SOURCE_LABELS)
                if image_info.get("size") != mask_info.get("size"):
                    region_report["size_mismatches"].append({"dataset": "source", "stem": stem, "image": image_info.get("size"), "mask": mask_info.get("size")})
            for stem in sorted(set(converted_images) & set(converted_masks)):
                image_info, _ = inspect(converted_images[stem], None)
                mask_info, _ = inspect(converted_masks[stem], VALID_TARGET_LABELS)
                if image_info.get("size") != mask_info.get("size"):
                    region_report["size_mismatches"].append({"dataset": "converted", "stem": stem, "image": image_info.get("size"), "mask": mask_info.get("size")})
            issue_keys = ("missing_source_masks", "orphan_source_masks", "missing_converted_images", "extra_converted_images", "missing_converted_masks", "extra_converted_masks", "bad_files", "size_mismatches")
            if any(region_report[key] for key in issue_keys):
                report["issues"].append(f"{split}/{region}")
            split_report["regions"][region] = region_report
        report["splits"][split] = split_report
    report["source_label_pixels"] = {str(k): v for k, v in sorted(report["source_label_pixels"].items())}
    report["converted_label_pixels"] = {str(k): v for k, v in sorted(report["converted_label_pixels"].items())}
    report["ok"] = not report["issues"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--converted", type=Path, default=DEFAULT_CONVERTED)
    parser.add_argument("--splits", nargs="+", default=("train", "val"), choices=("train", "val", "test"))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = audit(args.source, args.converted, parse_splits(args.splits))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Audit {'PASSED' if report['ok'] else 'FAILED'}: {args.report.resolve()}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
