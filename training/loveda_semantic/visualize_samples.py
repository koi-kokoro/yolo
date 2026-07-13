"""Create sampled original/color-mask/overlay panels with a class legend."""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import CLASS_NAMES, IGNORE_COLOR, PALETTE, REGIONS

TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = TOOL_DIR / "data/loveda_yolo_semantic"
DEFAULT_OUTPUT = TOOL_DIR / "reports/samples"


def colorize(mask: np.ndarray) -> np.ndarray:
    output = np.empty((*mask.shape, 3), dtype=np.uint8)
    output[:] = IGNORE_COLOR
    for label, color in enumerate(PALETTE):
        output[mask == label] = color
    return output


def render(image_path: Path, mask_path: Path, destination: Path, alpha: float) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    with Image.open(mask_path) as source:
        mask = np.asarray(source)
    if mask.ndim != 2 or image.size != (mask.shape[1], mask.shape[0]):
        raise ValueError(f"invalid pair: {image_path}, {mask_path}")
    colored = Image.fromarray(colorize(mask), mode="RGB")
    overlay = Image.blend(image, colored, alpha)
    legend_height = 34 * 2
    canvas = Image.new("RGB", (image.width * 3, image.height + legend_height), "white")
    canvas.paste(image, (0, 0)); canvas.paste(colored, (image.width, 0)); canvas.paste(overlay, (image.width * 2, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    entries = list(enumerate(CLASS_NAMES)) + [(255, "ignore")]
    for index, (label, name) in enumerate(entries):
        x = 12 + (index % 4) * (canvas.width // 4)
        y = image.height + 8 + (index // 4) * 30
        color = tuple(IGNORE_COLOR) if label == 255 else tuple(PALETTE[label])
        draw.rectangle((x, y, x + 20, y + 20), fill=color, outline="black")
        draw.text((x + 26, y + 3), f"{label}: {name}", fill="black", font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--splits", nargs="+", default=("train", "val"), choices=("train", "val"))
    parser.add_argument("--count", type=int, default=4, help="samples per split/region")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=0.45)
    args = parser.parse_args()
    if args.count < 1 or not 0 <= args.alpha <= 1:
        parser.error("count must be positive and alpha must be in [0, 1]")
    rng = random.Random(args.seed)
    rendered = 0
    for split in args.splits:
        for region in REGIONS:
            images = {p.stem: p for p in sorted((args.dataset / "images" / split / region).glob("*.png"))}
            masks = {p.stem: p for p in sorted((args.dataset / "masks" / split / region).glob("*.png"))}
            stems = sorted(set(images) & set(masks))
            for stem in rng.sample(stems, min(args.count, len(stems))):
                render(images[stem], masks[stem], args.output / split / region / f"{stem}_panel.jpg", args.alpha)
                rendered += 1
    print(f"Rendered {rendered} panels to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
