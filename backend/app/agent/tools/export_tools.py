"""Export Agent 使用的当前用户数据导出工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.agent.tools.evaluation_tools import collect_evaluation_snapshot
from app.services.agent_export_service import agent_export_service
from app.services.patrol_export_service import patrol_export_service


def create_export_tools(user_id: int) -> list[Any]:
    """创建绑定当前用户的导出工具，用户 ID 不暴露给模型。"""

    @tool
    def export_platform_data(
        data_type: str = "patrol", file_format: str = "json", days: int = 30
    ) -> str:
        """将当前用户巡查数据或全局缓存评估指标导出为 JSON/CSV。"""
        safe_days = max(1, min(int(days), 365))
        if data_type == "evaluation":
            data = collect_evaluation_snapshot()
        elif data_type == "patrol":
            data = patrol_export_service.build(user_id=user_id, days=safe_days)
        else:
            raise ValueError("不支持的导出数据类型")
        result = agent_export_service.create(
            user_id=user_id,
            data_type=data_type,
            file_format=file_format,
            data=data,
        )
        if data_type == "patrol":
            top = data.get("dominant_land_cover")
            result["preview"] = {
                "tasks": data.get("summary", {}).get("tasks"),
                "images": data.get("summary", {}).get("images"),
                "top_class": top.get("display_name") if top else None,
                "top_class_ratio": top.get("ratio") if top else None,
                "warnings": data.get("data_quality", {}).get("warnings", []),
            }
        return json.dumps(result, ensure_ascii=False)

    return [export_platform_data]
