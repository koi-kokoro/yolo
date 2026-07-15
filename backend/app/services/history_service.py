"""
历史记录服务层
职责：
  - 检测任务分页查询
  - 任务详情查询（含结果列表）
  - 任务删除（级联删除结果）
  - 历史记录统计
  - 场景列表查询
架构：
  HistoryService 是无状态的纯服务，被 history.py API 层调用。
  所有数据库查询逻辑和会话管理集中在此层，API 层只负责参数校验和响应格式化。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask

logger = get_logger(__name__)


class HistoryService:
    """历史记录服务"""

    @staticmethod
    def list_tasks(
        user_id: int,
        page: int = 1,
        page_size: int = 10,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        scene_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """
        分页查询用户的检测任务列表

        Args:
            user_id: 用户 ID
            page: 页码（从 1 开始）
            page_size: 每页数量
            task_type: 任务类型筛选
            status: 状态筛选
            scene_id: 场景 ID 筛选
            start_date: 起始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            包含分页信息和任务列表的字典
        """
        db = SessionLocal()
        try:
            query = (
                db.query(DetectionTask)
                .options(joinedload(DetectionTask.scene))
                .filter(DetectionTask.user_id == user_id)
            )

            if task_type:
                query = query.filter(DetectionTask.task_type == task_type)
            if status:
                query = query.filter(DetectionTask.status == status)
            if scene_id:
                query = query.filter(DetectionTask.scene_id == scene_id)
            if start_date:
                try:
                    query = query.filter(
                        DetectionTask.created_at
                        >= datetime.strptime(start_date, "%Y-%m-%d")
                    )
                except ValueError:
                    pass
            if end_date:
                try:
                    query = query.filter(
                        DetectionTask.created_at
                        <= datetime.strptime(end_date, "%Y-%m-%d").replace(
                            hour=23, minute=59, second=59
                        )
                    )
                except ValueError:
                    pass

            total = query.count()
            total_pages = (total + page_size - 1) // page_size

            tasks = (
                query.order_by(desc(DetectionTask.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

            items = []
            for task in tasks:
                scene_name = task.scene.display_name if task.scene else None
                items.append(
                    {
                        "id": task.id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "scene_id": task.scene_id,
                        "scene_name": scene_name,
                        "total_images": task.total_images or 0,
                        "total_objects": task.total_objects or 0,
                        "total_inference_time": round(
                            task.total_inference_time or 0, 2
                        ),
                        "conf_threshold": task.conf_threshold,
                        "error_message": task.error_message,
                        "created_at": task.created_at.isoformat()
                        if task.created_at
                        else None,
                        "completed_at": task.completed_at.isoformat()
                        if task.completed_at
                        else None,
                    }
                )

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "items": items,
            }
        finally:
            db.close()

    @staticmethod
    def get_task_detail(user_id: int, task_id: int) -> Optional[dict]:
        """
        获取检测任务详情，包含完整的结果列表

        Args:
            user_id: 用户 ID
            task_id: 任务 ID

        Returns:
            任务详情字典，如果任务不存在或无权访问则返回 None
        """
        db = SessionLocal()
        try:
            task = (
                db.query(DetectionTask)
                .options(joinedload(DetectionTask.scene))
                .filter(DetectionTask.id == task_id, DetectionTask.user_id == user_id)
                .first()
            )

            if not task:
                return None

            results = (
                db.query(DetectionResult)
                .filter(DetectionResult.task_id == task_id)
                .all()
            )

            class_counts = {}
            for r in results:
                class_counts[r.class_name] = class_counts.get(r.class_name, 0) + 1

            result_items = [
                {
                    "id": r.id,
                    "class_name": r.class_name,
                    "class_name_cn": r.class_name_cn,
                    "class_id": r.class_id,
                    "confidence": round(r.confidence, 4),
                    "bbox": r.bbox,
                    "image_path": r.image_path,
                    "annotated_image_url": r.annotated_image_url,
                    "inference_time": round(r.inference_time, 2)
                    if r.inference_time
                    else None,
                }
                for r in results
            ]

            return {
                "task": {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "scene_id": task.scene_id,
                    "scene_name": task.scene.display_name if task.scene else None,
                    "total_images": task.total_images or 0,
                    "total_objects": task.total_objects or 0,
                    "total_inference_time": round(task.total_inference_time or 0, 2),
                    "conf_threshold": task.conf_threshold,
                    "iou_threshold": task.iou_threshold,
                    "error_message": task.error_message,
                    "created_at": task.created_at.isoformat()
                    if task.created_at
                    else None,
                    "completed_at": task.completed_at.isoformat()
                    if task.completed_at
                    else None,
                },
                "class_counts": class_counts,
                "results": result_items,
            }
        finally:
            db.close()

    @staticmethod
    def delete_task(user_id: int, task_id: int) -> bool:
        """
        删除检测任务及其关联的检测结果（级联删除）

        Args:
            user_id: 用户 ID
            task_id: 任务 ID

        Returns:
            删除成功返回 True，任务不存在或无权访问返回 False
        """
        db = SessionLocal()
        try:
            task = (
                db.query(DetectionTask)
                .filter(DetectionTask.id == task_id, DetectionTask.user_id == user_id)
                .first()
            )

            if not task:
                return False

            db.delete(task)
            db.commit()

            logger.info("用户 %d 删除检测任务 #%d", user_id, task_id)
            return True
        finally:
            db.close()

    @staticmethod
    def get_summary(user_id: int) -> dict:
        """
        获取用户检测历史摘要统计

        Args:
            user_id: 用户 ID

        Returns:
            统计信息字典：总任务数、今日任务数、各状态任务数
        """
        db = SessionLocal()
        try:
            today_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            total = (
                db.query(func.count(DetectionTask.id))
                .filter(DetectionTask.user_id == user_id)
                .scalar()
            )

            today_count = (
                db.query(func.count(DetectionTask.id))
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= today_start,
                )
                .scalar()
            )

            status_counts = {}
            for s in ["completed", "processing", "failed", "pending"]:
                count = (
                    db.query(func.count(DetectionTask.id))
                    .filter(DetectionTask.user_id == user_id, DetectionTask.status == s)
                    .scalar()
                )
                status_counts[s] = count

            return {
                "total_tasks": total,
                "today_tasks": today_count,
                "status_counts": status_counts,
            }
        finally:
            db.close()

    @staticmethod
    def list_scenes() -> list:
        """
        获取所有可用的检测场景列表

        Returns:
            场景列表
        """
        db = SessionLocal()
        try:
            scenes = (
                db.query(DetectionScene).filter(DetectionScene.is_active == True).all()
            )
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "display_name": s.display_name,
                    "category": s.category,
                }
                for s in scenes
            ]
        finally:
            db.close()


history_service = HistoryService()
