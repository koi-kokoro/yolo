"""Convert LoveDA masks into Ultralytics semantic-segmentation layout."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from common import REGIONS, map_mask, parse_splits, source_pairs

TOOL_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = TOOL_DIR.parents[2]
DEFAULT_SOURCE = WORKSPACE_DIR / "02 项目资源/数据集/archive"
DEFAULT_OUTPUT = TOOL_DIR / "data/loveda_yolo_semantic"


def transfer_image(source: Path, destination: Path, mode: str, overwrite: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not overwrite:
            return "skipped"
        destination.unlink()
    if mode == "hardlink":
        try:
            os.link(source, destination)
            return "linked"
        except OSError:
            shutil.copy2(source, destination)
            return "copied_fallback"
    shutil.copy2(source, destination)
    return "copied"


def convert_mask(source: Path, destination: Path, overwrite: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        return "skipped"
    with Image.open(source) as image:
        array = np.asarray(image)
    mapped = map_mask(array)
    temporary = destination.with_name(destination.name + ".tmp")
    Image.fromarray(mapped, mode="L").save(temporary, format="PNG")
    temporary.replace(destination)
    return "converted"


def convert(source_root: Path, output_root: Path, splits: tuple[str, ...], image_mode: str, overwrite: bool) -> dict[str, int]:
    if source_root.resolve() == output_root.resolve() or source_root.resolve() in output_root.resolve().parents:
        raise ValueError("output root must not equal or contain the read-only source root")
    counters: dict[str, int] = {}
    for split in splits:
        for region in REGIONS:
            images, masks = source_pairs(source_root, split, region)
            if not images:
                raise FileNotFoundError(f"no images found for {split}/{region}")
            if split != "test" and set(images) != set(masks):
                missing_masks = sorted(set(images) - set(masks))
                missing_images = sorted(set(masks) - set(images))
                raise RuntimeError(f"unpaired {split}/{region}: missing_masks={missing_masks[:10]}, missing_images={missing_images[:10]}")
            for stem, source_image in images.items():
                status = transfer_image(source_image, output_root / "images" / split / region / source_image.name, image_mode, overwrite)
                counters[status] = counters.get(status, 0) + 1
                if split != "test":
                    status = convert_mask(masks[stem], output_root / "masks" / split / region / f"{stem}.png", overwrite)
                    counters[status] = counters.get(status, 0) + 1
    return counters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--splits", nargs="+", default=("train", "val"), choices=("train", "val", "test"))
    parser.add_argument("--image-mode", choices=("copy", "hardlink"), default="copy", help="hardlink automatically falls back to copy")
    parser.add_argument("--overwrite", action="store_true", help="replace existing derived files; never changes source files")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        counters = convert(args.source, args.output, parse_splits(args.splits), args.image_mode, args.overwrite)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Output: {args.output.resolve()}")
    print("Results: " + ", ".join(f"{key}={value}" for key, value in sorted(counters.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
