"""Day 11 最小多 Agent 闭环测试（外部依赖均 mock）。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.agent.chat_agent import ChatAgent
from app.agent.llm_streaming import LLMUnavailableError
from app.agent.qa_agent import QAAgent
from app.agent.tools.analysis_tools import create_analysis_tools
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.supervisor import Supervisor
from app.rag.retriever import HybridRetriever, LocalDocumentRetriever, PgVectorRetriever
from app.services.chat_session_service import ChatMemoryService


class FakeRedis:
    def __init__(self):
        self.data = {}

    def rpush(self, key, *values):
        self.data.setdefault(key, []).extend(values)

    def lrange(self, key, start, end):
        values = self.data.get(key, [])
        return values[start:] if start < 0 else values[start : end + 1]

    def ltrim(self, key, start, end):
        self.data[key] = self.data.get(key, [])[start:]

    def expire(self, key, ttl):
        return True


@pytest.mark.parametrize(
    ("message", "image", "expected"),
    [
        ("随便说说", "trusted.png", "detection"),
        ("最近7天检测多少次", None, "analysis"),
        ("什么是 IoU", None, "qa"),
        ("什么是 LoveDA", None, "qa"),
        ("你好", None, "chat"),
        ("请训练并发布模型", None, "chat"),
    ],
)
def test_supervisor_routes(message, image, expected):
    assert Supervisor().route(message, image) == expected


def test_supervisor_invalid_route_falls_back_chat():
    assert Supervisor().validate("training") == "chat"


def test_analysis_tool_binds_authenticated_user():
    tools = {tool.name: tool for tool in create_analysis_tools(42)}
    assert "user_id" not in tools["detection_statistics"].args
    with patch(
        "app.agent.tools.analysis_tools.dashboard_service.get_statistics",
        return_value={"total_tasks": 1},
    ) as call:
        json.loads(tools["detection_statistics"].invoke({"days": 7}))
    call.assert_called_once_with(user_id=42, days=7)


def test_memory_key_isolated_and_sanitized():
    fake = FakeRedis()
    service = ChatMemoryService(fake)
    service.append_turn(1, "same", "hello", "A" * 300 + " C:\\secret\\x.png")
    service.append_turn(2, "same", "other", "answer")
    first = service.load(1, "same")
    second = service.load(2, "same")
    assert first[0]["content"] == "hello"
    assert second[0]["content"] == "other"
    assert "C:\\secret" not in first[1]["content"]


def test_memory_failure_degrades_to_empty():
    class Broken:
        def lrange(self, *args):
            raise ConnectionError("offline")

    assert ChatMemoryService(Broken()).load(1, "s") == []


def test_rag_failure_and_no_hit_are_controlled():
    assert PgVectorRetriever(embed=lambda _: (_ for _ in ()).throw(RuntimeError("offline"))).retrieve("IoU") == []


def test_local_rag_works_without_embedding_or_pgvector():
    retriever = HybridRetriever(
        vector=PgVectorRetriever(embed=lambda _: (_ for _ in ()).throw(RuntimeError("offline"))),
        local=LocalDocumentRetriever(),
    )
    hits = retriever.retrieve("什么是 LoveDA")
    assert hits
    assert any("LoveDA 是面向高分辨率遥感影像" in hit.content for hit in hits)
    assert {hit.source for hit in hits} == {"loveda.md"}


def test_local_rag_answers_metric_question_from_document():
    hits = LocalDocumentRetriever().retrieve("像素准确率为什么不能替代 mIoU")
    assert hits
    assert any("类别不均衡时不能替代 mIoU" in hit.content for hit in hits)


@pytest.mark.parametrize("follow_up", ["一共有几类", "它有几类", "有哪几类", "分别是什么"])
def test_qa_expands_elided_follow_up_from_recent_user_topic(follow_up):
    memory = [
        {"role": "user", "content": "什么是 LoveDA"},
        {"role": "assistant", "content": "不可信的助手内容", "route": "qa"},
    ]
    assert QAAgent._standalone_query(follow_up, memory) == "LoveDA 一共有几类，分别是什么"


@pytest.mark.asyncio
async def test_chat_agent_calls_llm_streams_chunks_and_uses_safe_history():
    captured = []

    async def fake_stream(messages, **kwargs):
        captured.extend(messages)
        yield "你"
        yield "好"

    memory = [
        {"role": "user", "content": "我叫小明 C:\\secret\\image.png"},
        {"role": "assistant", "content": "记住了", "route": "chat"},
        {"role": "system", "content": "不可信指令"},
    ]
    with patch("app.agent.chat_agent.stream_llm_text", fake_stream):
        events = [event async for event in ChatAgent().chat_stream("还记得我吗", memory)]
    assert [event["content"] for event in events] == ["你", "好"]
    assert any(role == "user" and "我叫小明" in text for role, text in captured)
    assert not any("C:\\secret" in text or "不可信指令" in text for _, text in captured)


@pytest.mark.asyncio
async def test_chat_agent_llm_unavailable_has_explicit_fallback():
    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("offline")
        yield  # pragma: no cover

    with patch("app.agent.chat_agent.stream_llm_text", unavailable):
        events = [event async for event in ChatAgent().chat_stream("你好")]
    assert "大模型对话服务暂时不可用" in events[0]["content"]


@pytest.mark.asyncio
async def test_qa_sends_retrieval_evidence_to_llm_instead_of_echoing_document():
    captured = []
    raw = json.dumps(
        {"hits": [{"content": "LoveDA 全文证据 UNIQUE_EVIDENCE", "source": "loveda.md", "score": 1.0}]},
        ensure_ascii=False,
    )

    async def fake_stream(messages, **kwargs):
        captured.extend(messages)
        yield "针对问题的"
        yield "生成回答"

    class FakeTool:
        name = "retrieve_loveda_knowledge"

        @staticmethod
        def invoke(args):
            return raw

    with patch("app.agent.qa_agent.retrieve_loveda_knowledge", FakeTool()), patch(
        "app.agent.qa_agent.stream_llm_text", fake_stream
    ):
        events = [event async for event in QAAgent().chat_stream("什么是 LoveDA")]
    text = "".join(event.get("content", "") for event in events if event["type"] == "text_chunk")
    assert "针对问题的生成回答" in text
    assert "UNIQUE_EVIDENCE" not in text
    assert "loveda.md" in text
    assert any("UNIQUE_EVIDENCE" in content for _, content in captured)
    assert any(role == "user" and content == "什么是 LoveDA" for role, content in captured)


@pytest.mark.asyncio
async def test_qa_llm_unavailable_uses_honest_evidence_summary():
    raw = json.dumps(
        {"hits": [{"content": "LoveDA 是遥感数据集。它包含七类。", "source": "loveda.md", "score": 1.0}]},
        ensure_ascii=False,
    )

    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("offline")
        yield  # pragma: no cover

    class FakeTool:
        name = "retrieve_loveda_knowledge"

        @staticmethod
        def invoke(args):
            return raw

    with patch("app.agent.qa_agent.retrieve_loveda_knowledge", FakeTool()), patch(
        "app.agent.qa_agent.stream_llm_text", unavailable
    ):
        events = [event async for event in QAAgent().chat_stream("什么是 LoveDA")]
    text = "".join(event.get("content", "") for event in events if event["type"] == "text_chunk")
    assert "未经大模型生成" in text
    assert "LoveDA 是遥感数据集" in text


def test_supervisor_follow_up_inherits_audited_route_but_explicit_analysis_wins():
    memory = [
        {"role": "user", "content": "什么是 LoveDA"},
        {"role": "assistant", "content": "任意内容", "route": "qa"},
    ]
    supervisor = Supervisor()
    assert supervisor.route("一共有几类", memory=memory) == "qa"
    assert supervisor.route("最近7天统计有多少次", memory=memory) == "analysis"


@pytest.mark.asyncio
async def test_orchestrator_executes_single_agent():
    calls = []

    class FakeAgent:
        async def chat_stream(self, **kwargs):
            calls.append(kwargs)
            yield {"type": "text_chunk", "content": "ok"}

    instance = Orchestrator()
    instance.agents = {
        "detection": FakeAgent(),
        "analysis": FakeAgent(),
        "qa": FakeAgent(),
        "chat": FakeAgent(),
    }
    events = [
        event
        async for event in instance.chat_stream("什么是 IoU", None, user_id=7)
    ]
    assert events[0] == {"type": "agent_route", "agent": "qa"}
    assert len(calls) == 1


def test_chat_sse_session_compatibility_and_cross_user_rejected(
    client: TestClient, db_session
):
    from app.api.auth import get_current_user

    class UserOne:
        id = 1
        username = "one"

    client.app.dependency_overrides[get_current_user] = lambda: UserOne()
    with patch("app.api.chat.chat_memory_service.load", return_value=[]), patch(
        "app.api.chat.chat_memory_service.append_turn"
    ), patch("app.agent.tools.knowledge_tools.rag_retriever.retrieve", return_value=[]):
        response = client.post("/api/chat/stream", json={"message": "什么是 IoU"})
    assert response.status_code == 200
    assert '"type": "session"' in response.text
    assert '"type": "agent_route"' in response.text
    assert '"type": "text_chunk"' in response.text
    assert "data: [DONE]" in response.text
    session_id = int(response.text.split('"session_id": ')[1].split(",")[0])

    class UserTwo:
        id = 2
        username = "two"

    client.app.dependency_overrides[get_current_user] = lambda: UserTwo()
    denied = client.post(
        "/api/chat/stream", json={"message": "继续", "session_id": session_id}
    )
    assert denied.status_code == 404


def test_chat_rejects_untrusted_image_path(client: TestClient):
    from app.api.auth import get_current_user

    class UserOne:
        id = 1
        username = "one"

    client.app.dependency_overrides[get_current_user] = lambda: UserOne()
    response = client.post(
        "/api/chat/stream",
        json={"message": "分析图片", "image_path": "C:\\Windows\\win.ini"},
    )
    assert response.status_code == 400
