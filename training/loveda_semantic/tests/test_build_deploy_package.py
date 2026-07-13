"""Pure-function tests for deployment package construction."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_deploy_package import (  # noqa: E402
    DEFAULT_OUTPUT,
    build_metadata,
    infer_imgsz,
    is_default_output,
    make_parser,
    parse_sha256sums,
    publish_validated_directory,
    replacement_allowed,
    validate_metadata,
)


class BuildDeployPackageTests(unittest.TestCase):
    def test_parser_defaults_to_script_relative_current_deploy(self):
        args = make_parser().parse_args([])
        self.assertEqual(args.output_dir, DEFAULT_OUTPUT)
        self.assertTrue(is_default_output(args.output_dir))
        self.assertTrue(DEFAULT_OUTPUT.is_absolute())

    def test_replacement_policy_is_low_friction_only_for_fixed_current(self):
        self.assertTrue(replacement_allowed(DEFAULT_OUTPUT, force=False))
        self.assertFalse(replacement_allowed(DEFAULT_OUTPUT.parent / "other", force=False))
        self.assertTrue(replacement_allowed(DEFAULT_OUTPUT.parent / "other", force=True))

    def test_validated_directory_replaces_existing_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, staged = root / "deploy", root / ".deploy.building"
            output.mkdir()
            staged.mkdir()
            (output / "marker.txt").write_text("old", encoding="utf-8")
            (staged / "marker.txt").write_text("new", encoding="utf-8")
            publish_validated_directory(staged, output)
            self.assertEqual((output / "marker.txt").read_text(encoding="utf-8"), "new")
            self.assertFalse(staged.exists())

    def test_swap_failure_restores_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, staged = root / "deploy", root / ".deploy.building"
            output.mkdir()
            staged.mkdir()
            (output / "marker.txt").write_text("old", encoding="utf-8")
            (staged / "marker.txt").write_text("new", encoding="utf-8")
            original_replace = Path.replace

            def fail_staged_publish(path: Path, target: Path):
                if path == staged:
                    raise OSError("simulated publish failure")
                return original_replace(path, target)

            with patch.object(Path, "replace", autospec=True, side_effect=fail_staged_publish):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    publish_validated_directory(staged, output)
            self.assertEqual((output / "marker.txt").read_text(encoding="utf-8"), "old")
            self.assertEqual((staged / "marker.txt").read_text(encoding="utf-8"), "new")

    def test_parse_sha256sums_accepts_standard_format(self):
        digest = "a" * 64
        self.assertEqual(parse_sha256sums(f"{digest}  best_dynamic.onnx\n"), {"best_dynamic.onnx": digest})

    def test_parse_sha256sums_rejects_unsafe_or_invalid_lines(self):
        with self.assertRaises(ValueError):
            parse_sha256sums("not-a-digest  best.pt\n")
        with self.assertRaises(ValueError):
            parse_sha256sums(f"{'a' * 64}  ../best.pt\n")

    def test_infer_imgsz_prefers_adjacent_training_args(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            weights = run / "weights"
            weights.mkdir(parents=True)
            pt = weights / "best.pt"
            pt.write_bytes(b"checkpoint")
            (run / "args.yaml").write_text("imgsz: 768\n", encoding="utf-8")
            self.assertEqual(infer_imgsz(pt, {"imgsz": 640})[0], 768)

    def test_infer_imgsz_checkpoint_then_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            pt = Path(directory) / "run/weights/best.pt"
            pt.parent.mkdir(parents=True)
            pt.write_bytes(b"checkpoint")
            self.assertEqual(infer_imgsz(pt, {"imgsz": [640, 640]}), (640, "checkpoint.train_args"))
            self.assertEqual(infer_imgsz(pt, {}), (1024, "fallback"))

    def test_metadata_contract_contains_public_classes_and_dynamic_shape(self):
        metadata = build_metadata("YOLO26s Semantic", "v2", 1024, 17)
        self.assertEqual(validate_metadata(metadata), (1024, 1024))
        self.assertEqual(metadata["output"]["class_id_range"], [0, 6])
        self.assertTrue(metadata["input"]["dynamic_spatial"])
        self.assertEqual([item["id"] for item in metadata["classes"]], list(range(7)))
        self.assertTrue(all(item["display_name"] for item in metadata["classes"]))

    def test_metadata_rejects_invalid_size_and_classes(self):
        metadata = json.loads(json.dumps(build_metadata("model", "v", 1024, 17)))
        metadata["input"]["size"] = [0, 1024]
        with self.assertRaises(ValueError):
            validate_metadata(metadata)
        metadata = build_metadata("model", "v", 1024, 17)
        metadata["classes"][1]["id"] = 3
        with self.assertRaises(ValueError):
            validate_metadata(metadata)


if __name__ == "__main__":
    unittest.main()
