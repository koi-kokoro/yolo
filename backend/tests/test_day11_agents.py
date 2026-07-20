"""Day 11 最小多 Agent 闭环测试（外部依赖均 mock）。"""

from __future__ import annotations

import json
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.agent.chat_agent import ChatAgent
from app.agent.evaluation_agent import EvaluationAgent
from app.agent.export_agent import ExportAgent
from app.agent.llm_streaming import LLMUnavailableError
from app.agent.qa_agent import QAAgent
from app.agent.report_agent import ReportAgent
from app.agent.tools.analysis_tools import create_analysis_tools
from app.agent.tools.report_tools import create_report_tools
from app.agent.tools.evaluation_tools import collect_evaluation_snapshot
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.supervisor import Supervisor
from app.rag.retriever import HybridRetriever, LocalDocumentRetriever, PgVectorRetriever
from app.services.chat_session_service import ChatMemoryService
from app.services.agent_export_service import AgentExportService
from app.services.chat_image_reference_service import ChatImageReferenceService
from app.api.chat import _requests_session_image


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
        ("生成最近7天巡查报告", None, "report"),
        ("查看当前模型评估结果", None, "evaluation"),
        ("导出最近7天巡查数据为 CSV", None, "export"),
        ("什么是 IoU", None, "qa"),
        ("什么是 LoveDA", None, "qa"),
        ("识别一下", None, "detection"),
        ("检测一下", None, "detection"),
        ("语义分割一下", None, "detection"),
        ("什么是语义分割", None, "qa"),
        ("你好", None, "chat"),
        ("请训练并发布模型", None, "chat"),
    ],
)
def test_supervisor_routes(message, image, expected):
    assert Supervisor().route(message, image) == expected


def test_supervisor_invalid_route_falls_back_chat():
    assert Supervisor().validate("training") == "chat"


@pytest.mark.parametrize(
    "message",
    [
        "识别一下",
        "检测一下",
        "分割一下",
        "语义分割一下",
        "帮我看看",
        "看看刚刚那张图",
        "分析上传的图片",
    ],
)
def test_short_image_commands_reuse_session_image(message):
    assert _requests_session_image(message) is True


def test_knowledge_question_does_not_reuse_session_image():
    assert _requests_session_image("什么是语义分割") is False


def test_analysis_tool_binds_authenticated_user():
    tools = {tool.name: tool for tool in create_analysis_tools(42)}
    assert "user_id" not in tools["detection_statistics"].args
    with patch(
        "app.agent.tools.analysis_tools.dashboard_service.get_statistics",
        return_value={"total_tasks": 1},
    ) as call:
        json.loads(tools["detection_statistics"].invoke({"days": 7}))
    call.assert_called_once_with(user_id=42, days=7)


def test_report_tool_binds_authenticated_user_and_collects_read_only_data():
    tool = create_report_tools(42)[0]
    assert "user_id" not in tool.args
    with patch(
        "app.agent.tools.report_tools.dashboard_service.get_statistics",
        return_value={"total_tasks": 1},
    ) as statistics, patch(
        "app.agent.tools.report_tools.dashboard_service.get_trend",
        return_value={"trend": []},
    ), patch(
        "app.agent.tools.report_tools.dashboard_service.get_class_distribution",
        return_value={"distribution": []},
    ), patch(
        "app.agent.tools.report_tools.history_service.get_summary",
        return_value={"total_tasks": 1},
    ), patch(
        "app.agent.tools.report_tools.history_service.list_tasks",
        return_value={"total": 0, "items": []},
    ):
        result = json.loads(tool.invoke({"days": 7}))
    assert result["period_days"] == 7
    statistics.assert_called_once_with(user_id=42, days=7)


def test_report_agent_understands_daily_weekly_and_monthly_periods():
    assert ReportAgent._days("生成巡查日报") == 1
    assert ReportAgent._days("生成巡查周报") == 7
    assert ReportAgent._days("生成巡查月报") == 30
    assert ReportAgent._days("生成最近90天报告") == 90


