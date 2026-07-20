"""Day 11 Supervisor：明确业务意图优先，普通输入进入通用 Chat Agent。"""

from __future__ import annotations

import re
from typing import Literal

from app.orchestration.workflow import AgentStep, TaskPlan

AgentRoute = Literal[
    "detection", "evaluation", "export", "analysis", "qa", "report", "chat"
]


class Supervisor:
    ALLOWED_ROUTES = frozenset(
        {"detection", "evaluation", "export", "analysis", "qa", "report", "chat"}
    )
    EXPORT_WORDS = ("导出", "下载数据", "下载报告", "下载指标")
    EVALUATION_WORDS = (
        "模型评估",
        "评估模型",
        "评估结果",
        "评估指标",
        "模型指标",
        "模型表现",
        "模型性能",
        "模型对比",
        "对比模型",
        "哪个模型",
        "当前模型",
        "基线模型",
        "弱势类别",
    )
    REPORT_WORDS = (
        "巡查报告",
        "检测报告",
        "分析报告",
        "生成报告",
        "总结报告",
        "巡查日报",
        "巡查周报",
        "巡查月报",
        "报告",
    )
    ANALYSIS_WORDS = ("统计", "趋势", "历史", "记录", "多少次", "分布", "最近", "看板", "摘要")
    QA_WORDS = ("iou", "loveda", "遥感", "语义分割", "mIoU", "交并比", "像素准确率", "什么是")
    SHORT_DETECTION = re.compile(
        r"^(?:帮我)?(?:再)?(?:识别|检测|分析|查看|看看|分割|语义分割)"
        r"(?:一?下|一下吧|看看)?[。！!？?]*$"
    )
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
        if any(word in lowered for word in self.EXPORT_WORDS):
            return "export"
        if any(word in lowered for word in self.EVALUATION_WORDS):
            return "evaluation"
        if any(word in lowered for word in self.REPORT_WORDS):
            return "report"
        if any(word.lower() in lowered for word in self.ANALYSIS_WORDS):
            return "analysis"
        explicit_detection = self.SHORT_DETECTION.fullmatch(message.strip()) or any(
            word in lowered
            for word in (
                "主要是什么地物",
                "检测结果",
                "分割结果",
                "识别图片",
                "识别上传图片",
                "检测图片",
                "检测上传图片",
                "分割图片",
                "分析图片",
                "刚才的图片",
                "刚刚的图片",
                "刚刚那张图",
            )
        )
        if explicit_detection and not any(
            prefix in message for prefix in ("什么是", "解释一下", "介绍一下")
        ):
            return "detection"
        if any(word.lower() in lowered for word in self.QA_WORDS):
            return "qa"
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

    def plan(
        self,
        message: str,
        image_path: str | None = None,
        memory: list[dict[str, str]] | None = None,
    ) -> TaskPlan:
        """生成白名单任务计划；单意图保持原来的单 Agent 行为。"""
        primary = self.validate(self.route(message, image_path, memory))
        lowered = message.lower()
        wants_report = any(word in lowered for word in self.REPORT_WORDS)
        wants_export = any(word in lowered for word in self.EXPORT_WORDS)
        wants_evaluation = any(word in lowered for word in self.EVALUATION_WORDS)
        wants_analysis = any(word.lower() in lowered for word in self.ANALYSIS_WORDS)

        if image_path and wants_report:
            return TaskPlan(
                primary_route="report",
                reason="当前图片检测、证据分析、审核与报告生成",
                steps=(
                    AgentStep("detection", "detection", expose_text=False),
                    AgentStep("analysis", "analysis", ("detection",), expose_text=False),
                    AgentStep("review", "review", ("analysis",), expose_text=False),
                    AgentStep("report", "report", ("review",)),
                ),
            )
        if wants_report:
            return TaskPlan(
                primary_route="report",
                reason="统计分析、证据审核与巡查报告生成",
                steps=(
                    AgentStep("analysis", "analysis", expose_text=False),
                    AgentStep("review", "review", ("analysis",), expose_text=False),
                    AgentStep("report", "report", ("review",)),
                ),
            )
        if wants_export and wants_evaluation:
            return TaskPlan(
                primary_route="export",
                reason="先解释模型评估，再导出相同领域指标",
                steps=(
                    AgentStep("evaluation", "evaluation", expose_text=False),
                    AgentStep("export", "export", ("evaluation",)),
                ),
            )
        if wants_export and wants_analysis:
            return TaskPlan(
                primary_route="export",
                reason="先查询巡查统计，再导出巡查数据",
                steps=(
                    AgentStep("analysis", "analysis", expose_text=False),
                    AgentStep("export", "export", ("analysis",)),
                ),
            )
        return TaskPlan(
            primary_route=primary,
            reason="单一明确意图",
            steps=(AgentStep(primary, primary),),
        )


supervisor = Supervisor()
