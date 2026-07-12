#!/usr/bin/env python3
"""
Fix out-of-range VOC XML bounding box coordinates.

Rules:
  - xmin/ymin are clipped to 0
  - xmax/ymax are clipped to image width/height
  - objects with invalid boxes are removed
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_DIR = PROJECT_ROOT / "datasets" / "rsod" / "raw" / "annotations"


def fix_xml_file(xml_path: str | os.PathLike) -> dict:
    """Fix one VOC XML file."""
    path = Path(xml_path)
    stats = {"fixed": 0, "deleted": 0, "total": 0}

    try:
        tree = ET.parse(path)
        root = tree.getroot()

        size = root.find("size")
        if size is None:
            return stats

        width_elem = size.find("width")
        height_elem = size.find("height")
        if width_elem is None or height_elem is None:
            return stats
        if width_elem.text is None or height_elem.text is None:
            return stats

        img_width = int(float(width_elem.text))
        img_height = int(float(height_elem.text))
        if img_width <= 0 or img_height <= 0:
            return stats

        objects = root.findall("object")
        stats["total"] = len(objects)
        to_delete = []

        for obj in objects:
            bbox = obj.find("bndbox")
            if bbox is None:
                continue

            xmin_elem = bbox.find("xmin")
            ymin_elem = bbox.find("ymin")
            xmax_elem = bbox.find("xmax")
            ymax_elem = bbox.find("ymax")
            elems = [xmin_elem, ymin_elem, xmax_elem, ymax_elem]

            if any(elem is None or elem.text is None for elem in elems):
                continue

            xmin = float(xmin_elem.text)
            ymin = float(ymin_elem.text)
            xmax = float(xmax_elem.text)
            ymax = float(ymax_elem.text)
            original = [xmin, ymin, xmax, ymax]

            xmin = max(0.0, min(float(img_width), xmin))
            ymin = max(0.0, min(float(img_height), ymin))
            xmax = max(0.0, min(float(img_width), xmax))
            ymax = max(0.0, min(float(img_height), ymax))

            if xmax <= xmin or ymax <= ymin:
                to_delete.append(obj)
                stats["deleted"] += 1
                continue

            if [xmin, ymin, xmax, ymax] != original:
                xmin_elem.text = str(int(round(xmin)))
                ymin_elem.text = str(int(round(ymin)))
                xmax_elem.text = str(int(round(xmax)))
                ymax_elem.text = str(int(round(ymax)))
                stats["fixed"] += 1

        for obj in to_delete:
            root.remove(obj)

        if stats["fixed"] > 0 or stats["deleted"] > 0:
            tree.write(path, encoding="utf-8", xml_declaration=True)

    except Exception as exc:
        print(f"  [error] {path.name}: {exc}")

    return stats


def main() -> None:
    """Fix all XML files in the default annotation directory."""
    print("=" * 70)
    print("Fix VOC XML bbox coordinates")
    print("=" * 70)

    total_stats = {"fixed": 0, "deleted": 0, "total": 0, "files_affected": 0}

    if not ANNOTATION_DIR.exists():
        print(f"Annotation directory not found: {ANNOTATION_DIR}")
        return

    xml_files = sorted(ANNOTATION_DIR.glob("*.xml"))
    print(f"Found {len(xml_files)} XML files")

    for xml_file in xml_files:
        stats = fix_xml_file(xml_file)
        if stats["fixed"] > 0 or stats["deleted"] > 0:
            total_stats["files_affected"] += 1
            print(
                f"  {xml_file.name}: fixed {stats['fixed']}, "
                f"deleted {stats['deleted']}"
            )

        total_stats["fixed"] += stats["fixed"]
        total_stats["deleted"] += stats["deleted"]
        total_stats["total"] += stats["total"]

    print("\n" + "=" * 70)
    print("Done")
    for key, value in total_stats.items():
        print(f"  {key}: {value}")
    print("=" * 70)


if __name__ == "__main__":
    main()