def test_evaluation_snapshot_removes_confusion_matrix_and_internal_paths():
    report = {
        "overall": {
            "miou": 0.5,
            "pixel_accuracy": 0.7,
            "per_class": [
                {"class_name": "water", "iou": 0.8, "support_pixels": 10}
            ],
            "confusion_matrix": [[1, 2], [3, 4]],
        }
    }
    models = [
        {
            "id": "deployed",
            "display_name": "模型",
            "best_miou": 0.5,
            "model_path": "C:\\private\\best.pt",
            "artifacts": [{"path": "C:\\private"}],
        }
    ]
    with patch(
        "app.agent.tools.evaluation_tools.semantic_model_ops.evaluate",
        return_value={"source": "cached", "report": report},
    ), patch(
        "app.agent.tools.evaluation_tools.model_management_service.models",
        return_value=models,
    ):
        result = collect_evaluation_snapshot()
    serialized = json.dumps(result, ensure_ascii=False)
    assert result["report"]["overall"]["miou"] == 0.5
    assert result["report"]["overall"]["per_class"][0]["display_name"] == "水体"
    assert "confusion_matrix" not in serialized
    assert "C:\\private" not in serialized


@pytest.mark.asyncio
async def test_evaluation_agent_llm_unavailable_returns_metric_summary():
    raw = json.dumps(
        {
            "source": "cached",
            "report": {
                "overall": {
                    "miou": 0.5,
                    "pixel_accuracy": 0.7,
                    "mean_dice_f1": 0.6,
                    "per_class": [
                        {"display_name": "水体", "iou": 0.8},
                        {"display_name": "裸地", "iou": 0.3},
                    ],
                }
            },
            "models": [],
        },
        ensure_ascii=False,
    )

    class FakeTool:
        name = "get_model_evaluation"

        @staticmethod
        def invoke(args):
            return raw

    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("offline")
        yield  # pragma: no cover

    with patch("app.agent.evaluation_agent.get_model_evaluation", FakeTool()), patch(
        "app.agent.evaluation_agent.stream_llm_text", unavailable
    ):
        events = [event async for event in EvaluationAgent().chat_stream("评估当前模型")]
    text = "".join(event.get("content", "") for event in events)
    assert "mIoU：50.00%" in text
    assert "最弱类别：裸地" in text
    assert "未在本次对话中重新运行" in text


def test_export_service_creates_user_isolated_json_and_csv(tmp_path):
    service = AgentExportService(tmp_path)
    evaluation = {
        "report": {
            "overall": {
                "miou": 0.5,
                "per_class": [{"display_name": "水体", "iou": 0.8}],
            }
        }
    }
    json_result = service.create(1, "evaluation", "json", evaluation)
    csv_result = service.create(1, "evaluation", "csv", evaluation)
    assert service.resolve(1, json_result["filename"]).is_file()
    assert service.resolve(1, csv_result["filename"]).read_text(
        encoding="utf-8-sig"
    ).startswith("domain,class_name")
    with pytest.raises(FileNotFoundError):
        service.resolve(2, json_result["filename"])
    with pytest.raises(FileNotFoundError):
        service.resolve(1, "../secret.json")


def test_export_agent_parses_type_format_and_period():
    assert ExportAgent._arguments("导出最近7天巡查数据为 CSV") == {
        "data_type": "patrol",
        "file_format": "csv",
        "days": 7,
    }
    assert ExportAgent._arguments("导出模型评估指标") == {
        "data_type": "evaluation",
        "file_format": "json",
        "days": 30,
    }
    assert ExportAgent._arguments("导出最近14天 DIOR 检测框 CSV") == {
        "data_type": "dior",
        "file_format": "csv",
        "days": 14,
    }


