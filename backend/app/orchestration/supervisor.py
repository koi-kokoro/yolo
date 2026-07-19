"""Day 11 Supervisor：明确业务意图优先，普通输入进入通用 Chat Agent。"""

from __future__ import annotations

import re
from typing import Literal

AgentRoute = Literal["detection", "analysis", "qa", "chat"]


class Supervisor:
    ALLOWED_ROUTES = frozenset({"detection", "analysis", "qa", "chat"})
    ANALYSIS_WORDS = ("统计", "趋势", "历史", "记录", "多少次", "分布", "最近", "看板", "摘要")
    QA_WORDS = ("iou", "loveda", "遥感", "语义分割", "mIoU", "交并比", "像素准确率", "什么是")
    ELIDED_FOLLOW_UP = re.compile(
        r"^(?:它|这个|该数据集|刚才)?(?:一共|总共)?有(?:(?:哪|几|多少)(?:几)?)?类[？?]?$|"
        r"^(?:它|这个|该数据集|刚才)?分别是(?:什么|哪些)[？?]?$|"
        r"^(?:这个|该)?数据集呢[？?]?$|^(?:它呢|那呢|刚才呢)[？?]?$"
    )

    def route(
        self,
        message: str,
        image_path: str | None = None,
        memory: list[dict[str, str]] | None = None,
    ) -> AgentRoute:
        if image_path:
            return "detection"
        lowered = message.lower()
        # 当前明确意图始终优先于历史。
        if any(word.lower() in lowered for word in self.ANALYSIS_WORDS):
            return "analysis"
        if any(word.lower() in lowered for word in self.QA_WORDS):
            return "qa"
        if any(word in lowered for word in ("主要是什么地物", "检测结果", "分割结果", "检测图片", "分析图片")):
            return "detection"
        # 仅省略表达继承上一轮服务端持久化 route；不解析助手文本，也不接受白名单外值。
        if self.ELIDED_FOLLOW_UP.match(message.strip()):
            for item in reversed(memory or []):
                if item.get("role") != "assistant":
                    continue
                route = item.get("route")
                if route in self.ALLOWED_ROUTES:
                    return route  # type: ignore[return-value]
                break
        return "chat"

    def validate(self, route: str) -> AgentRoute:
        return route if route in self.ALLOWED_ROUTES else "chat"  # type: ignore[return-value]


supervisor = Supervisor()
