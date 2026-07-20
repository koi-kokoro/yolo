"""按请求绑定当前用户的只读巡查报告数据工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.services.dashboard_service import dashboard_service
from app.services.history_service import history_service


def create_report_tools(user_id: int) -> list[Any]:
    """创建只允许读取当前认证用户数据的报告工具。"""

    @tool
    def collect_patrol_report_data(days: int = 30) -> str:
        """收集当前用户指定周期内的巡查统计、趋势、类别分布和近期任务。"""
        safe_days = max(1, min(int(days), 365))
        recent = history_service.list_tasks(user_id=user_id, page=1, page_size=5)
        # 报告上下文只保留展示所需字段，不携带错误详情或其他内部数据。
        safe_recent_tasks = [
            {
                key: item.get(key)
                for key in (
                    "task_type",
                    "status",
                    "scene_name",
                    "total_images",
                    "total_objects",
                    "total_inference_time",
                    "created_at",
                    "completed_at",
                )
            }
            for item in recent.get("items", [])[:5]
        ]
        payload = {
            "period_days": safe_days,
            "statistics": dashboard_service.get_statistics(
                user_id=user_id, days=safe_days
            ),
            "trend": dashboard_service.get_trend(user_id=user_id, days=safe_days),
            "class_distribution": dashboard_service.get_class_distribution(
                user_id=user_id, days=safe_days
            ),
            "history_summary": history_service.get_summary(user_id=user_id),
            "recent_tasks": {
                "total": int(recent.get("total") or 0),
                "items": safe_recent_tasks,
            },
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    return [collect_patrol_report_data]
