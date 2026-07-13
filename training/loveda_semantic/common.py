"""Shared constants and path helpers for LoveDA semantic tooling."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

REGIONS = ("Urban", "Rural")
SOURCE_SPLITS = {"train": ("Train", "Train"), "val": ("Val", "Val"), "test": ("Test", "Test")}
LABEL_MAPPING = {0: 255, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}
VALID_SOURCE_LABELS = frozenset(LABEL_MAPPING)
VALID_TARGET_LABELS = frozenset({0, 1, 2, 3, 4, 5, 6, 255})
CLASS_NAMES = ("background", "building", "road", "water", "barren", "forest", "agricultural")
PALETTE = np.asarray(
    [(0, 0, 0), (255, 64, 64), (255, 200, 64), (64, 160, 255), (180, 120, 64), (64, 180, 96), (180, 220, 64)],
    dtype=np.uint8,
)
IGNORE_COLOR = np.asarray((160, 160, 160), dtype=np.uint8)


def source_region_dir(source_root: Path, split: str, region: str) -> Path:
    """Return a LoveDA source region directory without touching the filesystem."""
    outer, inner = SOURCE_SPLITS[split]
    return source_root / outer / inner / region


def source_pairs(source_root: Path, split: str, region: str) -> tuple[dict[str, Path], dict[str, Path]]:
    """Index source PNG images and masks by stem."""
    base = source_region_dir(source_root, split, region)
    images = {path.stem: path for path in sorted((base / "images_png").glob("*.png"))}
    masks_dir = base / "masks_png"
    masks = {path.stem: path for path in sorted(masks_dir.glob("*.png"))} if masks_dir.is_dir() else {}
    return images, masks


def map_mask(mask: np.ndarray) -> np.ndarray:
    """Map LoveDA labels to Ultralytics labels, rejecting unknown source values."""
    if mask.ndim != 2:
        raise ValueError(f"mask must be 2-D grayscale, got shape={mask.shape}")
    values = set(int(value) for value in np.unique(mask))
    unknown = values - VALID_SOURCE_LABELS
    if unknown:
        raise ValueError(f"unknown LoveDA labels: {sorted(unknown)}")
    lookup = np.full(256, 255, dtype=np.uint8)
    for source, target in LABEL_MAPPING.items():
        lookup[source] = target
    return lookup[mask.astype(np.uint8, copy=False)]


def parse_splits(values: Iterable[str]) -> tuple[str, ...]:
    splits = tuple(dict.fromkeys(value.lower() for value in values))
    unknown = set(splits) - set(SOURCE_SPLITS)
    if unknown:
        raise ValueError(f"unknown splits: {sorted(unknown)}")
    return splits
