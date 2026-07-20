"""生成用户隔离下载文件的确定性 Export Agent。"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator

from app.agent.tools.export_tools import create_export_tools
from app.core.logger import get_logger

logger = get_logger(__name__)


class ExportAgent:
    @staticmethod
    def _arguments(message: str) -> dict[str, Any]:
        lowered = message.lower()
        if any(
            word in lowered
            for word in ("dior", "设施", "飞机", "机场", "船舶", "储油罐", "检测框")
        ):
            data_type = "dior"
        elif any(word in lowered for word in ("评估", "模型", "miou", "iou", "dice")):
            data_type = "evaluation"
        else:
            data_type = "patrol"
        file_format = "csv" if "csv" in lowered else "json"
        match = re.search(r"(?:最近|近)?\s*(\d+)\s*天", message)
        days = max(1, min(int(match.group(1)), 365)) if match else 30
        return {"data_type": data_type, "file_format": file_format, "days": days}

    async def chat_stream(
        self,
        message: str,
        user_id: int,
        **_: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        tool = create_export_tools(user_id)[0]
        args = self._arguments(message)
        yield {"type": "tool_call", "tool": tool.name, "input": args}
        try:
            raw = tool.invoke(args)
            result = json.loads(raw)
        except Exception:
            logger.exception("Agent export failed for user_id=%s", user_id)
            yield {"type": "error", "content": "数据导出失败，请稍后重试。"}
            return
        yield {"type": "tool_result", "tool": tool.name, "result": raw}
        label = {
            "evaluation": "模型评估指标",
            "dior": "DIOR 设施检测数据",
        }.get(args["data_type"], "巡查数据")
        preview = result.get("preview") or {}
        details = ""
        if args["data_type"] in {"patrol", "dior"}:
            details = (
                f"本次包含 {int(preview.get('tasks') or 0)} 个任务、"
                f"{int(preview.get('images') or 0)} 张影像"
            )
            if preview.get("top_class"):
                details += (
                    f"，主要地物为{preview['top_class']}"
                    f"（{float(preview.get('top_class_ratio') or 0) * 100:.2f}%）"
                )
            if args["data_type"] == "dior":
                details += (
                    f"，包含 {int(preview.get('objects') or 0)} 个设施目标、"
                    f"{int(preview.get('object_classes') or 0)} 个目标类别"
                )
            details += "。"
            if preview.get("warnings"):
                details += f" 数据质量提示：{'；'.join(preview['warnings'])}。"
        yield {
            "type": "text_chunk",
            "content": (
                f"{label}已导出为 {args['file_format'].upper()} 文件："
                f"`{result['filename']}`。{details}请使用下方下载按钮保存。"
            ),
        }


export_agent = ExportAgent()