def test_export_download_uses_authenticated_user(client: TestClient, tmp_path):
    from app.api.auth import get_current_user

    class ExportUser:
        id = 77
        username = "export-user"

    output = tmp_path / "evaluation_test.json"
    output.write_text('{"ok": true}', encoding="utf-8")
    client.app.dependency_overrides[get_current_user] = lambda: ExportUser()
    try:
        with patch(
            "app.api.chat.agent_export_service.resolve", return_value=output
        ) as resolve:
            response = client.get("/api/chat/exports/evaluation_test.json")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        resolve.assert_called_once_with(77, "evaluation_test.json")
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_export_tool_result_is_persisted_for_session_reload(
    client: TestClient, db_session
):
    from app.api.auth import get_current_user
    from app.entity.db_models import ChatMessage

    class ExportUser:
        id = 1
        username = "export-user"

    result = {
        "filename": "evaluation_test.json",
        "format": "json",
        "data_type": "evaluation",
        "size_bytes": 12,
        "download_url": "/api/chat/exports/evaluation_test.json",
    }

    async def fake_stream(**kwargs):
        yield {"type": "agent_route", "agent": "export"}
        yield {"type": "tool_call", "tool": "export_platform_data", "input": {}}
        yield {
            "type": "tool_result",
            "tool": "export_platform_data",
            "result": json.dumps(result),
        }
        yield {"type": "text_chunk", "content": "导出完成"}

    client.app.dependency_overrides[get_current_user] = lambda: ExportUser()
    try:
        with patch("app.api.chat.orchestrator.chat_stream", fake_stream), patch(
            "app.api.chat.chat_memory_service.load", return_value=[]
        ), patch("app.api.chat.chat_memory_service.append_turn"):
            response = client.post("/api/chat/stream", json={"message": "导出评估指标"})
        assert response.status_code == 200
        assistant = (
            db_session.query(ChatMessage)
            .filter(ChatMessage.role == "assistant")
            .order_by(ChatMessage.id.desc())
            .first()
        )
        assert json.loads(assistant.tool_result)["filename"] == result["filename"]
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_report_agent_streams_grounded_report():
    raw = json.dumps(
        {
            "period_days": 7,
            "statistics": {"total_tasks": 2},
            "trend": {"trend": []},
            "class_distribution": {"distribution": []},
            "history_summary": {"total_tasks": 2},
            "recent_tasks": {"items": []},
        },
        ensure_ascii=False,
    )
    captured = []

    class FakeTool:
        name = "collect_patrol_report_data"

        @staticmethod
        def invoke(args):
            return raw

    async def fake_stream(messages, **kwargs):
        captured.extend(messages)
        yield "# 巡查报告"

    with patch("app.agent.report_agent.create_report_tools", return_value=[FakeTool()]), patch(
        "app.agent.report_agent.stream_llm_text", fake_stream
    ):
        events = [event async for event in ReportAgent().chat_stream("生成最近7天报告", 42)]
    assert [event["type"] for event in events] == ["tool_call", "tool_result", "text_chunk"]
    assert any('"total_tasks": 2' in content for _, content in captured)


@pytest.mark.asyncio
async def test_report_agent_llm_unavailable_returns_deterministic_report():
    raw = json.dumps(
        {
            "period_days": 7,
            "statistics": {"total_tasks": 2, "total_images": 3},
            "trend": {"trend": []},
            "class_distribution": {"distribution": []},
            "history_summary": {"total_tasks": 2, "status_counts": {"completed": 2}},
            "recent_tasks": {"items": []},
        },
        ensure_ascii=False,
    )

    class FakeTool:
        name = "collect_patrol_report_data"

        @staticmethod
        def invoke(args):
            return raw

    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("offline")
        yield  # pragma: no cover

    with patch("app.agent.report_agent.create_report_tools", return_value=[FakeTool()]), patch(
        "app.agent.report_agent.stream_llm_text", unavailable
    ):
        events = [event async for event in ReportAgent().chat_stream("生成最近7天报告", 42)]
    text = "".join(event.get("content", "") for event in events)
    assert "最近 7 天巡查报告" in text
    assert "检测任务：2 次" in text


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
        "evaluation": FakeAgent(),
        "export": FakeAgent(),
        "analysis": FakeAgent(),
        "qa": FakeAgent(),
        "report": FakeAgent(),
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


