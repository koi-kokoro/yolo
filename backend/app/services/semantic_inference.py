"""Pure semantic preprocessing and artifact postprocessing."""

from dataclasses import dataclass
import io

import numpy as np
from PIL import Image


DISPLAY_NAMES = {"background": "背景", "building": "建筑", "road": "道路", "water": "水体", "barren": "裸地", "forest": "森林", "agricultural": "农田"}


class SemanticContractError(RuntimeError):
    pass


@dataclass
class SemanticArtifacts:
    index_mask: bytes
    color_mask: bytes
    overlay: bytes
    class_statistics: list[dict]
    output_shape: list[int]
    internal_label_7_collapsed: bool


def preprocess(image: Image.Image, input_size: tuple[int, int]) -> np.ndarray:
    resized = image.convert("RGB").resize(input_size, Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...])


def normalize_class_map(output: np.ndarray) -> tuple[np.ndarray, bool]:
    array = np.asarray(output)
    if array.ndim != 3 or array.shape[0] != 1:
        raise SemanticContractError(f"Expected [1,H,W] class-id map, got {array.shape}")
    if not np.all(np.isfinite(array)) or not np.all(array == np.rint(array)):
        raise SemanticContractError("Model output is not an integer class-id map")
    mask = np.rint(array[0]).astype(np.int64)
    collapsed = bool(np.any(mask == 7))
    mask[mask == 7] = 0
    values = np.unique(mask)
    if np.any((values < 0) | (values > 6)):
        raise SemanticContractError(f"Invalid public class ids: {values.tolist()}")
    return mask.astype(np.uint8), collapsed


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def build_artifacts(original: Image.Image, output: np.ndarray, classes: list[dict], overlay_alpha: float) -> SemanticArtifacts:
    mask, collapsed = normalize_class_map(output)
    original_rgb = original.convert("RGB")
    restored = Image.fromarray(mask, mode="L").resize(original_rgb.size, Image.Resampling.NEAREST)
    restored_array = np.asarray(restored, dtype=np.uint8)
    palette = np.zeros((7, 3), dtype=np.uint8)
    for expected_id, item in enumerate(classes):
        if item.get("id") != expected_id or len(item.get("rgb", [])) != 3:
            raise SemanticContractError("Metadata classes must be contiguous ids 0..6 with RGB colors")
        palette[expected_id] = item["rgb"]
    color_array = palette[restored_array]
    color = Image.fromarray(color_array, mode="RGB")
    overlay = Image.blend(original_rgb, color, overlay_alpha)
    counts = np.bincount(restored_array.ravel(), minlength=7)
    total = original_rgb.width * original_rgb.height
    statistics = [{"class_id": item["id"], "name": item["name"], "display_name": DISPLAY_NAMES.get(item["name"], item["name"]), "rgb": item["rgb"], "pixel_count": int(counts[item["id"]]), "ratio": float(counts[item["id"]] / total)} for item in classes]
    return SemanticArtifacts(_png(restored), _png(color), _png(overlay), statistics, list(np.asarray(output).shape), collapsed)
