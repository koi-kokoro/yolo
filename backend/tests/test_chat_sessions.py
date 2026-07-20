"""会话 CRUD、游标分页、Redis 回源与连续上下文测试。"""

from unittest.mock import patch

from app.api.auth import get_current_user
from app.entity.db_models import ChatMessage
from app.services.chat_session_service import ChatSessionService


class AuthUser:
    id = 101
    username = "owner"


class OtherUser:
    id = 202
    username = "other"


def auth(client, user=AuthUser):
    client.app.dependency_overrides[get_current_user] = lambda: user()


def test_session_crud_pagination_cross_user_and_cascade(client, db_session):
    auth(client)
    created = client.post("/api/chat/sessions", json={"title": "第一会话"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert client.get("/api/chat/sessions").json()["total"] == 1
    renamed = client.patch(f"/api/chat/sessions/{session_id}", json={"title": "已重命名"})
    assert renamed.json()["title"] == "已重命名"

    service = ChatSessionService()
    session = service.owned(db_session, AuthUser.id, session_id)
    for index in range(4):
        service.save_turn(db_session, session, f"u{index}", f"a{index}", "qa")
    first = client.get(f"/api/chat/sessions/{session_id}/messages?limit=3").json()
    assert len(first["items"]) == 3 and first["has_more"] is True
    older = client.get(
        f"/api/chat/sessions/{session_id}/messages?limit=3&before_id={first['next_cursor']}"
    ).json()
    assert older["items"]

    auth(client, OtherUser)
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 404
    auth(client)
    with patch("app.services.chat_session_service.chat_memory_service.delete"):
        assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 204
    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count() == 0


def test_redis_miss_falls_back_to_database_and_refills(db_session):
    service = ChatSessionService()
    session = service.create(db_session, AuthUser.id, "回源")
    service.save_turn(db_session, session, "什么是 LoveDA？", "LoveDA 是数据集。", "qa")
    with patch("app.services.chat_session_service.chat_memory_service.load", return_value=[]), patch(
        "app.services.chat_session_service.chat_memory_service.replace"
    ) as refill:
        memory = service.load_memory(db_session, AuthUser.id, session)
    assert memory[-2]["role"] == "user"
    assert memory[-1]["content"] == "LoveDA 是数据集。"
    assert memory[-1]["route"] == "qa"
    refill.assert_called_once()


def test_first_successful_turn_generates_title_only_once(db_session):
    service = ChatSessionService()
    session = service.create(db_session, AuthUser.id, "新会话")

    service.save_turn(db_session, session, "请分析一下这张图片：5185.png", "分析完成。", "detection")
    assert session.title == "分析图片 5185.png"

    service.save_turn(db_session, session, "换一个完全不同的话题", "好的。", "chat")
    assert session.title == "分析图片 5185.png"


def test_manual_title_is_not_overwritten_by_first_turn(db_session):
    service = ChatSessionService()
    session = service.create(db_session, AuthUser.id, "我的固定标题")

    service.save_turn(db_session, session, "第一条消息", "回答。", "chat")

    assert session.title == "我的固定标题"


def test_continuous_loveda_followups_work_after_redis_miss(client):
    auth(client)
    session_id = client.post("/api/chat/sessions", json={"title": "连续知识问答"}).json()["id"]

    with patch("app.services.chat_session_service.chat_memory_service.load", return_value=[]), patch(
        "app.services.chat_session_service.chat_memory_service.replace"
    ), patch("app.api.chat.chat_memory_service.append_turn"):
        first = client.post(
            "/api/chat/stream", json={"message": "什么是 LoveDA", "session_id": session_id}
        )
        second = client.post(
            "/api/chat/stream", json={"message": "一共有几类", "session_id": session_id}
        )
        third = client.post(
            "/api/chat/stream", json={"message": "分别是什么", "session_id": session_id}
        )

    assert "loveda.md" in first.text
    for response in (second, third):
        assert '"agent": "qa"' in response.text
        assert "LoveDA 7 类" in response.text
        assert "背景" in response.text and "农业用地" in response.text
        assert "loveda.md" in response.text


def test_sessions_and_users_do_not_share_followup_topic(db_session):
    service = ChatSessionService()
    first = service.create(db_session, AuthUser.id, "一")
    second = service.create(db_session, AuthUser.id, "二")
    other = service.create(db_session, OtherUser.id, "其他用户")
    service.save_turn(db_session, first, "什么是 LoveDA", "回答", "qa")
    with patch("app.services.chat_session_service.chat_memory_service.load", return_value=[]), patch(
        "app.services.chat_session_service.chat_memory_service.replace"
    ):
        assert service.load_memory(db_session, AuthUser.id, second) == []
        assert service.load_memory(db_session, OtherUser.id, other) == []


def test_sse_always_emits_same_session(client):
    auth(client)
    session_id = client.post("/api/chat/sessions", json={"title": "连续"}).json()["id"]
    with patch("app.api.chat.chat_memory_service.load", return_value=[]), patch(
        "app.api.chat.chat_memory_service.append_turn"
    ), patch("app.agent.tools.knowledge_tools.rag_retriever.retrieve", return_value=[]):
        response = client.post(
            "/api/chat/stream", json={"message": "什么是 LoveDA？", "session_id": session_id}
        )
    assert response.status_code == 200
    assert f'"session_id": {session_id}' in response.text
    assert response.text.count('"type": "session"') == 1
