"""Agent 数据导出的用户隔离存储与 CSV/JSON 序列化。"""

from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings

_SAFE_FILENAME = re.compile(r"^[a-z0-9_\-]+\.(?:json|csv)$")


class AgentExportService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or (settings.chat_upload_path.parent / "exports")).resolve()

    def _user_dir(self, user_id: int) -> Path:
        path = (self.root / str(int(user_id))).resolve()
        if path.parent != self.root:
            raise ValueError("无效用户目录")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_evaluation_csv(path: Path, data: dict[str, Any]) -> None:
        fields = [
            "domain",
            "class_name",
            "miou",
            "pixel_accuracy",
            "mean_dice_f1",
            "iou",
            "dice_f1",
            "precision",
            "recall",
            "support_pixels",
        ]
        with path.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for domain, values in (data.get("report") or {}).items():
                writer.writerow(
                    {
                        "domain": domain,
                        "miou": values.get("miou"),
                        "pixel_accuracy": values.get("pixel_accuracy"),
                        "mean_dice_f1": values.get("mean_dice_f1"),
                    }
                )
                for item in values.get("per_class") or []:
                    writer.writerow(
                        {
                            "domain": domain,
                            "class_name": item.get("display_name") or item.get("class_name"),
                            **{key: item.get(key) for key in fields[5:]},
                        }
                    )

    @staticmethod
    def _write_patrol_csv(path: Path, data: dict[str, Any]) -> None:
        fields = [
            "section",
            "date",
            "name",
            "display_name",
            "value",
            "unit",
            "ratio",
            "task_count",
            "image_count",
            "segmented_pixels",
            "status",
            "scene_name",
            "task_type",
            "inference_time_ms",
            "top_class",
            "anomaly_score",
            "reliability_score",
            "review_level",
            "note",
        ]
        with path.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            units = {
                "tasks": "次",
                "completed_tasks": "次",
                "failed_tasks": "次",
                "images": "张",
                "segmented_pixels": "像素",
                "semantic_tasks": "次",
                "semantic_samples": "张",
                "timed_tasks": "次",
                "average_inference_time_ms_per_image": "毫秒/张",
                "active_days": "天",
                "completion_rate": "比例",
            }
            for key, value in (data.get("summary") or {}).items():
                writer.writerow(
                    {
                        "section": "summary",
                        "name": key,
                        "value": value,
                        "unit": units.get(key),
                    }
                )
            for key, value in (
                data.get("comparison_with_previous_period") or {}
            ).items():
                writer.writerow(
                    {
                        "section": "comparison",
                        "name": key,
                        "value": value,
                        "unit": "%",
                    }
                )
            for item in data.get("land_cover") or []:
                writer.writerow(
                    {
                        "section": "land_cover",
                        "name": item.get("class_name"),
                        "display_name": item.get("display_name"),
                        "value": item.get("pixel_count"),
                        "unit": "像素",
                        "ratio": item.get("ratio"),
                    }
                )
            for item in data.get("daily_trend") or []:
                writer.writerow(
                    {
                        "section": "daily_trend",
                        **{
                            key: item.get(key)
                            for key in (
                                "date",
                                "task_count",
                                "image_count",
                                "segmented_pixels",
                            )
                        },
                    }
                )
            for item in data.get("recent_tasks") or []:
                writer.writerow(
                    {
                        "section": "recent_tasks",
                        "date": item.get("created_at"),
                        "status": item.get("status"),
                        "scene_name": item.get("scene_name"),
                        "task_type": item.get("task_type"),
                        "image_count": item.get("image_count"),
                        "segmented_pixels": item.get("segmented_pixels"),
                        "inference_time_ms": item.get("inference_time_ms"),
                        "top_class": item.get("top_class"),
                        "ratio": item.get("top_class_ratio"),
                        "anomaly_score": item.get("anomaly_score"),
                        "reliability_score": item.get("reliability_score"),
                        "review_level": item.get("review_level"),
                    }
                )
            for warning in (data.get("data_quality") or {}).get("warnings", []):
                writer.writerow({"section": "data_quality", "note": warning})
            writer.writerow(
                {"section": "conclusion", "note": data.get("conclusion")}
            )

    def create(
        self,
        user_id: int,
        data_type: str,
        file_format: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if data_type not in {"evaluation", "patrol"}:
            raise ValueError("不支持的导出数据类型")
        if file_format not in {"json", "csv"}:
            raise ValueError("不支持的导出格式")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{data_type}_{stamp}_{uuid.uuid4().hex[:8]}.{file_format}"
        path = self._user_dir(user_id) / filename
        if file_format == "json":
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        elif data_type == "evaluation":
            self._write_evaluation_csv(path, data)
        else:
            self._write_patrol_csv(path, data)
        return {
            "filename": filename,
            "format": file_format,
            "data_type": data_type,
            "size_bytes": path.stat().st_size,
            "download_url": f"/api/chat/exports/{filename}",
        }

    def resolve(self, user_id: int, filename: str) -> Path:
        if not _SAFE_FILENAME.fullmatch(filename):
            raise FileNotFoundError(filename)
        user_dir = self._user_dir(user_id)
        path = (user_dir / filename).resolve()
        if path.parent != user_dir or not path.is_file():
            raise FileNotFoundError(filename)
        return path


agent_export_service = AgentExportService()
