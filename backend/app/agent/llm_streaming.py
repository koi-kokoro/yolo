"""Chat/QA 共用的安全消息构造与 LLM 流式调用。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from langchain_openai import ChatOpenAI

from app.config.settings import settings
from app.core.logger import get_logger
from app.services.chat_session_service import ChatMemoryService

logger = get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    """LLM 未配置或提供方调用失败；对外不得暴露底层异常。"""


def _configured_key(value: str, placeholder: str) -> str | None:
    """空值和示例占位符均不得被当作可用凭据。"""
    key = value.strip()
    return key if key and key != placeholder else None


def create_chat_llm(*, temperature: float = 0.3) -> ChatOpenAI:
    """按 Ollama > DeepSeek > Qwen > OpenAI 优先级创建兼容客户端。"""
    if settings.USE_LOCAL_LLM:
        provider = "ollama"
        model = settings.OLLAMA_MODEL
        kwargs = {
            "model": model,
            "api_key": "ollama",
            "base_url": f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
        }
    else:
        candidates = (
            (
                "deepseek",
                _configured_key(settings.DEEPSEEK_API_KEY, "sk-your-deepseek-api-key"),
                settings.DEEPSEEK_MODEL,
                settings.DEEPSEEK_BASE_URL,
            ),
            (
                "qwen",
                _configured_key(settings.QWEN_API_KEY, "sk-your-qwen-api-key"),
                settings.QWEN_MODEL,
                settings.QWEN_BASE_URL,
            ),
            (
                "openai",
                _configured_key(settings.OPENAI_API_KEY, "sk-your-openai-api-key"),
                settings.OPENAI_MODEL,
                settings.OPENAI_BASE_URL,
            ),
        )
        selected = next((item for item in candidates if item[1]), None)
        if selected is None:
            raise LLMUnavailableError("LLM 服务未配置")
        provider, api_key, model, base_url = selected
        kwargs = {"model": model, "api_key": api_key, "base_url": base_url}

    logger.info("Creating LLM client: provider=%s model=%s", provider, model)
    return ChatOpenAI(temperature=temperature, **kwargs)


def safe_history(memory: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """复用会话层的角色白名单、敏感内容清洗和消息/字符限长。"""
    return [
        {"role": item["role"], "content": item["content"]}
        for item in ChatMemoryService.clean_messages(memory or [])
    ]


def build_messages(
    system_prompt: str,
    message: str,
    memory: list[dict[str, Any]] | None = None,
    *,
    context: str | None = None,
) -> list[tuple[str, str]]:
    """构造不含 route、路径、二进制和非 user/assistant 角色的模型消息。"""
    messages: list[tuple[str, str]] = [("system", system_prompt)]
    messages.extend((item["role"], item["content"]) for item in safe_history(memory))
    if context:
        messages.append(("system", context))
    messages.append(("user", ChatMemoryService.sanitize(message)))
    return messages


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


async def stream_llm_text(
    messages: list[tuple[str, str]], *, temperature: float = 0.3
) -> AsyncGenerator[str, None]:
    """统一流式调用入口，便于 Chat/QA mock，并归一化提供方内容块。"""
    try:
        llm = create_chat_llm(temperature=temperature)
        async for chunk in llm.astream(messages):
            text = _chunk_text(chunk)
            if text:
                yield text
    except LLMUnavailableError:
        raise
    except Exception as exc:
        raise LLMUnavailableError("LLM 服务暂时不可用") from exc
