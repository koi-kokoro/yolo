"""当前用户只读统计 Analysis Agent。"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator

from app.agent.tools.analysis_tools import create_analysis_tools
from app.orchestration.workflow import (
    build_land_cover_analysis,
    build_object_detection_analysis,
)


class AnalysisAgent:
    """最小闭环采用确定性工具选择，避免统计查询依赖外部 LLM。"""

    @staticmethod
    def _days(message: str) -> int:
        match = re.search(r"(?:最近|近)?\s*(\d+)\s*天", message)
        return max(1, min(int(match.group(1)), 365)) if match else 30

    @staticmethod
    def _previous_tool(memory: list[dict[str, str]]) -> str | None:
        for item in reversed(memory):
            if item.get("role") != "assistant":
                continue
            text = item.get("content", "")
            if "检测趋势" in text:
                return "detection_trend"
            if "类别分布" in text:
                return "class_distribution"
            if "检测历史" in text or "本页返回" in text:
                return "detection_history"
            if "共完成" in text:
                return "detection_statistics"
        return None

    @staticmethod
    def _domain(message: str) -> str:
        facility_words = (
            "dior",
            "设施",
            "目标",
            "飞机",
            "机场",
            "桥梁",
            "船舶",
            "储油罐",
            "车辆",
            "风力发电机",
            "体育场",
            "港口",
            "烟囱",
            "水坝",
        )
        lowered = message.lower()
        return "dior" if any(word in lowered for word in facility_words) else "all"

    async def chat_stream(
        self,
        message: str,
        user_id: int,
        memory: list[dict[str, str]] | None = None,
        workflow_state: dict[str, Any] | None = None,
        **_: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        evidence = (workflow_state or {}).get("evidence_pack") or {}
        tool_results = evidence.get("tool_results") or {}
        semantic_key = next(
            (
                key
                for key in ("detection", "land_cover")
                if isinstance(tool_results.get(key), dict)
            ),
            None,
        )
        facility_key = next(
            (
                key
                for key in ("facility_detection", "facilities")
                if isinstance(tool_results.get(key), dict)
            ),
            None,
        )
        analyses: list[dict[str, Any]] = []
        if semantic_key:
            detection = tool_results[semantic_key]
            if detection.get("class_statistics") is not None:
                analyses.append(build_land_cover_analysis(detection, semantic_key))
        if facility_key:
            analyses.append(
                build_object_detection_analysis(tool_results[facility_key], facility_key)
            )
        if analyses:
            if len(analyses) == 1:
                result = analyses[0]
            else:
                result = {
                    "domain": "combined_detection",
                    "scope": "current_image",
                    "claims": [
                        claim for analysis in analyses for claim in analysis["claims"]
                    ],
                    "summary": " ".join(analysis["summary"] for analysis in analyses),
                }
            yield {"type": "analysis_result", "result": result}
            yield {"type": "text_chunk", "content": result["summary"]}
            return

        tools = {item.name: item for item in create_analysis_tools(user_id)}
        days = self._days(message)
        domain = self._domain(message)
        if "趋势" in message:
            name, args = "detection_trend", {"days": days, "domain": domain}
        elif any(word in message for word in ("类别", "分布", "占比")):
            name, args = "class_distribution", {"days": days, "domain": domain}
        elif any(word in message for word in ("列表", "记录", "历史")):
            name, args = "detection_history", {
                "page": 1,
                "page_size": 10,
                "domain": domain,
            }
        elif any(word in message for word in ("状态", "摘要")):
            name, args = "history_summary", {"domain": domain}
        else:
            # 省略问法只继承白名单工具类型；days 每轮从当前消息重算。
            name = self._previous_tool(memory or []) or "detection_statistics"
            args = (
                {"page": 1, "page_size": 10, "domain": domain}
                if name == "detection_history"
                else (
                    {"domain": domain}
                    if name == "history_summary"
                    else {"days": days, "domain": domain}
                )
            )

        yield {"type": "tool_call", "tool": name, "input": args}
        result = tools[name].invoke(args)
        yield {"type": "tool_result", "tool": name, "result": result}
        parsed = json.loads(result)
        if name == "detection_statistics":
            text = (
                f"最近 {parsed['period_days']} 天共完成 {parsed['total_tasks']} 次检测，"
                f"处理 {parsed['total_images']} 张图片，"
                + (
                    f"检测到设施目标 {parsed['total_objects']} 个。"
                    if domain == "dior"
                    else f"记录结果数量 {parsed['total_objects']}。"
                )
            )
        elif name == "detection_trend":
            text = f"已查询最近 {parsed['period_days']} 天检测趋势，共 {len(parsed['trend'])} 个日期点。"
        elif name == "class_distribution":
            label = "DIOR 目标类别" if domain == "dior" else "检测类别"
            text = f"已查询最近 {parsed['period_days']} 天{label}分布，共 {len(parsed['distribution'])} 类。"
        elif name == "detection_history":
            text = f"当前用户共有 {parsed['total']} 条检测历史，本页返回 {len(parsed['items'])} 条。"
        else:
            text = f"检测历史共 {parsed['total_tasks']} 条，今日 {parsed['today_tasks']} 条。"
        analysis_result = {
            "domain": "object_detection" if domain == "dior" else "mixed",
            "scope": "patrol_statistics",
            "claims": [
                {
                    "text": text,
                    "claim_type": "observation",
                    "evidence_ref": "tool_results.analysis",
                    "observed_value": parsed,
                }
            ],
            "summary": text,
        }
        yield {"type": "analysis_result", "result": analysis_result}
        yield {"type": "text_chunk", "content": text}
