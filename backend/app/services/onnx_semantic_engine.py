"""ONNX Runtime CPU engine for postprocessed class-id map output."""

import hashlib
import json
from pathlib import Path
import time

import numpy as np

from app.services.semantic_inference import normalize_class_map


class OnnxSemanticEngine:
    engine = "onnx"
    provider = "CPUExecutionProvider"

    def __init__(self, deploy_dir: Path, expected_sha256: str, verify_sha256: bool = True):
        import onnxruntime as ort

        self.model_path = deploy_dir / "best_dynamic.onnx"
        metadata_path = deploy_dir / "metadata.json"
        if not self.model_path.is_file() or not metadata_path.is_file():
            raise RuntimeError("Semantic model or metadata is missing")
        model_bytes = self.model_path.read_bytes()
        self.model_sha256 = hashlib.sha256(model_bytes).hexdigest()
        if verify_sha256 and self.model_sha256 != expected_sha256:
            raise RuntimeError("Semantic ONNX SHA256 mismatch")
        raw_metadata = metadata_path.read_bytes()
        self.metadata_sha256 = hashlib.sha256(raw_metadata).hexdigest()
        self.metadata = json.loads(raw_metadata)
        self._validate_metadata()
        self.session = ort.InferenceSession(str(self.model_path), providers=[self.provider])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or inputs[0].name != "images" or inputs[0].type != "tensor(float)" or len(inputs[0].shape) != 4:
            raise RuntimeError("Unexpected ONNX input contract")
        if len(outputs) != 1 or outputs[0].name != "output0" or len(outputs[0].shape) != 3:
            raise RuntimeError("Unexpected ONNX output contract")
        self.input_name, self.output_name = "images", "output0"
        self.runtime_version = ort.__version__
        warmup = self.session.run([self.output_name], {self.input_name: np.zeros((1, 3, 512, 512), dtype=np.float32)})[0]
        normalize_class_map(warmup)
        if tuple(warmup.shape) != (1, 512, 512):
            raise RuntimeError(f"Unexpected warm-up output shape {warmup.shape}")

    def _validate_metadata(self) -> None:
        meta = self.metadata
        if meta.get("task") != "semantic-segmentation" or meta.get("input", {}).get("layout") != "NCHW" or meta.get("input", {}).get("size") != [512, 512] or meta.get("input", {}).get("color") != "RGB" or meta.get("input", {}).get("dtype") != "float32" or meta.get("input", {}).get("scale") != "0..1":
            raise RuntimeError("Invalid semantic metadata input contract")
        if [item.get("id") for item in meta.get("classes", [])] != list(range(7)):
            raise RuntimeError("Invalid semantic metadata classes")

    def infer(self, tensor: np.ndarray) -> tuple[np.ndarray, int]:
        started = time.perf_counter()
        output = self.session.run([self.output_name], {self.input_name: tensor})[0]
        elapsed = round((time.perf_counter() - started) * 1000)
        normalize_class_map(output)
        return output, elapsed
