"""将检测任务转换为面向业务的巡查导出数据。"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.entity.db_models import DetectionTask

DISPLAY_NAMES = {
    "background": "背景",
    "building": "建筑",
    "road": "道路",
    "water": "水体",
    "barren": "裸地",
    "forest": "森林",
    "agricultural": "农田",
}


def _growth(current: int | float, previous: int | float) -> float | None:
    """上一周期无数据时返回 null，避免制造 100% 的伪增长。"""
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _semantic_samples(task: DetectionTask) -> list[dict[str, Any]]:
    payload = task.semantic_metrics if isinstance(task.semantic_metrics, dict) else {}
    return [item for item in payload.get("samples", []) if isinstance(item, dict)]


def _task_semantic_summary(task: DetectionTask) -> dict[str, Any]:
    samples = _semantic_samples(task)
    pixels_by_class = {name: 0 for name in DISPLAY_NAMES}
    segmented_pixels = 0
    anomaly_scores: list[float] = []
    reliability_scores: list[float] = []
    review_levels: list[str] = []
    for sample in samples:
        total = max(0, int(sample.get("total_pixels") or 0))
        segmented_pixels += total
        ratios = sample.get("class_ratios") or {}
        for name in pixels_by_class:
            pixels_by_class[name] += max(
                0, int(round(float(ratios.get(name) or 0.0) * total))
            )
        if sample.get("anomaly_score") is not None:
            anomaly_scores.append(float(sample["anomaly_score"]))
        if sample.get("reliability_score") is not None:
            reliability_scores.append(float(sample["reliability_score"]))
        if sample.get("review_level"):
            review_levels.append(str(sample["review_level"]))

    ranked = sorted(pixels_by_class.items(), key=lambda item: item[1], reverse=True)
    top_name, top_pixels = ranked[0] if ranked and ranked[0][1] > 0 else (None, 0)
    review_rank = {"low": 1, "medium": 2, "high": 3}
    review_level = max(review_levels, key=lambda item: review_rank.get(item, 0), default=None)
    return {
        "sample_count": len(samples),
        "segmented_pixels": segmented_pixels,
        "pixels_by_class": pixels_by_class,
        "top_class": DISPLAY_NAMES.get(top_name) if top_name else None,
        "top_class_ratio": round(top_pixels / segmented_pixels, 6)
        if segmented_pixels
        else None,
        "average_anomaly_score": round(sum(anomaly_scores) / len(anomaly_scores), 1)
        if anomaly_scores
        else None,
        "average_reliability_score": round(
            sum(reliability_scores) / len(reliability_scores), 1
        )
        if reliability_scores
        else None,
        "review_level": review_level,
    }


class PatrolExportService:
    @staticmethod
    def _summary(tasks: list[DetectionTask]) -> dict[str, Any]:
        semantic = [_task_semantic_summary(task) for task in tasks]
        positive_time = [
            task for task in tasks if float(task.total_inference_time or 0) > 0
        ]
        timed_images = sum(max(1, int(task.total_images or 0)) for task in positive_time)
        total_time = sum(float(task.total_inference_time or 0) for task in positive_time)
        return {
            "tasks": len(tasks),
            "completed_tasks": sum(task.status == "completed" for task in tasks),
            "failed_tasks": sum(task.status == "failed" for task in tasks),
            "images": sum(int(task.total_images or 0) for task in tasks),
            "segmented_pixels": sum(item["segmented_pixels"] for item in semantic),
            "semantic_tasks": sum(bool(item["sample_count"]) for item in semantic),
            "semantic_samples": sum(item["sample_count"] for item in semantic),
            "timed_tasks": len(positive_time),
            "average_inference_time_ms_per_image": round(total_time / timed_images, 2)
            if timed_images
            else None,
        }

    @classmethod
    def compose(
        cls,
        current_tasks: list[DetectionTask],
        previous_tasks: list[DetectionTask],
        days: int,
        now: datetime,
    ) -> dict[str, Any]:
        today = now.date()
        start_date = today - timedelta(days=days - 1)
        current = cls._summary(current_tasks)
        previous = cls._summary(previous_tasks)

        class_pixels = {name: 0 for name in DISPLAY_NAMES}
        semantic_by_task: dict[int, dict[str, Any]] = {}
        for task in current_tasks:
            summary = _task_semantic_summary(task)
            semantic_by_task[id(task)] = summary
            for name, value in summary["pixels_by_class"].items():
                class_pixels[name] += value

        class_total = sum(class_pixels.values())
        land_cover = [
            {
                "class_name": name,
                "display_name": DISPLAY_NAMES[name],
                "pixel_count": pixels,
                "ratio": round(pixels / class_total, 6) if class_total else None,
            }
            for name, pixels in sorted(
                class_pixels.items(), key=lambda item: item[1], reverse=True
            )
        ]

        object_tasks = [
            task
            for task in current_tasks
            if task.scene
            and (
                task.scene.name == "dior_facility_detection"
                or task.scene.category == "object_detection"
            )
        ]
        object_counts: dict[tuple[str, str], int] = {}
        confidences: list[float] = []
        object_detections: list[dict[str, Any]] = []
        for task in object_tasks:
            for result in task.results or []:
                key = (result.class_name, result.class_name_cn or result.class_name)
                object_counts[key] = object_counts.get(key, 0) + 1
                confidences.append(float(result.confidence))
                object_detections.append(
                    {
                        "task_id": task.id,
                        "created_at": task.created_at.isoformat()
                        if task.created_at
                        else None,
                        "class_name": result.class_name,
                        "class_name_cn": result.class_name_cn,
                        "class_id": result.class_id,
                        "confidence": round(float(result.confidence), 6),
                        "bbox": result.bbox,
                        "image_width": result.image_width,
                        "image_height": result.image_height,
                    }
                )
        object_class_distribution = [
            {
                "class_name": name,
                "display_name": display_name,
                "count": count,
                "ratio": round(count / len(object_detections), 6)
                if object_detections
                else None,
            }
            for (name, display_name), count in sorted(
                object_counts.items(), key=lambda item: item[1], reverse=True
            )
        ]
        object_detection = {
            "tasks": len(object_tasks),
            "images": sum(int(task.total_images or 0) for task in object_tasks),
            "total_objects": len(object_detections),
            "class_distribution": object_class_distribution,
            "confidence": {
                "average": round(sum(confidences) / len(confidences), 6)
                if confidences
                else None,
                "minimum": round(min(confidences), 6) if confidences else None,
                "maximum": round(max(confidences), 6) if confidences else None,
            },
        }

        daily = {
            (start_date + timedelta(days=index)).isoformat(): {
                "date": (start_date + timedelta(days=index)).isoformat(),
                "task_count": 0,
                "image_count": 0,
                "segmented_pixels": 0,
            }
            for index in range(days)
        }
        for task in current_tasks:
            if not task.created_at:
                continue
            key = task.created_at.date().isoformat()
            if key not in daily:
                continue
            daily[key]["task_count"] += 1
            daily[key]["image_count"] += int(task.total_images or 0)
            daily[key]["segmented_pixels"] += semantic_by_task[id(task)][
                "segmented_pixels"
            ]
        daily_trend = list(daily.values())
        active_days = sum(item["task_count"] > 0 for item in daily_trend)
        peak = (
            max(daily_trend, key=lambda item: item["task_count"], default=None)
            if current["tasks"]
            else None
        )

        recent_tasks = []
        for task in sorted(
            current_tasks, key=lambda item: item.created_at or datetime.min, reverse=True
        )[:10]:
            semantic = semantic_by_task[id(task)]
            recent_tasks.append(
                {
                    "task_id": task.id,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "task_type": task.task_type,
                    "status": task.status,
                    "scene_name": task.scene.display_name if task.scene else None,
                    "image_count": int(task.total_images or 0),
                    "segmented_pixels": semantic["segmented_pixels"] or None,
                    "inference_time_ms": float(task.total_inference_time)
                    if task.total_inference_time
                    else None,
                    "top_class": semantic["top_class"],
                    "top_class_ratio": semantic["top_class_ratio"],
                    "anomaly_score": semantic["average_anomaly_score"],
                    "reliability_score": semantic["average_reliability_score"],
                    "review_level": semantic["review_level"],
                }
            )

        warnings: list[str] = []
        missing_semantic = max(
            0, current["tasks"] - current["semantic_tasks"] - len(object_tasks)
        )
        missing_time = current["tasks"] - current["timed_tasks"]
        if missing_semantic:
            warnings.append(
                f"{missing_semantic} 条历史任务缺少类别统计，未纳入地物分布"
            )
        if missing_time:
            warnings.append(
                f"{missing_time} 条历史任务缺少有效推理耗时，平均耗时仅基于可用记录"
            )
        if previous["tasks"] == 0:
            warnings.append("上一周期没有任务，环比指标记为 null")

        dominant = next(
            (
                item
                for item in land_cover
                if item["class_name"] != "background" and item["pixel_count"] > 0
            ),
            None,
        )
        if current["tasks"] == 0:
            conclusion = "本周期没有巡查任务。"
        else:
            conclusion = (
                f"本周期完成 {current['completed_tasks']} 个任务，处理 {current['images']} 张影像，"
                f"共有 {active_days} 个活跃巡查日。"
            )
            if dominant:
                conclusion += (
                    f"有类别统计的数据中，除背景外以{dominant['display_name']}为主"
                    f"（占全部分割像素 {dominant['ratio'] * 100:.2f}%）。"
                )
            if object_detection["tasks"]:
                conclusion += (
                    f"DIOR 设施检测涉及 {object_detection['tasks']} 个任务，"
                    f"保存了 {object_detection['total_objects']} 个目标框。"
                )

        return {
            "schema_version": 3,
            "export_type": "patrol_business_report",
            "generated_at": now.isoformat(),
            "period": {
                "start": start_date.isoformat(),
                "end": today.isoformat(),
                "days": days,
            },
            "summary": {
                **current,
                "active_days": active_days,
                "completion_rate": round(
                    current["completed_tasks"] / current["tasks"], 4
                )
                if current["tasks"]
                else None,
            },
            "comparison_with_previous_period": {
                "task_growth_percent": _growth(current["tasks"], previous["tasks"]),
                "image_growth_percent": _growth(current["images"], previous["images"]),
                "segmented_pixel_growth_percent": _growth(
                    current["segmented_pixels"], previous["segmented_pixels"]
                ),
            },
            "land_cover": land_cover,
            "dominant_land_cover": dominant,
            "object_detection": object_detection,
            "object_detections": object_detections,
            "daily_trend": daily_trend,
            "peak_activity": peak,
            "recent_tasks": recent_tasks,
            "data_quality": {
                "semantic_task_coverage": round(
                    current["semantic_tasks"] / current["tasks"], 4
                )
                if current["tasks"]
                else None,
                "inference_time_coverage": round(
                    current["timed_tasks"] / current["tasks"], 4
                )
                if current["tasks"]
                else None,
                "class_pixels_estimated_from_stored_ratios": True,
                "object_task_coverage": round(
                    object_detection["tasks"] / current["tasks"], 4
                )
                if current["tasks"]
                else None,
                "object_detail_coverage": round(
                    len(object_detections)
                    / sum(int(task.total_objects or 0) for task in object_tasks),
                    4,
                )
                if sum(int(task.total_objects or 0) for task in object_tasks)
                else None,
                "warnings": warnings,
            },
            "metric_definitions": {
                "segmented_pixels": "有语义统计记录的影像像素总数，不是目标数量",
                "land_cover_ratio": "由任务保存的类别占比按影像像素加权汇总",
                "dominant_land_cover": "排除背景类别后，像素占比最高的地物类别",
                "inference_time": "有有效耗时记录的任务总耗时除以对应图像数，单位毫秒",
                "growth": "与紧邻的上一等长周期比较；上一周期为零时返回 null",
                "object_count": "DIOR 目标检测保存的水平检测框数量，不是像素或面积",
                "object_confidence": "模型对单个检测框类别判断的置信度",
            },
            "conclusion": conclusion,
        }

    def build(
        self, user_id: int, days: int = 30, domain: str = "all"
    ) -> dict[str, Any]:
        safe_days = max(1, min(int(days), 365))
        now = datetime.now()
        current_start = datetime.combine(
            now.date() - timedelta(days=safe_days - 1), time.min
        )
        previous_start = current_start - timedelta(days=safe_days)
        db = SessionLocal()
        try:
            query = (
                db.query(DetectionTask)
                .options(
                    joinedload(DetectionTask.scene),
                    joinedload(DetectionTask.results),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= previous_start,
                )
            )
            if domain == "dior":
                query = query.filter(
                    DetectionTask.scene.has(name="dior_facility_detection")
                )
            tasks = query.order_by(DetectionTask.created_at.desc()).all()
            current = [task for task in tasks if task.created_at >= current_start]
            previous = [task for task in tasks if task.created_at < current_start]
            return self.compose(current, previous, safe_days, now)
        finally:
            db.close()


patrol_export_service = PatrolExportService()
