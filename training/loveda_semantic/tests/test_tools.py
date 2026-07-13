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


if __name__ == "__main__":
    unittest.main()
