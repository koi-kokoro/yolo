#!/usr/bin/env python3
"""
Fix out-of-range YOLO bbox coordinates in label txt files.

Rules:
  - x_center, y_center, width, height are clipped into [0, 1]
  - boxes with width <= 0 or height <= 0 are removed
  - malformed lines are removed
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "datasets" / "rsod" / "yolo_dataset"
SPLITS = ["train", "val", "test"]


def fix_bbox_coordinates(label_dir: str | os.PathLike) -> dict:
    """Fix YOLO label files in one directory."""
    label_path = Path(label_dir)
    stats = {"fixed": 0, "deleted": 0, "total": 0, "files_affected": 0}

    if not label_path.exists():
        return stats

    for filepath in sorted(label_path.glob("*.txt")):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        file_fixed = 0
        file_deleted = 0

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split()
            stats["total"] += 1

            if len(parts) != 5:
                file_deleted += 1
                continue

            try:
                class_id = int(parts[0])
                original = list(map(float, parts[1:]))
            except ValueError:
                file_deleted += 1
                continue

            x_center, y_center, width, height = original
            x_center = max(0.0, min(1.0, x_center))
            y_center = max(0.0, min(1.0, y_center))
            width = max(0.0, min(1.0, width))
            height = max(0.0, min(1.0, height))

            if [x_center, y_center, width, height] != original:
                file_fixed += 1

            if width <= 0 or height <= 0 or class_id < 0:
                file_deleted += 1
                continue

            new_lines.append(
                f"{class_id} {x_center:.6f} {y_center:.6f} "
                f"{width:.6f} {height:.6f}"
            )

        if file_fixed > 0 or file_deleted > 0 or len(new_lines) != len(lines):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
                if new_lines:
                    f.write("\n")

        stats["fixed"] += file_fixed
        stats["deleted"] += file_deleted
        if file_fixed > 0 or file_deleted > 0:
            stats["files_affected"] += 1

    return stats


def main() -> None:
    """Fix labels in all standard splits."""
    print("=" * 70)
    print("Fix YOLO label bbox coordinates")
    print("=" * 70)

    total_stats = {"fixed": 0, "deleted": 0, "total": 0, "files_affected": 0}

    for split in SPLITS:
        label_dir = DATASET_DIR / "labels" / split
        print(f"\n[{split}]")
        if not label_dir.exists():
            print("  directory not found, skipped")
            continue

        stats = fix_bbox_coordinates(label_dir)
        print(f"  fixed: {stats['fixed']}")
        print(f"  deleted: {stats['deleted']}")
        print(f"  files affected: {stats['files_affected']}")

        for key in total_stats:
            total_stats[key] += stats[key]

    print("\n" + "=" * 70)
    print("Done")
    for key, value in total_stats.items():
        print(f"  {key}: {value}")
    print("=" * 70)


if __name__ == "__main__":
    main()