def test_chat_image_reference_is_user_isolated(tmp_path):
    service = ChatImageReferenceService(tmp_path)
    reference = service.save(1, "sample.png", io.BytesIO(b"image"))
    path = service.resolve(1, reference)
    assert path.parent == tmp_path.resolve() / "1"
    assert str(path) not in reference
    with pytest.raises(FileNotFoundError):
        service.resolve(2, reference)
    with pytest.raises(FileNotFoundError):
        service.resolve(1, "../sample")


def test_chat_reuses_safe_session_image_reference_without_exposing_path(
    client: TestClient, tmp_path
):
    from app.api.auth import get_current_user

    class ImageUser:
        id = 1
        username = "image-user"

    service = ChatImageReferenceService(tmp_path)
    client.app.dependency_overrides[get_current_user] = lambda: ImageUser()

    async def unavailable(*args, **kwargs):
        raise LLMUnavailableError("offline")
        yield  # pragma: no cover

    result = {
        "mode": "single",
        "filename": "safe.png",
        "image_width": 10,
        "image_height": 10,
        "annotated_image": "aGVsbG8=",
        "class_statistics": [
            {
                "name": "water",
                "display_name": "水体",
                "pixel_count": 100,
                "ratio": 1.0,
            }
        ],
    }
    try:
        with patch("app.api.chat.chat_image_reference_service", service):
            uploaded = client.post(
                "/api/chat/upload",
                files={"file": ("safe.png", b"image-bytes", "image/png")},
            )
            assert uploaded.status_code == 200
            upload_data = uploaded.json()
            assert set(upload_data) == {"image_ref"}
            reference = upload_data["image_ref"]

            session_id = client.post(
                "/api/chat/sessions", json={"title": "图片连续识别"}
            ).json()["id"]
            first = client.post(
                "/api/chat/stream",
                json={
                    "message": "先记住这张图片",
                    "session_id": session_id,
                    "image_ref": reference,
                },
            )
            assert first.status_code == 200
            assert "图片已接收" in first.text

            with patch(
                "app.agent.detection_agent.detection_chat_service.segment_single",
                return_value=result,
            ) as infer, patch(
                "app.agent.detection_agent.stream_llm_text", unavailable
            ):
                second = client.post(
                    "/api/chat/stream",
                    json={
                        "message": "识别一下",
                        "session_id": session_id,
                    },
                )

            assert second.status_code == 200
            assert '"agent": "detection"' in second.text
            assert "本地分割完成" in second.text
            inferred_path = infer.call_args.args[0]
            assert inferred_path == str(service.resolve(1, reference))
            assert inferred_path not in first.text
            assert inferred_path not in second.text
            assert reference not in first.text
            assert reference not in second.text
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_other_user_cannot_use_uploaded_image_reference(client: TestClient, tmp_path):
    from app.api.auth import get_current_user

    class Owner:
        id = 1
        username = "owner"

    class Other:
        id = 2
        username = "other"

    service = ChatImageReferenceService(tmp_path)
    reference = service.save(Owner.id, "safe.png", io.BytesIO(b"image"))
    with patch("app.api.chat.chat_image_reference_service", service):
        client.app.dependency_overrides[get_current_user] = lambda: Other()
        response = client.post(
            "/api/chat/stream",
            json={"message": "识别图片", "image_ref": reference},
        )
    client.app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 400
    assert "不属于当前用户" in json.dumps(response.json(), ensure_ascii=False)
