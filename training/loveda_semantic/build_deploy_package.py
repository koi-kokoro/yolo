"""Build and strictly validate a backend-ready LoveDA Semantic deployment package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from common import CLASS_NAMES, PALETTE

ROOT = Path(__file__).resolve().parent
DEFAULT_PT = ROOT / "runs/v2_hr1024_yolo26s_sem_full_e50_b4_m1_20260713T0336Z/weights/best.pt"
DEFAULT_OUTPUT = ROOT / "artifacts/current/deploy"
CHINESE_NAMES = ("背景", "建筑", "道路", "水体", "裸地", "森林", "农田")
PUBLIC_CLASS_COUNT = 7
DEFAULT_IMGSZ = 1024
SEED = 26


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse the conventional '<sha256><two spaces><relative path>' format."""
    result: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64 or any(c not in "0123456789abcdefABCDEF" for c in parts[0]):
            raise ValueError(f"Invalid SHA256SUMS line {number}")
        name = parts[1].lstrip("*").replace("\\", "/")
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"Unsafe SHA256SUMS path on line {number}")
        result[name] = parts[0].lower()
    return result


def _positive_imgsz(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def infer_imgsz(pt_path: Path, checkpoint_args: Mapping[str, Any] | None = None) -> tuple[int, str]:
    """Infer training image size from adjacent args.yaml, then loaded checkpoint args."""
    args_path = pt_path.parent.parent / "args.yaml"
    if args_path.is_file():
        try:
            import yaml
            data = yaml.safe_load(args_path.read_text(encoding="utf-8")) or {}
            value = _positive_imgsz(data.get("imgsz")) if isinstance(data, Mapping) else None
            if value:
                return value, str(args_path.resolve())
        except Exception:
            pass
    value = _positive_imgsz((checkpoint_args or {}).get("imgsz"))
    return (value, "checkpoint.train_args") if value else (DEFAULT_IMGSZ, "fallback")


def build_metadata(model_name: str, model_version: str, imgsz: int, opset: int) -> dict[str, Any]:
    classes = [
        {"id": index, "name": name, "display_name": CHINESE_NAMES[index], "rgb": PALETTE[index].tolist()}
        for index, name in enumerate(CLASS_NAMES)
    ]
    return {
        "schema_version": 1,
        "task": "semantic-segmentation",
        "model": model_name,
        "version": model_version,
        "input": {"name": "images", "layout": "NCHW", "size": [imgsz, imgsz], "dynamic_batch": True,
                  "dynamic_spatial": True, "color": "RGB", "dtype": "float32", "scale": "0..1"},
        "output": {"name": "output0", "layout": "NHW", "dtype": "int64", "semantics": "public-class-id-map",
                   "dynamic_batch": True, "dynamic_spatial": True, "class_id_range": [0, PUBLIC_CLASS_COUNT - 1]},
        "classes": classes,
        "ignore_label": 255,
        "internal_output_note": "Checkpoint class 7 is internal background/ignore and is folded to public class 0 inside ONNX.",
        "training_input_size": [imgsz, imgsz],
        "runtime": {"name": "onnxruntime", "provider": "CPUExecutionProvider", "opset": opset},
    }


def validate_metadata(metadata: Mapping[str, Any]) -> tuple[int, int]:
    if metadata.get("task") != "semantic-segmentation":
        raise ValueError("metadata task must be semantic-segmentation")
    input_meta, output_meta = metadata.get("input", {}), metadata.get("output", {})
    size = input_meta.get("size")
    if (input_meta.get("name"), input_meta.get("layout"), input_meta.get("dtype"), input_meta.get("color"), input_meta.get("scale")) != ("images", "NCHW", "float32", "RGB", "0..1"):
        raise ValueError("invalid metadata input contract")
    if not isinstance(size, list) or len(size) != 2 or any(not isinstance(x, int) or x <= 0 for x in size):
        raise ValueError("invalid metadata input size")
    if (output_meta.get("name"), output_meta.get("layout"), output_meta.get("dtype"), output_meta.get("semantics")) != ("output0", "NHW", "int64", "public-class-id-map"):
        raise ValueError("invalid metadata output contract")
    classes = metadata.get("classes", [])
    if [item.get("id") for item in classes] != list(range(PUBLIC_CLASS_COUNT)) or [item.get("name") for item in classes] != list(CLASS_NAMES):
        raise ValueError("invalid public class contract")
    for item in classes:
        if not isinstance(item.get("display_name"), str) or len(item.get("rgb", [])) != 3 or any(not isinstance(x, int) or not 0 <= x <= 255 for x in item["rgb"]):
            raise ValueError("invalid class display name or RGB")
    return int(size[0]), int(size[1])


def environment_info(torch_module: Any) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ("torch", "ultralytics", "onnx", "onnxruntime", "numpy", "PyYAML"):
        try:
            packages[name] = package_version(name)
        except PackageNotFoundError:
            packages[name] = None
    cuda = bool(torch_module.cuda.is_available())
    return {"generated_at": utc_now(), "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "cuda_available": cuda, "cuda_version": torch_module.version.cuda,
            "gpu": torch_module.cuda.get_device_name(0) if cuda else None, "packages": packages}


def _extract_logits(raw: Any, torch_module: Any) -> Any:
    if isinstance(raw, (tuple, list)):
        raw = raw[0]
    if not torch_module.is_tensor(raw) or raw.ndim != 4 or raw.shape[1] < PUBLIC_CLASS_COUNT:
        shape = getattr(raw, "shape", None)
        raise RuntimeError(f"Checkpoint is not a semantic logits model; got {type(raw).__name__} shape={shape}")
    return raw


def _checkpoint_args(yolo: Any) -> Mapping[str, Any]:
    for candidate in (getattr(yolo, "ckpt", None), getattr(yolo.model, "args", None)):
        if isinstance(candidate, Mapping):
            args = candidate.get("train_args", candidate)
            if isinstance(args, Mapping):
                return args
    return {}


def _validate_checkpoint_names(yolo: Any) -> None:
    names = getattr(yolo.model, "names", None)
    if isinstance(names, Mapping):
        ordered = [str(names[index]) for index in sorted(names)]
    elif isinstance(names, (list, tuple)):
        ordered = [str(name) for name in names]
    else:
        raise RuntimeError("Checkpoint has no class names")
    if ordered[:PUBLIC_CLASS_COUNT] != list(CLASS_NAMES) or len(ordered) not in (PUBLIC_CLASS_COUNT, PUBLIC_CLASS_COUNT + 1):
        raise RuntimeError(f"Checkpoint class contract mismatch: {ordered}")


def export_and_validate(yolo: Any, onnx_path: Path, imgsz: int, device: str, opset: int) -> dict[str, Any]:
    import onnx
    import onnxruntime as ort
    import torch
    import torch.nn.functional as functional

    class BackendClassMap(torch.nn.Module):
        def __init__(self, semantic_model: Any):
            super().__init__()
            self.semantic_model = semantic_model

        def forward(self, images: Any) -> Any:
            logits = _extract_logits(self.semantic_model(images), torch)
            logits = functional.interpolate(logits, size=images.shape[-2:], mode="bilinear", align_corners=False)
            class_map = logits.argmax(dim=1)
            return torch.where(class_map == PUBLIC_CLASS_COUNT, torch.zeros_like(class_map), class_map)

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    resolved_device = torch.device(device)
    yolo.model.to(resolved_device).eval()
    wrapper = BackendClassMap(yolo.model).to(resolved_device).eval()
    sample = torch.rand((1, 3, imgsz, imgsz), dtype=torch.float32, device=resolved_device)
    with torch.no_grad():
        pt_map = wrapper(sample).detach().cpu().numpy()
    if pt_map.shape != (1, imgsz, imgsz) or pt_map.min() < 0 or pt_map.max() >= PUBLIC_CLASS_COUNT:
        raise RuntimeError(f"Invalid PT class map shape/range: {pt_map.shape}, {pt_map.min()}..{pt_map.max()}")

    torch.onnx.export(wrapper, sample, str(onnx_path), input_names=["images"], output_names=["output0"],
                      opset_version=opset, do_constant_folding=True, dynamo=False,
                      dynamic_axes={"images": {0: "batch", 2: "height", 3: "width"},
                                    "output0": {0: "batch", 1: "height", 2: "width"}})
    if not onnx_path.is_file() or onnx_path.stat().st_size == 0:
        raise RuntimeError("ONNX export did not create a non-empty file")
    graph = onnx.load(str(onnx_path))
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != "images" or inputs[0].type != "tensor(float)" or len(inputs[0].shape) != 4:
        raise RuntimeError(f"Unexpected ONNX inputs: {[(x.name, x.type, x.shape) for x in inputs]}")
    if len(outputs) != 1 or outputs[0].name != "output0" or outputs[0].type != "tensor(int64)" or len(outputs[0].shape) != 3:
        raise RuntimeError(f"Unexpected ONNX outputs: {[(x.name, x.type, x.shape) for x in outputs]}")
    ort_map = session.run(["output0"], {"images": sample.detach().cpu().numpy()})[0]
    if ort_map.shape != (1, imgsz, imgsz) or ort_map.ndim != 3:
        raise RuntimeError(f"Unexpected ONNX output shape: {ort_map.shape}")
    if not np.issubdtype(ort_map.dtype, np.integer) or ort_map.min() < 0 or ort_map.max() >= PUBLIC_CLASS_COUNT:
        raise RuntimeError(f"Invalid ONNX class map dtype/range: {ort_map.dtype}, {ort_map.min()}..{ort_map.max()}")
    agreement = float(np.mean(pt_map == ort_map))
    if agreement < 0.999999:
        raise RuntimeError(f"PT/ONNX class-map agreement too low: {agreement:.9f}")

    # A second shape proves that spatial axes are genuinely dynamic, not only annotated.
    probe_h, probe_w = max(32, imgsz - 32), imgsz
    dynamic_map = session.run(["output0"], {"images": np.zeros((1, 3, probe_h, probe_w), dtype=np.float32)})[0]
    if dynamic_map.shape != (1, probe_h, probe_w) or dynamic_map.min() < 0 or dynamic_map.max() >= PUBLIC_CLASS_COUNT:
        raise RuntimeError(f"Dynamic-spatial validation failed: {dynamic_map.shape}")
    return {"onnx_checker": "passed", "provider": "CPUExecutionProvider", "input_name": "images",
            "input_dtype": "float32", "output_name": "output0", "output_dtype": "int64",
            "nominal_input_shape": [1, 3, imgsz, imgsz], "nominal_output_shape": list(ort_map.shape),
            "dynamic_probe_input_shape": [1, 3, probe_h, probe_w], "dynamic_probe_output_shape": list(dynamic_map.shape),
            "public_class_id_range_observed": [int(ort_map.min()), int(ort_map.max())],
            "pt_onnx_class_map_agreement": agreement}


def _model_name(yolo: Any) -> str:
    trained_from = str(_checkpoint_args(yolo).get("model", ""))
    stem = Path(trained_from).stem.lower()
    if stem.startswith("yolo") and stem.endswith("-sem"):
        base = stem[:-4]
        return f"YOLO{base[4:-1]}{base[-1]} Semantic"
    yaml_data = getattr(yolo.model, "yaml", {})
    candidate = yaml_data.get("model", "") if isinstance(yaml_data, Mapping) else ""
    return str(candidate or yolo.model.__class__.__name__)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def is_default_output(output_dir: Path) -> bool:
    """Return whether output_dir is the script-relative fixed current deployment path."""
    return output_dir.expanduser().resolve() == DEFAULT_OUTPUT.resolve()


def replacement_allowed(output_dir: Path, force: bool) -> bool:
    """The fixed current package is replaceable by default; custom outputs require --force."""
    return force or is_default_output(output_dir)


def publish_validated_directory(temp_dir: Path, output_dir: Path) -> None:
    """Publish a fully validated directory and restore the previous package on swap failure."""
    backup_dir: Path | None = None
    try:
        if output_dir.exists():
            backup_dir = output_dir.with_name(f".{output_dir.name}.backup-{os.getpid()}")
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            output_dir.replace(backup_dir)
        temp_dir.replace(output_dir)
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
            backup_dir.replace(output_dir)
        raise
    if backup_dir is not None:
        shutil.rmtree(backup_dir)


def build_package(pt_path: Path, output_dir: Path, imgsz_override: int | None, model_version: str,
                  device: str, opset: int, force: bool) -> Path:
    import torch
    from ultralytics import YOLO

    pt_path, output_dir = pt_path.expanduser().resolve(), output_dir.expanduser().resolve()
    if not pt_path.is_file() or pt_path.stat().st_size == 0:
        raise FileNotFoundError(f"PT checkpoint is missing or empty: {pt_path}")
    if output_dir.exists() and not replacement_allowed(output_dir, force):
        raise FileExistsError(
            f"Non-default output directory exists; pass --force to replace after successful validation: {output_dir}"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.building-", dir=output_dir.parent))
    started_at = utc_now()
    try:
        yolo = YOLO(str(pt_path), task="semantic")
        if getattr(yolo, "task", None) != "semantic":
            raise RuntimeError(f"Expected semantic checkpoint, got task={getattr(yolo, 'task', None)!r}")
        _validate_checkpoint_names(yolo)
        inferred_imgsz, imgsz_source = infer_imgsz(pt_path, _checkpoint_args(yolo))
        imgsz = imgsz_override or inferred_imgsz
        if imgsz <= 0:
            raise ValueError("--imgsz must be positive")
        metadata = build_metadata(_model_name(yolo), model_version, imgsz, opset)
        validate_metadata(metadata)

        copied_pt = temp_dir / "best.pt"
        shutil.copy2(pt_path, copied_pt)
        args_path = pt_path.parent.parent / "args.yaml"
        if args_path.is_file() and args_path.stat().st_size:
            shutil.copy2(args_path, temp_dir / "training_args.yaml")
        validation = export_and_validate(yolo, temp_dir / "best_dynamic.onnx", imgsz, device, opset)
        metadata["artifacts"] = {"best.pt": {"sha256": sha256_file(copied_pt)},
                                 "best_dynamic.onnx": {"sha256": sha256_file(temp_dir / "best_dynamic.onnx")}}
        _write_json(temp_dir / "metadata.json", metadata)
        _write_json(temp_dir / "environment.json", environment_info(torch))
        manifest = {"status": "success", "schema_version": 1, "started_at": started_at, "completed_at": utc_now(),
                    "source_pt": str(pt_path), "output_dir": str(output_dir), "parameters": {"imgsz": imgsz,
                    "imgsz_source": "cli" if imgsz_override else imgsz_source, "version": model_version,
                    "device": device, "opset": opset, "force": force}, "validation": validation}
        _write_json(temp_dir / "manifest.json", manifest)
        checksum_files = ["best.pt", "best_dynamic.onnx", "metadata.json", "environment.json", "manifest.json"]
        if (temp_dir / "training_args.yaml").is_file():
            checksum_files.append("training_args.yaml")
        (temp_dir / "SHA256SUMS.txt").write_text("".join(f"{sha256_file(temp_dir / name)}  {name}\n" for name in checksum_files), encoding="utf-8")
        parsed = parse_sha256sums((temp_dir / "SHA256SUMS.txt").read_text(encoding="utf-8"))
        for name, expected in parsed.items():
            if sha256_file(temp_dir / name) != expected:
                raise RuntimeError(f"Final checksum verification failed: {name}")
        required = ("best.pt", "best_dynamic.onnx", "metadata.json", "environment.json", "manifest.json", "SHA256SUMS.txt")
        if any(not (temp_dir / name).is_file() or (temp_dir / name).stat().st_size == 0 for name in required):
            raise RuntimeError("Deployment package is incomplete")

        publish_validated_directory(temp_dir, output_dir)
        return output_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a strictly validated LoveDA Semantic backend ONNX deployment package")
    parser.add_argument("--pt", type=Path, default=DEFAULT_PT, help="Semantic best.pt checkpoint")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT,
        help=f"Deployment output directory (default: script-relative {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--imgsz", type=int, default=None, help="Override training input size; otherwise infer args.yaml/checkpoint, then 1024")
    parser.add_argument("--version", default=None, help="Deployed model version; defaults to the run directory name")
    parser.add_argument("--device", default="cpu", help="Torch export/comparison device, for example cpu or cuda:0")
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument(
        "--force", action="store_true",
        help="Required to replace an existing non-default output; current/deploy is safely replaced after validation",
    )
    return parser


def main() -> None:
    args = make_parser().parse_args()
    version = args.version or args.pt.expanduser().resolve().parent.parent.name
    result = build_package(args.pt, args.output_dir, args.imgsz, version, args.device, args.opset, args.force)
    print(json.dumps({"status": "success", "deploy_dir": str(result), "manifest": str(result / "manifest.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
