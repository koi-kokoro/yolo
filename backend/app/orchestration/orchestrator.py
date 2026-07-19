"""每轮只执行一个子 Agent 的最小编排器。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from app.agent.analysis_agent import AnalysisAgent
from app.agent.chat_agent import chat_agent
from app.agent.detection_agent import detection_agent
from app.agent.qa_agent import qa_agent
from app.orchestration.supervisor import supervisor


class Orchestrator:
    def __init__(self) -> None:
        self.agents = {
            "detection": detection_agent,
            "analysis": AnalysisAgent(),
            "qa": qa_agent,
            "chat": chat_agent,
        }

    async def chat_stream(
        self,
        message: str,
        image_path: str | None,
        user_id: int,
        scene_id: int | None = None,
        memory: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        route = supervisor.validate(supervisor.route(message, image_path, memory or []))
        yield {"type": "agent_route", "agent": route}
        agent = self.agents[route]
        kwargs = {
            "message": message,
            "image_path": image_path,
            "user_id": user_id,
            "scene_id": scene_id,
            "memory": memory or [],
        }
        async for event in agent.chat_stream(**kwargs):
            yield event


orchestrator = Orchestrator()
