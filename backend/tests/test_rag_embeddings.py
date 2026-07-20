"""RAG embedding provider selection tests; all network clients are mocked."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import settings
from app.rag.retriever import EmbeddingService


@pytest.fixture
def embedding_settings(monkeypatch):
    values = {
        "RAG_EMBEDDING_PROVIDER": "auto",
        "RAG_EMBEDDING_API_KEY": "",
        "RAG_EMBEDDING_BASE_URL": "",
        "RAG_EMBEDDING_MODEL": "configured-embedding-model",
        "RAG_EMBEDDING_DIMENSION": 3,
        "QWEN_API_KEY": "",
        "QWEN_BASE_URL": "https://qwen.example/v1",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "https://openai.example/v1",
        "DEEPSEEK_API_KEY": "",
        "DEEPSEEK_BASE_URL": "https://deepseek.example/v1",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return settings


def fake_openai_response(vector):
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector)])


def test_explicit_deepseek_uses_rag_model_and_deepseek_endpoint(embedding_settings, monkeypatch):
    embedding_settings.RAG_EMBEDDING_PROVIDER = "deepseek"
    embedding_settings.DEEPSEEK_API_KEY = "deepseek-embedding-key"
    embedding_settings.DEEPSEEK_BASE_URL = "https://embedding.deepseek.example/v1"
    create = MagicMock(return_value=fake_openai_response([0.1, 0.2, 0.3]))
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    with patch("openai.OpenAI", return_value=client) as openai_client:
        vector = EmbeddingService().embed("query")

    assert vector == [0.1, 0.2, 0.3]
    create.assert_called_once_with(
        model="configured-embedding-model",
        input="query",
    )
    openai_client.assert_called_once_with(
        api_key="deepseek-embedding-key",
        base_url="https://embedding.deepseek.example/v1",
    )
    assert client.embeddings.create


def test_explicit_deepseek_can_override_key_and_base_url_with_rag_values(
    embedding_settings,
):
    embedding_settings.RAG_EMBEDDING_PROVIDER = "deepseek"
    embedding_settings.RAG_EMBEDDING_API_KEY = "rag-key"
    embedding_settings.RAG_EMBEDDING_BASE_URL = "https://custom.example/v1"
    embedding_settings.DEEPSEEK_API_KEY = "chat-provider-key"
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **kwargs: fake_openai_response([0.1, 0.2, 0.3]))
    )

    with patch("openai.OpenAI", return_value=client) as openai_client:
        EmbeddingService().embed("query")

    openai_client.assert_called_once_with(
        api_key="rag-key",
        base_url="https://custom.example/v1",
    )


def test_auto_preserves_qwen_then_openai_then_deepseek_fallback(embedding_settings):
    embedding_settings.QWEN_API_KEY = "qwen-key"
    embedding_settings.OPENAI_API_KEY = "openai-key"
    embedding_settings.DEEPSEEK_API_KEY = "deepseek-key"
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **kwargs: fake_openai_response([0.1, 0.2, 0.3]))
    )

    with patch("openai.OpenAI", return_value=client) as openai_client:
        EmbeddingService().embed("query")

    openai_client.assert_called_once_with(
        api_key="qwen-key",
        base_url="https://qwen.example/v1",
    )

    embedding_settings.QWEN_API_KEY = ""
    with patch("openai.OpenAI", return_value=client) as openai_client:
        EmbeddingService().embed("query")
    openai_client.assert_called_once_with(
        api_key="openai-key",
        base_url="https://openai.example/v1",
    )

    embedding_settings.OPENAI_API_KEY = ""
    with patch("openai.OpenAI", return_value=client) as openai_client:
        EmbeddingService().embed("query")
    openai_client.assert_called_once_with(
        api_key="deepseek-key",
        base_url="https://deepseek.example/v1",
    )


def test_auto_uses_explicit_rag_key_and_base_url(embedding_settings):
    embedding_settings.RAG_EMBEDDING_API_KEY = "rag-key"
    embedding_settings.RAG_EMBEDDING_BASE_URL = "https://custom.example/v1"
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **kwargs: fake_openai_response([0.1, 0.2, 0.3]))
    )

    with patch("openai.OpenAI", return_value=client) as openai_client:
        EmbeddingService().embed("query")

    openai_client.assert_called_once_with(
        api_key="rag-key",
        base_url="https://custom.example/v1",
    )


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        ("unsupported", "不支持的 embedding provider"),
        ("deepseek", "embedding provider deepseek 未配置 API key"),
    ],
)
def test_provider_configuration_errors_are_controlled(embedding_settings, provider, message):
    embedding_settings.RAG_EMBEDDING_PROVIDER = provider
    with pytest.raises(RuntimeError, match=message):
        EmbeddingService().embed("query")


def test_auto_without_any_key_is_controlled(embedding_settings):
    with pytest.raises(RuntimeError, match="embedding 服务未配置 API key"):
        EmbeddingService().embed("query")


def test_partial_custom_rag_configuration_is_rejected(embedding_settings):
    embedding_settings.RAG_EMBEDDING_API_KEY = "rag-key"
    with pytest.raises(RuntimeError, match="embedding provider custom 未配置 base URL"):
        EmbeddingService().embed("query")


def test_embedding_dimension_mismatch_is_controlled(embedding_settings):
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **kwargs: fake_openai_response([0.1, 0.2]))
    )
    embedding_settings.OPENAI_API_KEY = "openai-key"

    with patch("openai.OpenAI", return_value=client):
        with pytest.raises(RuntimeError, match="embedding 维度与配置不一致"):
            EmbeddingService().embed("query")
