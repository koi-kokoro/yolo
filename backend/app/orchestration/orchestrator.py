"""兼容单 Agent 请求、支持证据审核串行工作流的轻量编排器。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from app.agent.analysis_agent import AnalysisAgent
from app.agent.chat_agent import chat_agent
from app.agent.detection_agent import detection_agent
from app.agent.facility_detection_agent import facility_detection_agent
from app.agent.evaluation_agent import evaluation_agent
from app.agent.export_agent import export_agent
from app.agent.qa_agent import qa_agent
from app.agent.report_agent import report_agent
from app.agent.review_agent import review_agent
from app.orchestration.supervisor import supervisor
from app.orchestration.workflow import AgentStep, WorkflowState


class Orchestrator:
    def __init__(self) -> None:
        self.agents = {
            "detection": detection_agent,
            "facility_detection": facility_detection_agent,
            "evaluation": evaluation_agent,
            "export": export_agent,
            "analysis": AnalysisAgent(),
            "qa": qa_agent,
            "report": report_agent,
            "review": review_agent,
            "chat": chat_agent,
        }

    async def _execute_step(
        self,
        step: AgentStep,
        state: WorkflowState,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        state.node_statuses[step.id] = "running"
        yield {
            "type": "workflow_node",
            "workflow_id": state.workflow_id,
            "node": step.id,
            "agent": step.agent,
            "status": "running",
        }
        yield {"type": "agent_route", "agent": step.agent}
        failed = False
        try:
            agent_kwargs = dict(kwargs)
            agent_kwargs["workflow_state"] = state.agent_context()
            async for event in self.agents[step.agent].chat_stream(**agent_kwargs):
                state.record_event(step, event)
                if event.get("type") == "error":
                    failed = True
                if step.expose_text or event.get("type") != "text_chunk":
                    yield event
        except Exception as exc:
            failed = True
            state.errors.append({"node_id": step.id, "message": type(exc).__name__})
            yield {"type": "error", "content": f"工作流节点 {step.id} 执行失败。"}
        state.node_statuses[step.id] = "failed" if failed else "completed"
        yield {
            "type": "workflow_node",
            "workflow_id": state.workflow_id,
            "node": step.id,
            "agent": step.agent,
            "status": state.node_statuses[step.id],
        }

    async def chat_stream(
        self,
        message: str,
        image_path: str | None,
        user_id: int,
        scene_id: int | None = None,
        memory: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        plan = supervisor.plan(message, image_path, memory or [])
        state = WorkflowState(plan)
        kwargs = {
            "message": message,
            "image_path": image_path,
            "user_id": user_id,
            "scene_id": scene_id,
            "memory": memory or [],
        }
        if not plan.is_workflow:
            step = plan.steps[0]
            yield {"type": "agent_route", "agent": step.agent}
            agent_kwargs = dict(kwargs)
            agent_kwargs["workflow_state"] = state.agent_context()
            async for event in self.agents[step.agent].chat_stream(**agent_kwargs):
                yield event
            return

        yield state.public_event()

        for step in plan.steps:
            blocked = [
                dependency
                for dependency in step.depends_on
                if state.node_statuses.get(dependency) != "completed"
            ]
            if blocked:
                state.node_statuses[step.id] = "skipped"
                yield {
                    "type": "workflow_node",
                    "workflow_id": state.workflow_id,
                    "node": step.id,
                    "agent": step.agent,
                    "status": "skipped",
                    "blocked_by": blocked,
                }
                continue

            async for event in self._execute_step(step, state, kwargs):
                yield event

            if step.agent == "review" and not (state.review or {}).get("passed"):
                analysis_step = next(
                    (item for item in plan.steps if item.agent == "analysis"), None
                )
                while analysis_step and state.review_attempts < 1 and not (
                    state.review or {}
                ).get("passed"):
                    state.review_attempts += 1
                    yield {
                        "type": "workflow_retry",
                        "workflow_id": state.workflow_id,
                        "node": analysis_step.id,
                        "attempt": state.review_attempts + 1,
                        "reason": "review_failed",
                    }
                    async for event in self._execute_step(analysis_step, state, kwargs):
                        yield event
                    async for event in self._execute_step(step, state, kwargs):
                        yield event
                if not (state.review or {}).get("passed"):
                    state.node_statuses[step.id] = "failed"
                    yield {
                        "type": "workflow_node",
                        "workflow_id": state.workflow_id,
                        "node": step.id,
                        "agent": step.agent,
                        "status": "failed",
                    }
                    yield {
                        "type": "error",
                        "content": "结构化分析未通过证据审核，已停止生成报告。",
                    }
                    break

        if plan.is_workflow:
            completed = all(
                status == "completed" for status in state.node_statuses.values()
            )
            yield {
                "type": "workflow_complete",
                "workflow_id": state.workflow_id,
                "status": "completed" if completed else "partial",
                "node_statuses": state.node_statuses,
                "review": state.review,
            }


orchestrator = Orchestrator()
