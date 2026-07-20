"""Day 11 Supervisor：明确业务意图优先，普通输入进入通用 Chat Agent。"""

from __future__ import annotations

import re
from typing import Literal

from app.orchestration.workflow import AgentStep, TaskPlan

AgentRoute = Literal[
    "detection", "facility_detection", "evaluation", "export", "analysis", "qa", "report", "chat"
]


class Supervisor:
    ALLOWED_ROUTES = frozenset(
        {"detection", "facility_detection", "evaluation", "export", "analysis", "qa", "report", "chat"}
    )
    FACILITY_WORDS = (
        "dior", "设施", "目标", "检测框", "飞机", "机场", "棒球场", "篮球场",
        "桥梁", "烟囱", "水坝", "服务区", "收费站", "高尔夫球场", "田径场", "港口",
        "立交桥", "船舶", "体育场", "储油罐", "网球场", "火车站", "车辆", "风力发电机",
    )
    SEMANTIC_WORDS = (
        "loveda", "语义", "分割", "土地覆盖", "地物", "像素", "面积", "占比",
        "水体", "森林", "农田", "建筑", "道路", "裸地", "背景",
    )
    IMAGE_INSPECTION_WORDS = (
        "识别", "检测", "分析", "查看", "看看", "有什么", "有哪些", "什么东西",
        "主要", "地物", "类别", "目标", "分割",
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
        lowered = message.lower()
        facility_subject = any(word.lower() in lowered for word in self.FACILITY_WORDS)
        facility_action = any(
            word in lowered for word in ("检测", "识别", "查找", "标注", "定位", "框出", "运行")
        )
        if facility_subject and (image_path is not None or facility_action):
            return "facility_detection"
        if image_path:
            return "detection"
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

        facility_subject = any(word.lower() in lowered for word in self.FACILITY_WORDS)
        semantic_subject = any(word.lower() in lowered for word in self.SEMANTIC_WORDS)
        image_inspection = any(
            word.lower() in lowered for word in self.IMAGE_INSPECTION_WORDS
        )

        # 报告请求保留检测领域：显式设施意图只跑 DIOR，显式语义意图只跑
        # LoveDA，未指定领域或同时指定两个领域时生成联合报告。
        if image_path and wants_report:
            if facility_subject and not semantic_subject:
                detection_steps = (
                    AgentStep("facility_detection", "facility_detection", expose_text=False),
                )
                dependencies = ("facility_detection",)
                reason = "DIOR 设施检测、证据分析、审核与报告生成"
            elif semantic_subject and not facility_subject:
                detection_steps = (
                    AgentStep("detection", "detection", expose_text=False),
                )
                dependencies = ("detection",)
                reason = "LoveDA 土地覆盖检测、证据分析、审核与报告生成"
            else:
                detection_steps = (
                    AgentStep("land_cover", "detection", expose_text=False),
                    AgentStep("facilities", "facility_detection", expose_text=False),
                )
                dependencies = ("land_cover", "facilities")
                reason = "LoveDA 土地覆盖与 DIOR 设施目标联合巡查报告"
            return TaskPlan(
                primary_route="report",
                reason=reason,
                steps=detection_steps
                + (
                    AgentStep("analysis", "analysis", dependencies, expose_text=False),
                    AgentStep("review", "review", ("analysis",), expose_text=False),
                    AgentStep("report", "report", ("review",)),
                ),
            )

        # 当前图片的 DIOR 导出先完成检测，再由 Export Agent 导出当前证据；
        # 无图片的 DIOR 导出则查询当前用户的历史设施检测记录。
        if wants_export and facility_subject and not wants_evaluation:
            if image_path:
                steps = (
                    AgentStep("facility_detection", "facility_detection", expose_text=False),
                    AgentStep("export", "export", ("facility_detection",)),
                )
            else:
                steps = (
                    AgentStep("analysis", "analysis", expose_text=False),
                    AgentStep("export", "export", ("analysis",)),
                )
            return TaskPlan(
                primary_route="export",
                reason="DIOR 设施目标检测数据导出",
                steps=steps,
            )

        # 无图片的 DIOR 报告基于用户历史记录生成，不触发缺少图片的推理节点。
        if wants_report and facility_subject:
            return TaskPlan(
                primary_route="report",
                reason="DIOR 历史设施检测统计、审核与报告生成",
                steps=(
                    AgentStep("analysis", "analysis", expose_text=False),
                    AgentStep("review", "review", ("analysis",), expose_text=False),
                    AgentStep("report", "report", ("review",)),
                ),
            )

        # A generic image-inspection request has no reliable single-model
        # interpretation. Run both complementary models; explicit semantic or
        # facility wording still selects only the requested model.
        if (
            image_path
            and not wants_report
            and image_inspection
            and (
                (facility_subject and semantic_subject)
                or (not facility_subject and not semantic_subject)
            )
        ):
            return TaskPlan(
                primary_route="combined_detection",
                reason="LoveDA 土地覆盖与 DIOR 设施目标联合检测",
                steps=(
                    AgentStep("land_cover", "detection"),
                    AgentStep("facilities", "facility_detection"),
                ),
            )

        if primary == "facility_detection":
            return TaskPlan(
                primary_route=primary,
                reason="DIOR 遥感设施目标检测",
                steps=(AgentStep(primary, primary),),
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
