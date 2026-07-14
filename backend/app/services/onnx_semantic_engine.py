"""ONNX Runtime CPU engine for postprocessed class-id map output."""

import hashlib
import json
from pathlib import Path
import time
from typing import Mapping

import numpy as np

from app.services.semantic_inference import normalize_class_map


def parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        digest = parts[0].lower() if parts else ""
        if (
            len(parts) != 2
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise RuntimeError(f"Invalid SHA256SUMS line {line_number}")
        name = parts[1].lstrip("*").replace("\\", "/")
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise RuntimeError(f"Unsafe SHA256SUMS path on line {line_number}")
        checksums[name] = digest
    return checksums


def resolve_expected_sha256(
    deploy_dir: Path,
    filename: str,
    override: str | None,
    metadata: Mapping | None = None,
) -> tuple[str, str]:
    if override and override.strip():
        digest = override.strip().lower()
        source = "environment override"
    else:
        sums_path = deploy_dir / "SHA256SUMS.txt"
        sums = (
            parse_sha256sums(sums_path.read_text(encoding="utf-8"))
            if sums_path.is_file()
            else {}
        )
        digest = sums.get(filename, "")
        source = "SHA256SUMS.txt"
        if not digest and metadata:
            artifact = metadata.get("artifacts", {}).get(filename, {})
            digest = str(artifact.get("sha256", "")).lower()
            source = "metadata.json"
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RuntimeError(f"No valid trusted checksum for {filename}")
    return digest, source


class OnnxSemanticEngine:
    engine = "onnx"
    provider = "CPUExecutionProvider"

    def __init__(
        self,
        deploy_dir: Path,
        expected_sha256: str | None = None,
        verify_sha256: bool = True,
    ):
        import onnxruntime as ort

        self.model_path = deploy_dir / "best_dynamic.onnx"
        metadata_path = deploy_dir / "metadata.json"
        if not self.model_path.is_file() or not metadata_path.is_file():
            raise RuntimeError("Semantic model or metadata is missing")
        raw_metadata = metadata_path.read_bytes()
        self.metadata_sha256 = hashlib.sha256(raw_metadata).hexdigest()
        self.metadata = json.loads(raw_metadata)
        self._validate_metadata()
        self.model_sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        self.checksum_source = None
        if verify_sha256:
            expected, self.checksum_source = resolve_expected_sha256(
                deploy_dir, self.model_path.name, expected_sha256, self.metadata
            )
            if self.model_sha256 != expected:
                raise RuntimeError(
                    f"Semantic ONNX SHA256 mismatch ({self.checksum_source})"
                )
        self.session = ort.InferenceSession(
            str(self.model_path), providers=[self.provider]
        )
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (
            len(inputs) != 1
            or inputs[0].name != "images"
            or inputs[0].type != "tensor(float)"
            or len(inputs[0].shape) != 4
        ):
            raise RuntimeError("Unexpected ONNX input contract")
        if (
            len(outputs) != 1
            or outputs[0].name != "output0"
            or outputs[0].type
            not in {"tensor(int64)", "tensor(float)", "tensor(uint8)"}
            or len(outputs[0].shape) != 3
        ):
            raise RuntimeError("Unexpected ONNX output contract")
        self.input_name, self.output_name = "images", "output0"
        self.runtime_version = ort.__version__
        height, width = self.input_size
        warmup = self.session.run(
            [self.output_name],
            {self.input_name: np.zeros((1, 3, height, width), dtype=np.float32)},
        )[0]
        normalize_class_map(warmup)
        if tuple(warmup.shape) != (1, height, width):
            raise RuntimeError(f"Unexpected warm-up output shape {warmup.shape}")

    def _validate_metadata(self) -> None:
        meta = self.metadata
        input_meta = meta.get("input", {})
        size = input_meta.get("size")
        if (
            meta.get("task") != "semantic-segmentation"
            or input_meta.get("layout") != "NCHW"
            or input_meta.get("color") != "RGB"
            or input_meta.get("dtype") != "float32"
            or input_meta.get("scale") != "0..1"
        ):
            raise RuntimeError("Invalid semantic metadata input contract")
        if (
            not isinstance(size, list)
            or len(size) != 2
            or any(not isinstance(value, int) or value <= 0 for value in size)
        ):
            raise RuntimeError("Invalid semantic metadata input size")
        if [item.get("id") for item in meta.get("classes", [])] != list(range(7)):
            raise RuntimeError("Invalid semantic metadata classes")
        output_meta = meta.get("output")
        if output_meta and (
            output_meta.get("name"),
            output_meta.get("layout"),
            output_meta.get("semantics"),
        ) != ("output0", "NHW", "public-class-id-map"):
            raise RuntimeError("Invalid semantic metadata output contract")
        self.input_size = (size[0], size[1])
        self.model_version = str(meta.get("version") or "baseline-e50-i512-b2")

    def infer(self, tensor: np.ndarray) -> tuple[np.ndarray, int]:
        height, width = self.input_size
        if tensor.shape != (1, 3, height, width) or tensor.dtype != np.float32:
            raise RuntimeError(
                f"Unexpected semantic input tensor {tensor.shape}/{tensor.dtype}"
            )
        started = time.perf_counter()
        output = self.session.run([self.output_name], {self.input_name: tensor})[0]
        elapsed = round((time.perf_counter() - started) * 1000)
        normalize_class_map(output)
        return output, elapsed
