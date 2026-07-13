"""Semantic preprocessing/postprocessing contract tests."""

import io

import numpy as np
from PIL import Image
import pytest

from app.services.semantic_inference import SemanticContractError, build_artifacts, normalize_class_map, preprocess

CLASSES = [
    {"id": 0, "name": "background", "rgb": [0, 0, 0]},
    {"id": 1, "name": "building", "rgb": [255, 64, 64]},
    {"id": 2, "name": "road", "rgb": [255, 200, 64]},
    {"id": 3, "name": "water", "rgb": [64, 160, 255]},
    {"id": 4, "name": "barren", "rgb": [180, 120, 64]},
    {"id": 5, "name": "forest", "rgb": [64, 180, 96]},
    {"id": 6, "name": "agricultural", "rgb": [180, 220, 64]},
]


def test_preprocess_is_rgb_nchw_float32_normalized():
    image = Image.new("RGB", (3, 2), (255, 128, 0))
    tensor = preprocess(image, (512, 512))
    assert tensor.shape == (1, 3, 512, 512)
    assert tensor.dtype == np.float32
    assert tensor.min() >= 0 and tensor.max() <= 1
    assert tensor[0, 0, 0, 0] == 1.0


def test_class_map_is_not_argmax_and_internal_7_collapses():
    output = np.array([[[7, 1], [2, 6]]], dtype=np.int64)
    mask, collapsed = normalize_class_map(output)
    assert collapsed is True
    assert mask.tolist() == [[0, 1], [2, 6]]


def test_invalid_class_and_logits_shape_fail():
    with pytest.raises(SemanticContractError):
        normalize_class_map(np.array([[[8]]]))
    with pytest.raises(SemanticContractError):
        normalize_class_map(np.zeros((1, 7, 2, 2)))


def test_artifacts_restore_size_palette_and_statistics():
    original = Image.new("RGB", (4, 2), (100, 100, 100))
    output = np.array([[[0, 1], [2, 3]]], dtype=np.uint8)
    artifacts = build_artifacts(original, output, CLASSES, 0.45)
    index = Image.open(io.BytesIO(artifacts.index_mask))
    color = Image.open(io.BytesIO(artifacts.color_mask))
    overlay = Image.open(io.BytesIO(artifacts.overlay))
    assert index.size == color.size == overlay.size == (4, 2)
    assert set(index.getdata()) == {0, 1, 2, 3}
    assert sum(item["pixel_count"] for item in artifacts.class_statistics) == 8
    assert sum(item["ratio"] for item in artifacts.class_statistics) == pytest.approx(1.0)
    assert color.getpixel((3, 0)) == (255, 64, 64)
