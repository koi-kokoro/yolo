"""
数据看板服务层

职责：
  - 检测汇总统计（任务数/图片数/目标数/平均耗时 + 环比增长）
  - 每日检测趋势（近 N 天折线图数据）
  - 类别分布统计（饼图数据）
  - 场景分布统计（柱状图数据）
  - 任务类型分布统计（环形图数据）

架构：
  DashboardService 是无状态的纯服务，被 dashboard.py API 层调用。
  所有数据库查询逻辑和会话管理集中在此层，API 层只负责参数校验和响应格式化。
"""

from datetime import datetime, timedelta

from sqlalchemy import cast, Date, func

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask

logger = get_logger(__name__)


class DashboardService:
    """数据看板服务"""

    @staticmethod
    def get_statistics(
        user_id: int, days: int = 30, scene_name: str | None = None
    ) -> dict:
        """
        获取检测汇总统计数据

        Args:
            user_id: 用户 ID
            days: 统计最近 N 天

        Returns:
            包含总任务数、总图片数、总目标数、平均推理耗时及环比增长率的字典
        """
        db = SessionLocal()
        try:
            now = datetime.now()
            start_date = now - timedelta(days=days)
            prev_start = now - timedelta(days=days * 2)

            # ── 当前时段统计 ──
            current_query = db.query(
                    func.count(DetectionTask.id).label("total_tasks"),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "total_images"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "total_objects"
                    ),
                    func.coalesce(
                        func.avg(DetectionTask.total_inference_time), 0
                    ).label("avg_inference_time"),
                )
            if scene_name:
                current_query = current_query.join(
                    DetectionScene, DetectionTask.scene_id == DetectionScene.id
                ).filter(DetectionScene.name == scene_name)
            current_stats = (
                current_query.filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .first()
            )

            # ── 上一时段统计（用于环比） ──
            previous_query = db.query(
                    func.count(DetectionTask.id).label("total_tasks"),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "total_images"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "total_objects"
                    ),
                    func.coalesce(
                        func.avg(DetectionTask.total_inference_time), 0
                    ).label("avg_inference_time"),
                )
            if scene_name:
                previous_query = previous_query.join(
                    DetectionScene, DetectionTask.scene_id == DetectionScene.id
                ).filter(DetectionScene.name == scene_name)
            prev_stats = (
                previous_query.filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= prev_start,
                    DetectionTask.created_at < start_date,
                )
                .first()
            )

            def calc_growth(current, previous):
                """计算环比增长率（百分比）"""
                if previous == 0:
                    return 100.0 if current > 0 else 0.0
                return round((current - previous) / previous * 100, 1)

            return {
                "total_tasks": current_stats.total_tasks,
                "total_images": int(current_stats.total_images),
                "total_objects": int(current_stats.total_objects),
                "avg_inference_time": round(float(current_stats.avg_inference_time), 2),
                "growth": {
                    "tasks": calc_growth(
                        current_stats.total_tasks, prev_stats.total_tasks
                    ),
                    "images": calc_growth(
                        int(current_stats.total_images),
                        int(prev_stats.total_images),
                    ),
                    "objects": calc_growth(
                        int(current_stats.total_objects),
                        int(prev_stats.total_objects),
                    ),
                    "inference_time": calc_growth(
                        float(current_stats.avg_inference_time),
                        float(prev_stats.avg_inference_time),
                    ),
                },
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_trend(
        user_id: int, days: int = 30, scene_name: str | None = None
    ) -> dict:
        """
        获取每日检测趋势数据（用于折线图）

        Args:
            user_id: 用户 ID
            days: 统计最近 N 天

        Returns:
            包含每天检测任务数和目标数的趋势列表
        """
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)

            # 按日期聚合查询
            trend_query = db.query(
                    cast(DetectionTask.created_at, Date).label("date"),
                    func.count(DetectionTask.id).label("task_count"),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "object_count"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "image_count"
                    ),
                )
            if scene_name:
                trend_query = trend_query.join(
                    DetectionScene, DetectionTask.scene_id == DetectionScene.id
                ).filter(DetectionScene.name == scene_name)
            daily_stats = (
                trend_query.filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(cast(DetectionTask.created_at, Date))
                .order_by(cast(DetectionTask.created_at, Date))
                .all()
            )

            # 构建完整的日期序列（填充没有数据的日期为 0）
            date_map = {}
            for row in daily_stats:
                date_str = str(row.date)
                date_map[date_str] = {
                    "date": date_str,
                    "task_count": row.task_count,
                    "object_count": int(row.object_count),
                    "image_count": int(row.image_count),
                }

            # 填充空白日期
            result = []
            for i in range(days):
                d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
                if d in date_map:
                    result.append(date_map[d])
                else:
                    result.append(
                        {
                            "date": d,
                            "task_count": 0,
                            "object_count": 0,
                            "image_count": 0,
                        }
                    )

            return {"trend": result, "period_days": days}
        finally:
            db.close()

    @staticmethod
    def get_class_distribution(
        user_id: int, days: int = 30, scene_name: str | None = None
    ) -> dict:
        """
        获取各类别检测次数分布（用于饼图）

        Args:
            user_id: 用户 ID
            days: 统计最近 N 天

        Returns:
            包含各类别检测次数的分布列表
        """
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)

            # 关联查询：detection_results JOIN detection_tasks
            class_query = (
                db.query(
                    DetectionResult.class_name,
                    func.max(DetectionResult.class_name_cn).label("display_name"),
                    func.count(DetectionResult.id).label("count"),
                )
                .join(DetectionTask, DetectionResult.task_id == DetectionTask.id)
            )
            if scene_name:
                class_query = class_query.join(
                    DetectionScene, DetectionTask.scene_id == DetectionScene.id
                ).filter(DetectionScene.name == scene_name)
            class_stats = (
                class_query.filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionResult.class_name)
                .order_by(func.count(DetectionResult.id).desc())
                .all()
            )

            distribution = [
                {
                    "name": row.class_name,
                    "display_name": row.display_name or row.class_name,
                    "value": row.count,
                }
                for row in class_stats
            ]

            return {"distribution": distribution, "period_days": days}
        finally:
            db.close()

    @staticmethod
    def get_scene_distribution(user_id: int, days: int = 30) -> dict:
        """
        获取各检测场景的任务分布（用于柱状图）

        Args:
            user_id: 用户 ID
            days: 统计最近 N 天

        Returns:
            包含各场景任务数的分布列表
        """
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)

            scene_stats = (
                db.query(
                    DetectionScene.display_name,
                    func.count(DetectionTask.id).label("count"),
                )
                .join(DetectionScene, DetectionTask.scene_id == DetectionScene.id)
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionScene.display_name)
                .order_by(func.count(DetectionTask.id).desc())
                .all()
            )

            distribution = [
                {"name": row.display_name, "value": row.count} for row in scene_stats
            ]

            return {"distribution": distribution, "period_days": days}
        finally:
            db.close()

    @staticmethod
    def get_semantic_risk_matrix(user_id: int, days: int = 30) -> dict:
        """Return per-image semantic anomaly/reliability proxy points."""
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            tasks = (
                db.query(DetectionTask)
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                    DetectionTask.semantic_metrics.isnot(None),
                )
                .order_by(DetectionTask.created_at.desc())
                .all()
            )

            points = []
            for task in tasks:
                payload = task.semantic_metrics or {}
                for sample in payload.get("samples", []):
                    points.append(
                        {
                            "task_id": task.id,
                            "task_type": task.task_type,
                            "created_at": task.created_at.isoformat()
                            if task.created_at
                            else None,
                            "name": sample.get("name") or f"任务 {task.id}",
                            "anomaly_score": float(
                                sample.get("anomaly_score") or 0
                            ),
                            "reliability_score": float(
                                sample.get("reliability_score") or 0
                            ),
                            "domain_status": sample.get("domain_status"),
                            "review_level": sample.get("review_level"),
                            "total_pixels": int(sample.get("total_pixels") or 0),
                        }
                    )

            points.sort(key=lambda item: item["anomaly_score"], reverse=True)
            return {
                "points": points,
                "sample_count": len(points),
                "period_days": days,
                "metric_note": "基于 LoveDA 类别先验距离与验证集 IoU 的代理评估，非模型置信度",
            }
        finally:
            db.close()

    @staticmethod
    def get_domain_health(user_id: int, days: int = 30) -> dict:
        """Summarise semantic samples into input-domain health buckets."""
        matrix = DashboardService.get_semantic_risk_matrix(user_id, days)
        buckets = {
            "in_domain": {"name": "域内", "value": 0},
            "attention": {"name": "临界", "value": 0},
            "out_of_domain": {"name": "域外", "value": 0},
        }
        for point in matrix["points"]:
            status = point.get("domain_status")
            if status in buckets:
                buckets[status]["value"] += 1

        return {
            "distribution": list(buckets.values()),
            "sample_count": matrix["sample_count"],
            "period_days": days,
            "metric_note": matrix["metric_note"],
        }

    @staticmethod
    def get_type_distribution(user_id: int, days: int = 30) -> dict:
        """
        获取各任务类型的分布（用于环形图）

        Args:
            user_id: 用户 ID
            days: 统计最近 N 天

        Returns:
            包含各任务类型任务数的分布列表
        """
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)

            type_stats = (
                db.query(
                    DetectionTask.task_type,
                    func.count(DetectionTask.id).label("count"),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionTask.task_type)
                .order_by(func.count(DetectionTask.id).desc())
                .all()
            )

            # 任务类型中文映射
            type_names = {
                "single": "单图检测",
                "batch": "批量检测",
                "zip": "ZIP检测",
                "video": "视频检测",
                "camera": "摄像头检测",
            }

            distribution = [
                {
                    "name": type_names.get(row.task_type, row.task_type),
                    "value": row.count,
                }
                for row in type_stats
            ]

            return {"distribution": distribution, "period_days": days}
        finally:
            db.close()


dashboard_service = DashboardService()
