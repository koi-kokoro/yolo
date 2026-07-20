"""模型评估 Agent 使用的只读工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from app.services.model_management import model_management_service
from app.services.semantic_model_ops import DISPLAY_NAMES, semantic_model_ops

_DOMAIN_NAMES = {"overall": "总体", "Urban": "城市", "Rural": "乡村"}


def collect_evaluation_snapshot() -> dict[str, Any]:
    """读取缓存评估结果及模型概况，不触发重新评估。"""
    warnings: list[str] = []
    try:
        evaluation = semantic_model_ops.evaluate(force=False)
    except Exception as exc:
        # 当前部署目录可能是容器/主机链接；不可访问时读取前端已发布的可信副本。
        published = (
            Path(__file__).resolve().parents[4]
            / "frontend"
            / "public"
            / "model-dashboard"
            / "v2_evaluation_metrics.json"
        )
        try:
            report = json.loads(published.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fallback_exc:
            raise RuntimeError("没有可用的缓存评估指标") from fallback_exc
        warnings.append(
            f"部署缓存不可访问，已使用已发布评估指标副本（{type(exc).__name__}）"
        )
        evaluation = {"source": "published_cache", "report": report}
    report = evaluation.get("report") or {}
    safe_report: dict[str, Any] = {}
    for domain, values in report.items():
        if not isinstance(values, dict):
            continue
        safe_report[domain] = {
            "display_name": _DOMAIN_NAMES.get(domain, str(domain)),
            "images": values.get("images"),
            "valid_pixels": values.get("valid_pixels"),
            "miou": values.get("miou"),
            "pixel_accuracy": values.get("pixel_accuracy"),
            "mean_dice_f1": values.get("mean_dice_f1"),
            "per_class": [
                {
                    key: (
                        row.get("display_name")
                        or DISPLAY_NAMES.get(str(row.get("class_name")), row.get("class_name"))
                        if key == "display_name"
                        else row.get(key)
                    )
                    for key in (
                        "class_id",
                        "class_name",
                        "display_name",
                        "iou",
                        "dice_f1",
                        "precision",
                        "recall",
                        "support_pixels",
                    )
                }
                for row in (values.get("per_class") or [])
                if isinstance(row, dict)
            ],
        }

    try:
        model_items = model_management_service.models()
    except Exception as exc:
        model_items = []
        warnings.append(f"模型概况暂不可用（{type(exc).__name__}）")
    models = []
    for model in model_items:
        models.append(
            {
                key: model.get(key)
                for key in (
                    "id",
                    "display_name",
                    "source_type",
                    "lifecycle_status",
                    "deployment_status",
                    "latest_miou",
                    "best_miou",
                    "pixel_accuracy",
                    "current_epoch",
                    "epoch_target",
                    "progress",
                    "stale",
                    "warnings",
                )
            }
        )
    return {
        "source": evaluation.get("source", "cached"),
        "warnings": [
            item for item in [evaluation.get("warning"), *warnings] if item
        ],
        "report": safe_report,
        "models": models,
    }


@tool
def get_model_evaluation() -> str:
    """读取当前 LoveDA 模型的缓存评估指标和安全模型概况。"""
    return json.dumps(collect_evaluation_snapshot(), ensure_ascii=False, default=str)
