"""统一 LLM 流式层的提供方选择与 DeepSeek 回归测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent import chat_agent, llm_streaming, qa_agent
from app.agent.llm_streaming import LLMUnavailableError, create_chat_llm, stream_llm_text
from app.config.settings import settings


def _clear_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "USE_LOCAL_LLM", False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")


def test_only_deepseek_uses_configured_openai_compatible_client(monkeypatch):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setattr(settings, "DEEPSEEK_BASE_URL", "https://deepseek.example/v1")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "deepseek-chat-test")

    with patch("app.agent.llm_streaming.ChatOpenAI") as client:
        create_chat_llm(temperature=0.25)

    client.assert_called_once_with(
        model="deepseek-chat-test",
        api_key="deepseek-test-key",
        base_url="https://deepseek.example/v1",
        temperature=0.25,
    )


@pytest.mark.asyncio
async def test_deepseek_compatible_stream_is_consumed_by_unified_layer(monkeypatch):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-test-key")

    class FakeDeepSeekClient:
        async def astream(self, messages):
            assert messages == [("user", "你好")]
            yield SimpleNamespace(content="你")
            yield SimpleNamespace(content=[{"text": "好"}])

    with patch("app.agent.llm_streaming.ChatOpenAI", return_value=FakeDeepSeekClient()):
        chunks = [chunk async for chunk in stream_llm_text([("user", "你好")])]

    assert chunks == ["你", "好"]


def test_provider_priority_is_ollama_then_deepseek_then_qwen_then_openai(monkeypatch):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "qwen-test-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-test-key")

    with patch("app.agent.llm_streaming.ChatOpenAI") as client:
        create_chat_llm()
        assert client.call_args.kwargs["model"] == settings.DEEPSEEK_MODEL

        monkeypatch.setattr(settings, "USE_LOCAL_LLM", True)
        create_chat_llm()
        assert client.call_args.kwargs["model"] == settings.OLLAMA_MODEL
        assert client.call_args.kwargs["base_url"] == f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1"


def test_unconfigured_deepseek_does_not_block_existing_cloud_providers(monkeypatch):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-your-deepseek-api-key")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "qwen-test-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-test-key")

    with patch("app.agent.llm_streaming.ChatOpenAI") as client:
        create_chat_llm()
        assert client.call_args.kwargs["model"] == settings.QWEN_MODEL

        monkeypatch.setattr(settings, "QWEN_API_KEY", "")
        create_chat_llm()
        assert client.call_args.kwargs["model"] == settings.OPENAI_MODEL


@pytest.mark.parametrize(
    ("provider", "key_attr", "model_attr", "expected_model"),
    [
        ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-only"),
        ("qwen", "QWEN_API_KEY", "QWEN_MODEL", "qwen-only"),
        ("openai", "OPENAI_API_KEY", "OPENAI_MODEL", "openai-only"),
    ],
)
def test_each_cloud_provider_can_be_selected_alone(
    monkeypatch, provider, key_attr, model_attr, expected_model
):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, key_attr, f"{provider}-key")
    monkeypatch.setattr(settings, model_attr, expected_model)
    with patch("app.agent.llm_streaming.ChatOpenAI") as client:
        create_chat_llm()
    assert client.call_args.kwargs["model"] == expected_model
    assert client.call_args.kwargs["api_key"] == f"{provider}-key"


def test_ollama_can_be_selected_without_cloud_credentials(monkeypatch):
    _clear_provider_settings(monkeypatch)
    monkeypatch.setattr(settings, "USE_LOCAL_LLM", True)
    with patch("app.agent.llm_streaming.ChatOpenAI") as client:
        create_chat_llm()
    assert client.call_args.kwargs["model"] == settings.OLLAMA_MODEL
    assert client.call_args.kwargs["api_key"] == "ollama"


def test_no_provider_still_raises_controlled_unavailable_error(monkeypatch):
    _clear_provider_settings(monkeypatch)
    with pytest.raises(LLMUnavailableError, match="LLM 服务未配置"):
        create_chat_llm()


def test_chat_qa_and_detection_reuse_unified_llm_layer():
    from app.agent import detection_agent

    assert chat_agent.stream_llm_text is llm_streaming.stream_llm_text
    assert qa_agent.stream_llm_text is llm_streaming.stream_llm_text
    assert detection_agent.create_chat_llm is llm_streaming.create_chat_llm
    assert not hasattr(detection_agent, "_create_llm")
