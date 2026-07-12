#!/usr/bin/env python3
"""
Verify a YOLO dataset directory.

Checks:
  - images/train, images/val, images/test and matching labels directories
  - image/label filename pairing
  - YOLO txt line format: class_id x_center y_center width height
  - normalized bbox values are in [0, 1], width/height > 0
  - optional data.yaml existence
"""

import os
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
SPLITS = ["train", "val", "test"]


def read_data_yaml(dataset_dir: str) -> dict:
    """Read simple top-level data.yaml keys without requiring PyYAML."""
    yaml_path = Path(dataset_dir) / "data.yaml"
    if not yaml_path.exists():
        return {}

    data = {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def list_images(directory: Path) -> list[Path]:
    """Return supported image files in a directory."""
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )


def list_labels(directory: Path) -> list[Path]:
    """Return label txt files in a directory."""
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix.lower() == ".txt")


def verify_label_file(label_file: Path) -> dict:
    """Verify one YOLO label file and collect class/object counts."""
    stats = {
        "objects": 0,
        "invalid_lines": [],
        "classes": {},
    }

    with open(label_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) != 5:
            stats["invalid_lines"].append((line_no, "expected 5 values"))
            continue

        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = map(float, parts[1:])
        except ValueError:
            stats["invalid_lines"].append((line_no, "non-numeric value"))
            continue

        if class_id < 0:
            stats["invalid_lines"].append((line_no, "negative class_id"))
            continue

        values = [x_center, y_center, width, height]
        if any(value < 0 or value > 1 for value in values):
            stats["invalid_lines"].append((line_no, "bbox value out of [0, 1]"))
            continue

        if width <= 0 or height <= 0:
            stats["invalid_lines"].append((line_no, "width/height must be > 0"))
            continue

        stats["objects"] += 1
        stats["classes"][class_id] = stats["classes"].get(class_id, 0) + 1

    return stats


def verify_dataset(dataset_dir: str) -> dict:
    """Verify YOLO dataset integrity and return a structured report."""
    root = Path(dataset_dir)
    results = {
        "dataset_dir": str(root),
        "exists": root.exists(),
        "data_yaml": read_data_yaml(dataset_dir),
        "splits": {},
        "summary": {
            "images": 0,
            "labels": 0,
            "objects": 0,
            "missing_labels": 0,
            "orphan_labels": 0,
            "invalid_lines": 0,
        },
        "warnings": [],
        "errors": [],
        "classes": {},
    }

    if not root.exists():
        results["errors"].append(f"dataset directory not found: {root}")
        return results

    for split in SPLITS:
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        image_files = list_images(image_dir)
        label_files = list_labels(label_dir)

        image_stems = {path.stem for path in image_files}
        label_stems = {path.stem for path in label_files}
        missing_labels = sorted(image_stems - label_stems)
        orphan_labels = sorted(label_stems - image_stems)

        split_result = {
            "image_dir_exists": image_dir.exists(),
            "label_dir_exists": label_dir.exists(),
            "images": len(image_files),
            "labels": len(label_files),
            "objects": 0,
            "missing_labels": missing_labels,
            "orphan_labels": orphan_labels,
            "invalid_files": {},
        }

        if not image_dir.exists():
            results["warnings"].append(f"missing image directory: {image_dir}")
        if not label_dir.exists():
            results["warnings"].append(f"missing label directory: {label_dir}")

        for label_file in label_files:
            label_stats = verify_label_file(label_file)
            split_result["objects"] += label_stats["objects"]
            if label_stats["invalid_lines"]:
                split_result["invalid_files"][label_file.name] = label_stats[
                    "invalid_lines"
                ]
                results["summary"]["invalid_lines"] += len(
                    label_stats["invalid_lines"]
                )

            for class_id, count in label_stats["classes"].items():
                results["classes"][class_id] = results["classes"].get(class_id, 0) + count

        results["splits"][split] = split_result
        results["summary"]["images"] += split_result["images"]
        results["summary"]["labels"] += split_result["labels"]
        results["summary"]["objects"] += split_result["objects"]
        results["summary"]["missing_labels"] += len(missing_labels)
        results["summary"]["orphan_labels"] += len(orphan_labels)

    if not results["data_yaml"]:
        results["warnings"].append("data.yaml not found or empty")

    if results["summary"]["missing_labels"] > 0:
        results["warnings"].append("some images have no matching label files")
    if results["summary"]["orphan_labels"] > 0:
        results["warnings"].append("some label files have no matching images")
    if results["summary"]["invalid_lines"] > 0:
        results["errors"].append("invalid YOLO label lines found")

    return results


def print_report(results: dict) -> None:
    """Print a human-readable dataset verification report."""
    print("=" * 70)
    print("YOLO Dataset Verification")
    print("=" * 70)
    print(f"Dataset: {results['dataset_dir']}")
    print(f"Exists : {results['exists']}")

    print("\n[Summary]")
    for key, value in results["summary"].items():
        print(f"  {key}: {value}")

    print("\n[Splits]")
    for split, item in results["splits"].items():
        print(
            f"  {split}: images={item['images']}, labels={item['labels']}, "
            f"objects={item['objects']}"
        )
        if item["missing_labels"]:
            print(f"    missing labels: {len(item['missing_labels'])}")
        if item["orphan_labels"]:
            print(f"    orphan labels: {len(item['orphan_labels'])}")
        if item["invalid_files"]:
            print(f"    invalid label files: {len(item['invalid_files'])}")

    print("\n[Classes]")
    if results["classes"]:
        for class_id in sorted(results["classes"]):
            print(f"  {class_id}: {results['classes'][class_id]}")
    else:
        print("  no objects found")

    if results["warnings"]:
        print("\n[Warnings]")
        for warning in results["warnings"]:
            print(f"  - {warning}")

    if results["errors"]:
        print("\n[Errors]")
        for error in results["errors"]:
            print(f"  - {error}")

    print("\nResult:", "FAILED" if results["errors"] else "PASSED")
    print("=" * 70)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    default_dataset = project_root / "datasets" / "rsod" / "yolo_dataset"
    dataset = sys.argv[1] if len(sys.argv) > 1 else str(default_dataset)
    report = verify_dataset(dataset)
    print_report(report)
    if report["errors"]:
        sys.exit(1)
