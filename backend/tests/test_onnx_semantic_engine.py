"""Contract tests for semantic package metadata and checksums without a real model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.config.settings import Settings
from app.services.onnx_semantic_engine import OnnxSemanticEngine, parse_sha256sums, resolve_expected_sha256
from app.services import semantic_runtime as semantic_runtime_module


def metadata(size=1024, version="v2"):
    names = ("background", "building", "road", "water", "barren", "forest", "agricultural")
    return {"task": "semantic-segmentation", "model": "YOLO26s Semantic", "version": version,
            "input": {"layout": "NCHW", "size": [size, size], "color": "RGB", "dtype": "float32", "scale": "0..1"},
            "output": {"name": "output0", "layout": "NHW", "semantics": "public-class-id-map"},
            "classes": [{"id": index, "name": name, "rgb": [index, index, index]} for index, name in enumerate(names)]}


def test_checksum_parser_and_resolution_priority(tmp_path: Path):
    model = tmp_path / "best_dynamic.onnx"
    model.write_bytes(b"model")
    actual = hashlib.sha256(b"model").hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(f"{actual}  best_dynamic.onnx\n", encoding="utf-8")
    assert parse_sha256sums((tmp_path / "SHA256SUMS.txt").read_text())["best_dynamic.onnx"] == actual
    assert resolve_expected_sha256(tmp_path, "best_dynamic.onnx", None, {}) == (actual, "SHA256SUMS.txt")
    override = "b" * 64
    assert resolve_expected_sha256(tmp_path, "best_dynamic.onnx", override, {}) == (override, "environment override")


def test_default_settings_do_not_override_onnx_checksum(monkeypatch):
    monkeypatch.delenv("SEMANTIC_ONNX_SHA256", raising=False)
    assert Settings(_env_file=None).SEMANTIC_ONNX_SHA256 is None


def test_runtime_passes_none_and_uses_package_checksum(tmp_path: Path, monkeypatch):
    digest = "d" * 64
    (tmp_path / "SHA256SUMS.txt").write_text(f"{digest}  best_dynamic.onnx\n", encoding="utf-8")
    observed = {}

    def engine_factory(deploy_dir, expected_sha256, verify_sha256):
        observed["expected_sha256"] = expected_sha256
        observed["resolved"] = resolve_expected_sha256(deploy_dir, "best_dynamic.onnx", expected_sha256)
        return SimpleNamespace()

    monkeypatch.setattr(semantic_runtime_module.settings, "SEMANTIC_ONNX_SHA256", None)
    monkeypatch.setattr(semantic_runtime_module.settings, "SEMANTIC_DEPLOY_DIR", str(tmp_path))
    monkeypatch.setattr(semantic_runtime_module, "OnnxSemanticEngine", engine_factory)
    runtime = semantic_runtime_module.SemanticRuntime()
    try:
        runtime.start()
        assert runtime.ready
        assert observed == {"expected_sha256": None, "resolved": (digest, "SHA256SUMS.txt")}
    finally:
        runtime.shutdown()


def test_checksum_resolution_can_use_metadata(tmp_path: Path):
    digest = "c" * 64
    value = {"artifacts": {"best_dynamic.onnx": {"sha256": digest}}}
    assert resolve_expected_sha256(tmp_path, "best_dynamic.onnx", None, value) == (digest, "metadata.json")


def test_metadata_validation_uses_dynamic_size_and_version():
    engine = object.__new__(OnnxSemanticEngine)
    engine.metadata = metadata(1024, "release-2")
    engine._validate_metadata()
    assert engine.input_size == (1024, 1024)
    assert engine.model_version == "release-2"


def test_metadata_validation_rejects_bad_size():
    engine = object.__new__(OnnxSemanticEngine)
    engine.metadata = metadata()
    engine.metadata["input"]["size"] = [512]
    with pytest.raises(RuntimeError):
        engine._validate_metadata()


def test_infer_enforces_engine_input_size():
    engine = object.__new__(OnnxSemanticEngine)
    engine.input_size = (640, 640)
    engine.input_name = "images"
    engine.output_name = "output0"
    engine.session = SimpleNamespace(run=lambda *_args: [np.zeros((1, 640, 640), dtype=np.int64)])
    output, _ = engine.infer(np.zeros((1, 3, 640, 640), dtype=np.float32))
    assert output.shape == (1, 640, 640)
    with pytest.raises(RuntimeError):
        engine.infer(np.zeros((1, 3, 512, 512), dtype=np.float32))
