"""多 Agent 工作流的轻量任务计划与请求级共享状态。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any


_BINARY_KEYS = {
    "annotated_image",
    "annotated_image_base64",
    "base64",
    "color_mask",
    "index_mask",
    "overlay",
}
_PATH_KEYS = {"absolute_path", "image_path", "image_paths", "path", "zip_path"}
_MAX_TEXT = 4000


def compact_evidence(value: Any) -> Any:
    """移除不应进入共享状态/LLM 上下文的二进制、路径和超长字段。"""
    if isinstance(value, dict):
        return {
            str(key): compact_evidence(item)
            for key, item in value.items()
            if str(key) not in _BINARY_KEYS
            and str(key) not in _PATH_KEYS
            and not str(key).lower().endswith(("_path", "_paths"))
        }
    if isinstance(value, list):
        return [compact_evidence(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    return value


def parse_tool_result(value: Any) -> Any:
    """尽量解析 Agent 的 JSON 工具结果，失败时保留安全文本。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            pass
    return compact_evidence(value)


def build_land_cover_analysis(detection: dict[str, Any]) -> dict[str, Any]:
    """从原始类别数组生成可审核结论，并保留排序前的证据索引。"""
    indexed_statistics = list(enumerate(detection.get("class_statistics") or []))
    statistics = sorted(
        indexed_statistics,
        key=lambda pair: int(pair[1].get("pixel_count") or 0),
        reverse=True,
    )
    valid = [
        pair for pair in statistics if int(pair[1].get("pixel_count") or 0) > 0
    ]
    total = sum(int(item.get("pixel_count") or 0) for _, item in valid) or 1
    claims: list[dict[str, Any]] = []
    for source_index, item in valid[:5]:
        count = int(item.get("pixel_count") or 0)
        source_ratio = item.get("ratio")
        ratio = float(source_ratio) if source_ratio is not None else count / total
        name = item.get("display_name") or item.get("name") or "未知类别"
        if source_ratio is None:
            text = f"{name}在当前分割结果中的像素数量为 {count}。"
            evidence_ref = (
                f"tool_results.detection.class_statistics[{source_index}].pixel_count"
            )
            observed_value: Any = item.get("pixel_count")
        else:
            text = f"{name}在当前分割结果中的像素占比为 {ratio * 100:.2f}% 。"
            evidence_ref = (
                f"tool_results.detection.class_statistics[{source_index}].ratio"
            )
            observed_value = source_ratio
        claims.append(
            {
                "text": text,
                "claim_type": "observation",
                "evidence_ref": evidence_ref,
                "observed_value": observed_value,
            }
        )
    if not claims:
        claims.append(
            {
                "text": "当前分割结果没有记录到有效类别像素，建议人工检查输入影像。",
                "claim_type": "recommendation",
                "evidence_ref": "tool_results.detection.class_statistics",
                "observed_value": 0,
            }
        )
    return {
        "scope": "current_image",
        "claims": claims,
        "summary": "；".join(item["text"] for item in claims[:3]),
    }


@dataclass(frozen=True)
class AgentStep:
    id: str
    agent: str
    depends_on: tuple[str, ...] = ()
    expose_text: bool = True


@dataclass(frozen=True)
class TaskPlan:
    primary_route: str
    steps: tuple[AgentStep, ...]
    reason: str

    @property
    def is_workflow(self) -> bool:
        return len(self.steps) > 1

    def public_dict(self) -> dict[str, Any]:
        return {
            "primary_route": self.primary_route,
            "reason": self.reason,
            "steps": [
                {
                    "id": step.id,
                    "agent": step.agent,
                    "depends_on": list(step.depends_on),
                }
                for step in self.steps
            ],
        }


@dataclass
class WorkflowState:
    """单个请求内共享的结构化状态；大文件仅允许保存清洗后引用。"""

    plan: TaskPlan
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    node_statuses: dict[str, str] = field(default_factory=dict)
    evidence_pack: dict[str, Any] = field(
        default_factory=lambda: {"tool_results": {}, "analysis": None}
    )
    node_outputs: dict[str, str] = field(default_factory=dict)
    review: dict[str, Any] | None = None
    review_attempts: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node_statuses = {step.id: "pending" for step in self.plan.steps}

    def agent_context(self) -> dict[str, Any]:
        """提供给 Agent 的只读快照，避免 Agent 直接修改编排器状态。"""
        return compact_evidence(
            {
                "workflow_id": self.workflow_id,
                "plan": self.plan.public_dict(),
                "node_statuses": self.node_statuses,
                "evidence_pack": self.evidence_pack,
                "review": self.review,
                "review_attempts": self.review_attempts,
            }
        )

    def record_event(self, step: AgentStep, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "tool_result":
            self.evidence_pack["tool_results"][step.id] = parse_tool_result(
                event.get("result")
            )
        elif kind == "analysis_result":
            self.evidence_pack["analysis"] = compact_evidence(event.get("result"))
        elif kind == "review_result":
            result = compact_evidence(event.get("result"))
            self.review = result if isinstance(result, dict) else {"passed": False}
        elif kind == "text_chunk":
            current = self.node_outputs.get(step.id, "")
            self.node_outputs[step.id] = (current + str(event.get("content", "")))[
                :_MAX_TEXT
            ]
        elif kind == "error":
            self.errors.append(
                {"node_id": step.id, "message": str(event.get("content", "执行失败"))}
            )

    def public_event(self) -> dict[str, Any]:
        return {
            "type": "workflow_plan",
            "workflow_id": self.workflow_id,
            "plan": self.plan.public_dict(),
        }
