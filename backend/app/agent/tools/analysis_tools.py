"""按请求创建、在闭包中绑定认证 user_id 的只读分析工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.services.dashboard_service import dashboard_service
from app.services.history_service import history_service


def create_analysis_tools(user_id: int) -> list[Any]:
    """LLM 的 schema 不暴露 user_id，从而无法越权指定其他用户。"""

    @tool
    def detection_statistics(days: int = 30) -> str:
        """查询当前用户最近若干天的检测任务、图片、地物像素和耗时统计。"""
        safe_days = max(1, min(int(days), 365))
        return json.dumps(
            dashboard_service.get_statistics(user_id=user_id, days=safe_days),
            ensure_ascii=False,
            default=str,
        )

    @tool
    def detection_trend(days: int = 30) -> str:
        """查询当前用户最近若干天每日检测趋势。"""
        safe_days = max(1, min(int(days), 365))
        return json.dumps(
            dashboard_service.get_trend(user_id=user_id, days=safe_days),
            ensure_ascii=False,
            default=str,
        )

    @tool
    def class_distribution(days: int = 30) -> str:
        """查询当前用户 LoveDA 地物类别分布。"""
        safe_days = max(1, min(int(days), 365))
        return json.dumps(
            dashboard_service.get_class_distribution(user_id=user_id, days=safe_days),
            ensure_ascii=False,
            default=str,
        )

    @tool
    def detection_history(page: int = 1, page_size: int = 10) -> str:
        """只读列出当前用户检测历史，最多返回 20 条。"""
        return json.dumps(
            history_service.list_tasks(
                user_id=user_id,
                page=max(1, int(page)),
                page_size=max(1, min(int(page_size), 20)),
            ),
            ensure_ascii=False,
            default=str,
        )

    @tool
    def history_summary() -> str:
        """查询当前用户检测历史状态摘要。"""
        return json.dumps(
            history_service.get_summary(user_id=user_id),
            ensure_ascii=False,
            default=str,
        )

    return [
        detection_statistics,
        detection_trend,
        class_distribution,
        detection_history,
        history_summary,
    ]
