"""安全会话 CRUD、权威数据库历史与可降级 Redis 最近消息缓存。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.entity.db_models import ChatMessage, ChatSession

logger = get_logger(__name__)
_BASE64_RE = re.compile(r"(?:data:[^;]+;base64,)?[A-Za-z0-9+/]{256,}={0,2}")
_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)(?:[^\s,;]+[\\/])+[^\s,;]+")


class SessionAccessError(ValueError):
    """会话不存在或不属于当前用户；API 层统一映射为 404。"""


class ChatMemoryService:
    """Redis 只缓存最近清洗消息，任何故障均不影响 PostgreSQL。"""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                settings.REDIS_URL, decode_responses=True, socket_timeout=0.5
            )
        return self._client

    @staticmethod
    def _key(user_id: int, session_uuid: str) -> str:
        return f"chat:memory:user:{user_id}:session:{session_uuid}"

    @staticmethod
    def sanitize(content: str) -> str:
        value = _BASE64_RE.sub("[省略二进制数据]", str(content))
        value = _PATH_RE.sub("[省略服务端路径]", value)
        return value[: settings.CHAT_MEMORY_MAX_CHARS]

    @classmethod
    def clean_messages(cls, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for item in messages:
            if item.get("role") not in {"user", "assistant"} or not item.get("content"):
                continue
            message = {
                "role": str(item["role"]),
                "content": cls.sanitize(str(item["content"])),
            }
            # route 仅来自服务端持久化的 agent_used，用于省略追问路由，不作为事实来源。
            route = item.get("route") or item.get("agent_used")
            if item.get("role") == "assistant" and route in {"qa", "analysis", "detection", "chat"}:
                message["route"] = str(route)
            cleaned.append(message)
        # 从偶数边界开始，尽量只保留完整 user/assistant turns。
        cleaned = cleaned[-settings.CHAT_MEMORY_MAX_MESSAGES :]
        if cleaned and cleaned[0]["role"] == "assistant":
            cleaned = cleaned[1:]
        return cleaned

    def load(self, user_id: int, session_uuid: str) -> list[dict[str, str]]:
        try:
            values = self._get_client().lrange(
                self._key(user_id, session_uuid),
                -settings.CHAT_MEMORY_MAX_MESSAGES,
                -1,
            )
            return self.clean_messages([json.loads(value) for value in values])
        except Exception as exc:
            logger.warning("Redis chat memory unavailable: %s", exc)
            return []

    def replace(self, user_id: int, session_uuid: str, messages: list[dict[str, Any]]) -> None:
        try:
            key = self._key(user_id, session_uuid)
            client = self._get_client()
            client.delete(key)
            cleaned = self.clean_messages(messages)
            if cleaned:
                client.rpush(
                    key,
                    *(json.dumps(item, ensure_ascii=False) for item in cleaned),
                )
                client.expire(key, settings.CHAT_MEMORY_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Redis chat memory refill skipped: %s", exc)

    def append_turn(
        self,
        user_id: int,
        session_uuid: str,
        user_content: str,
        assistant_content: str,
        route: str | None = None,
    ) -> None:
        try:
            key = self._key(user_id, session_uuid)
            client = self._get_client()
            assistant = {"role": "assistant", "content": self.sanitize(assistant_content)}
            if route in {"qa", "analysis", "detection", "chat"}:
                assistant["route"] = route
            payloads = [
                json.dumps({"role": "user", "content": self.sanitize(user_content)}, ensure_ascii=False),
                json.dumps(assistant, ensure_ascii=False),
            ]
            client.rpush(key, *payloads)
            client.ltrim(key, -settings.CHAT_MEMORY_MAX_MESSAGES, -1)
            client.expire(key, settings.CHAT_MEMORY_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Redis chat memory write skipped: %s", exc)

    def delete(self, user_id: int, session_uuid: str) -> None:
        try:
            self._get_client().delete(self._key(user_id, session_uuid))
        except Exception as exc:
            logger.warning("Redis chat memory delete skipped: %s", exc)


class ChatSessionService:
    """所有读写统一使用 session_id 与 user_id 双条件。"""

    @staticmethod
    def automatic_title(value: str | None) -> str:
        title = re.sub(r"\s+", " ", ChatMemoryService.sanitize(value or "")).strip()
        return (title[:40] or "新会话")

    @staticmethod
    def owned(db: Session, user_id: int, session_id: int) -> ChatSession:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        ).first()
        if session is None:
            raise SessionAccessError("会话不存在")
        return session

    def create(self, db: Session, user_id: int, title: str | None = None) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            session_uuid=str(uuid.uuid4()),
            title=self.automatic_title(title),
            status="active",
            message_count=0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def get_or_create(
        self, db: Session, user_id: int, session_id: int | None, title: str
    ) -> tuple[ChatSession, bool]:
        if session_id is not None:
            return self.owned(db, user_id, session_id), False
        return self.create(db, user_id, title), True

    @staticmethod
    def list_sessions(db: Session, user_id: int, page: int, page_size: int):
        query = db.query(ChatSession).filter(ChatSession.user_id == user_id)
        total = query.count()
        items = query.order_by(
            ChatSession.last_message_at.desc(), ChatSession.created_at.desc()
        ).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def rename(self, db: Session, user_id: int, session_id: int, title: str) -> ChatSession:
        session = self.owned(db, user_id, session_id)
        session.title = self.automatic_title(title)
        db.commit()
        db.refresh(session)
        return session

    def delete(self, db: Session, user_id: int, session_id: int) -> None:
        session = self.owned(db, user_id, session_id)
        session_uuid = session.session_uuid
        db.delete(session)
        db.commit()
        chat_memory_service.delete(user_id, session_uuid)

    def messages(
        self, db: Session, user_id: int, session_id: int, limit: int, before_id: int | None
    ) -> tuple[list[ChatMessage], int | None, bool]:
        session = self.owned(db, user_id, session_id)
        query = db.query(ChatMessage).filter(ChatMessage.session_id == session.id)
        if before_id is not None:
            query = query.filter(ChatMessage.id < before_id)
        rows = query.order_by(ChatMessage.id.desc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        rows.reverse()
        return rows, (rows[0].id if has_more and rows else None), has_more

    def load_memory(self, db: Session, user_id: int, session: ChatSession) -> list[dict[str, str]]:
        cached = chat_memory_service.load(user_id, session.session_uuid)
        if cached:
            logger.info("Chat memory loaded: source=redis user_id=%s session_id=%s messages=%d", user_id, session.id, len(cached))
            return cached
        rows = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(
            ChatMessage.id.desc()
        ).limit(settings.CHAT_MEMORY_MAX_MESSAGES).all()
        memory = ChatMemoryService.clean_messages(
            [
                {"role": row.role, "content": row.content, "agent_used": row.agent_used}
                for row in reversed(rows)
            ]
        )
        logger.info("Chat memory loaded: source=database user_id=%s session_id=%s messages=%d", user_id, session.id, len(memory))
        if memory:
            chat_memory_service.replace(user_id, session.session_uuid, memory)
        return memory

    @staticmethod
    def save_turn(
        db: Session,
        session: ChatSession,
        user_content: str,
        assistant_content: str,
        agent_used: str,
        tool_calls: list[dict] | None = None,
    ) -> None:
        """成功整轮先原子提交数据库；调用方随后 best-effort 更新 Redis。"""
        safe_user = ChatMemoryService.sanitize(user_content)
        safe_assistant = ChatMemoryService.sanitize(assistant_content)
        db.add_all(
            [
                ChatMessage(session_id=session.id, role="user", content=safe_user),
                ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=safe_assistant,
                    agent_used=agent_used,
                    tool_calls=tool_calls or None,
                    tool_result=None,
                ),
            ]
        )
        session.message_count = (session.message_count or 0) + 2
        session.last_message_at = datetime.now()
        db.commit()


chat_memory_service = ChatMemoryService()
chat_session_service = ChatSessionService()
