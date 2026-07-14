from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

TOOL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_DIR))

from common import map_mask, source_pairs, source_region_dir  # noqa: E402
from day07_evaluate_export import confusion_update, metrics, validate_report  # noqa: E402


class MappingTests(unittest.TestCase):
    def test_fixed_mapping_and_uint8(self) -> None:
        source = np.asarray([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.uint8)
        expected = np.asarray([[255, 0, 1, 2], [3, 4, 5, 6]], dtype=np.uint8)
        actual = map_mask(source)
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.dtype, np.uint8)

    def test_unknown_label_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown LoveDA labels"):
            map_mask(np.asarray([[8]], dtype=np.uint8))


class PairingTests(unittest.TestCase):
    def test_source_pairing_uses_stem_and_region_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            region = source_region_dir(root, "train", "Urban")
            (region / "images_png").mkdir(parents=True)
            (region / "masks_png").mkdir()
            Image.new("RGB", (2, 2)).save(region / "images_png" / "样本 01.png")
            Image.new("L", (2, 2)).save(region / "masks_png" / "样本 01.png")
            Image.new("L", (2, 2)).save(region / "masks_png" / "orphan.png")
            images, masks = source_pairs(root, "train", "Urban")
            self.assertEqual(set(images), {"样本 01"})
            self.assertEqual(set(masks), {"样本 01", "orphan"})
            self.assertEqual(images["样本 01"].parent.name, "images_png")


class EvaluationTests(unittest.TestCase):
    def test_confusion_metrics_and_integrity_validation(self) -> None:
        matrix = np.zeros((7, 7), dtype=np.int64)
        target = np.asarray([[0, 1, 255], [6, 2, 3]], dtype=np.uint8)
        prediction = np.asarray([[0, 1, 4], [7, 2, 0]], dtype=np.uint8)
        valid, ignored = confusion_update(matrix, target, prediction)
        self.assertEqual((valid, ignored), (5, 1))
        self.assertEqual(int(matrix.sum()), 5)
        self.assertEqual(matrix[6, 0], 1)
        domain_matrix = np.eye(7, dtype=np.int64)
        overall_matrix = domain_matrix * 2
        report = {
            "overall": {**metrics(overall_matrix), "images": 2, "ignored_pixels": 2},
            "Urban": {**metrics(domain_matrix), "images": 1, "ignored_pixels": 1},
            "Rural": {**metrics(domain_matrix), "images": 1, "ignored_pixels": 1},
        }
        checks = validate_report(report, expected_images=2)
        self.assertTrue(checks["passed"])


if __name__ == "__main__":
    unittest.main()
