"""业务巡查导出结构与数据语义测试。"""

from datetime import datetime, timedelta

from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask
from app.services.agent_export_service import AgentExportService
from app.services.patrol_export_service import PatrolExportService


def _task(
    task_id: int,
    created_at: datetime,
    *,
    metrics=None,
    images: int = 1,
    misleading_total_objects: int = 1_048_576,
    inference_time: float = 0,
):
    scene = DetectionScene(name=f"scene-{task_id}", display_name="LoveDA 语义分割", category="semantic")
    task = DetectionTask(
        id=task_id,
        user_id=1,
        scene_id=task_id,
        task_type="single",
        status="completed",
        total_images=images,
        total_objects=misleading_total_objects,
        semantic_metrics=metrics,
        total_inference_time=inference_time,
        created_at=created_at,
        completed_at=created_at,
    )
    task.scene = scene
    return task


def test_patrol_export_uses_semantic_pixels_and_reports_missing_data():
    now = datetime(2026, 7, 20, 15, 0, 0)
    metrics = {
        "version": 1,
        "samples": [
            {
                "name": "image.png",
                "total_pixels": 100,
                "class_ratios": {"building": 0.6, "agricultural": 0.4},
                "anomaly_score": 20.0,
                "reliability_score": 70.0,
                "review_level": "low",
            }
        ],
    }
    tasks = [
        _task(1, now, metrics=metrics, inference_time=20),
        _task(2, now - timedelta(days=1)),
    ]

    report = PatrolExportService.compose(tasks, [], 7, now)

    assert report["schema_version"] == 3
    assert report["summary"]["tasks"] == 2
    assert report["summary"]["segmented_pixels"] == 100
    assert report["summary"]["segmented_pixels"] != sum(
        task.total_objects for task in tasks
    )
    assert report["summary"]["average_inference_time_ms_per_image"] == 20.0
    assert report["comparison_with_previous_period"]["task_growth_percent"] is None
    assert report["land_cover"][0]["display_name"] == "建筑"
    assert report["land_cover"][0]["pixel_count"] == 60
    assert report["land_cover"][0]["ratio"] == 0.6
    assert report["dominant_land_cover"]["display_name"] == "建筑"
    assert report["recent_tasks"][0]["top_class"] == "建筑"
    assert report["recent_tasks"][0]["anomaly_score"] == 20.0
    warnings = " ".join(report["data_quality"]["warnings"])
    assert "1 条历史任务缺少类别统计" in warnings
    assert "1 条历史任务缺少有效推理耗时" in warnings
    assert "环比指标记为 null" in warnings


def test_patrol_export_computes_growth_only_with_previous_baseline():
    now = datetime(2026, 7, 20, 15, 0, 0)
    current = [_task(1, now, images=4)]
    previous = [_task(2, now - timedelta(days=8), images=2)]
    report = PatrolExportService.compose(current, previous, 7, now)
    assert report["comparison_with_previous_period"]["task_growth_percent"] == 0.0
    assert report["comparison_with_previous_period"]["image_growth_percent"] == 100.0


def test_patrol_csv_contains_business_sections(tmp_path):
    now = datetime(2026, 7, 20, 15, 0, 0)
    metrics = {
        "samples": [
            {
                "total_pixels": 100,
                "class_ratios": {"water": 1.0},
                "review_level": "medium",
            }
        ]
    }
    report = PatrolExportService.compose([_task(1, now, metrics=metrics)], [], 7, now)
    service = AgentExportService(tmp_path)
    result = service.create(1, "patrol", "csv", report)
    content = service.resolve(1, result["filename"]).read_text(encoding="utf-8-sig")
    assert "summary" in content
    assert "land_cover" in content
    assert "daily_trend" in content
    assert "recent_tasks" in content
    assert "conclusion" in content
    assert "segmented_pixels" in content


def test_dior_objects_are_exported_with_confidence_and_bbox(tmp_path):
    now = datetime(2026, 7, 20, 15, 0, 0)
    scene = DetectionScene(
        id=9,
        name="dior_facility_detection",
        display_name="DIOR 遥感设施检测",
        category="object_detection",
    )
    task = DetectionTask(
        id=9,
        user_id=1,
        scene_id=9,
        task_type="single",
        status="completed",
        total_images=1,
        total_objects=1,
        total_inference_time=12.5,
        created_at=now,
        completed_at=now,
    )
    task.scene = scene
    task.results = [
        DetectionResult(
            task_id=9,
            image_path="object-key",
            class_name="airplane",
            class_name_cn="飞机",
            class_id=0,
            confidence=0.91,
            bbox={"x1": 1, "y1": 2, "x2": 20, "y2": 18},
            image_width=32,
            image_height=24,
        )
    ]

    report = PatrolExportService.compose([task], [], 7, now)
    assert report["object_detection"]["total_objects"] == 1
    assert report["object_detection"]["class_distribution"][0]["display_name"] == "飞机"
    assert report["object_detections"][0]["confidence"] == 0.91
    assert "缺少类别统计" not in " ".join(report["data_quality"]["warnings"])

    service = AgentExportService(tmp_path)
    result = service.create(1, "dior", "csv", report)
    content = service.resolve(1, result["filename"]).read_text(encoding="utf-8-sig")
    assert "object_summary" in content
    assert "object_detection" in content
    assert "0.91" in content
    assert '"x1": 1' in content
