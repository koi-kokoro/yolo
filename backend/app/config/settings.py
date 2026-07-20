"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application configuration."""

    APP_NAME: str = "RSOD Agent Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "rsod_agent"
    DB_USER: str = "rsod_admin"
    DB_PASSWORD: str = "rsod_admin"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    CHAT_MEMORY_TTL_SECONDS: int = 86400
    CHAT_MEMORY_MAX_MESSAGES: int = 12
    CHAT_MEMORY_MAX_CHARS: int = 2000

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rsod-agent-images"
    MINIO_SECURE: bool = False

    JWT_SECRET_KEY: str = "rsod-dev-secret-key-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ADMIN_REGISTRATION_CODE: str = ""

    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {
            "release",
            "production",
            "prod",
        }:
            return False
        return value

    SEMANTIC_DEPLOY_DIR: str = "../training/loveda_semantic/artifacts/current/deploy"
    MODEL_MANAGEMENT_TRUSTED_ROOT: str = "../training/loveda_semantic"
    MODEL_MANAGEMENT_DEPLOY_DIR: str = "artifacts/current/deploy"
    MODEL_MANAGEMENT_TRAINING_RUN_DIR: str = (
        "runs/v2_hr1024_yolo26s_sem_full_e50_b4_m1_20260713T0336Z"
    )
    MODEL_MANAGEMENT_STALE_SECONDS: int = 1800
    MODEL_MANAGEMENT_MAX_TEXT_BYTES: int = 2 * 1024 * 1024
    MODEL_MANAGEMENT_MAX_CSV_ROWS: int = 1000
    SEMANTIC_ENGINE: str = "onnx"
    SEMANTIC_FALLBACK_TO_ONNX: bool = True
    SEMANTIC_VERIFY_SHA256: bool = True
    SEMANTIC_ONNX_SHA256: str | None = None
    SEMANTIC_PT_SHA256: str = (
        "c147eff5a13d63183b4efb7d89417f7ace5354f708befd019908b5b8c2196ad9"
    )
    SEMANTIC_INPUT_SIZE: int = 512
    SEMANTIC_MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024
    SEMANTIC_MAX_DIMENSION: int = 10000
    SEMANTIC_MAX_PIXELS: int = 40_000_000
    SEMANTIC_EXECUTOR_WORKERS: int = 1
    SEMANTIC_QUEUE_SIZE: int = 8
    SEMANTIC_USER_ACTIVE_LIMIT: int = 2
    SEMANTIC_URL_EXPIRE_SECONDS: int = 900
    SEMANTIC_OVERLAY_ALPHA: float = 0.45
    SEMANTIC_PT_DEVICE: str = "cuda:0"

    # DIOR YOLO11 horizontal-box facility detection.  This is intentionally
    # isolated from the LoveDA semantic runtime because their output contracts
    # (boxes vs. masks) are different.
    DIOR_DEPLOY_DIR: str = "../training/dior/artifacts/current/deploy"
    DIOR_DEVICE: str = "cpu"
    DIOR_INPUT_SIZE: int = 640
    DIOR_CONF_THRESHOLD: float = 0.25
    DIOR_IOU_THRESHOLD: float = 0.45
    DIOR_VERIFY_SHA256: bool = True
    DIOR_MODEL_SHA256: str | None = None
    DIOR_EXECUTOR_WORKERS: int = 1
    DIOR_QUEUE_SIZE: int = 8
    DIOR_MAX_BATCH_IMAGES: int = 20

    # ── LoveDA 在线训练（可信固定入口，测试可通过环境覆盖）──
    ONLINE_TRAINING_ENABLED: bool = False
    ONLINE_TRAINING_TRUSTED_ROOT: str = "../training/loveda_semantic"
    ONLINE_TRAINING_WORKER: str = "online_training_worker.py"
    ONLINE_TRAINING_PYTHON: str = ""
    ONLINE_TRAINING_OUTPUT_ROOT: str = "online_runs"
    ONLINE_TRAINING_FULL_YAML: str = "loveda7.yaml"
    ONLINE_TRAINING_SMOKE_YAML: str = "loveda7_smoke.yaml"
    ONLINE_TRAINING_ALLOWED_MODELS: str = "yolo26n-sem.pt,yolo26s-sem.pt"
    ONLINE_TRAINING_ALLOWED_DEVICES: str = "cpu,0,cuda:0"
    ONLINE_TRAINING_DEFAULT_EPOCHS: int = 15
    ONLINE_TRAINING_MAX_EPOCHS: int = 50
    ONLINE_TRAINING_ALLOW_SMALL_EPOCHS: bool = False
    ONLINE_TRAINING_GLOBAL_ACTIVE_LIMIT: int = 1
    ONLINE_TRAINING_USER_ACTIVE_LIMIT: int = 1
    ONLINE_TRAINING_POLL_SECONDS: float = 1.0
    ONLINE_TRAINING_HEARTBEAT_SECONDS: float = 10.0
    ONLINE_TRAINING_STOP_GRACE_SECONDS: float = 15.0
    ONLINE_TRAINING_MAX_LOG_BYTES: int = 20 * 1024 * 1024
    ONLINE_TRAINING_LOG_TAIL_BYTES: int = 64 * 1024

    # ── LLM 配置（Day 8/11 智能对话）─────────────────
    # 密钥只能由环境变量注入，禁止在源码中提供可用默认值。
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen3.6-flash"

    CHAT_UPLOAD_DIR: str = "uploads/chat"
    RAG_DOCUMENT_DIR: str = "knowledge"
    # Embedding uses its own provider/key/base URL and never reuses the chat model.
    RAG_EMBEDDING_PROVIDER: str = "auto"
    RAG_EMBEDDING_API_KEY: str = ""
    RAG_EMBEDDING_BASE_URL: str = ""
    RAG_EMBEDDING_MODEL: str = "text-embedding-v3"
    RAG_EMBEDDING_DIMENSION: int = 1024
    RAG_TOP_K: int = 4
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 100

    USE_LOCAL_LLM: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    def _backend_relative_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        return (Path(__file__).resolve().parents[2] / path).resolve()

    @property
    def chat_upload_path(self) -> Path:
        return self._backend_relative_path(self.CHAT_UPLOAD_DIR)

    @property
    def rag_document_path(self) -> Path:
        return self._backend_relative_path(self.RAG_DOCUMENT_DIR)

    @property
    def semantic_deploy_path(self) -> Path:
        return self._backend_relative_path(self.SEMANTIC_DEPLOY_DIR)

    @property
    def dior_deploy_path(self) -> Path:
        return self._backend_relative_path(self.DIOR_DEPLOY_DIR)

    @property
    def model_management_trusted_root_path(self) -> Path:
        return self._backend_relative_path(self.MODEL_MANAGEMENT_TRUSTED_ROOT)

    @property
    def online_training_trusted_root_path(self) -> Path:
        return self._backend_relative_path(self.ONLINE_TRAINING_TRUSTED_ROOT)

    @property
    def online_training_worker_path(self) -> Path:
        return (
            self.online_training_trusted_root_path / self.ONLINE_TRAINING_WORKER
        ).resolve()

    @property
    def online_training_output_root_path(self) -> Path:
        return (
            self.online_training_trusted_root_path / self.ONLINE_TRAINING_OUTPUT_ROOT
        ).resolve()

    @property
    def online_training_allowed_models(self) -> set[str]:
        return {
            item.strip()
            for item in self.ONLINE_TRAINING_ALLOWED_MODELS.split(",")
            if item.strip()
        }

    @property
    def online_training_allowed_devices(self) -> set[str]:
        return {
            item.strip()
            for item in self.ONLINE_TRAINING_ALLOWED_DEVICES.split(",")
            if item.strip()
        }

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    class Config:
        # Resolve from src/backend instead of the caller's current directory so
        # Alembic, tests and the API process always use the same database.
        env_file = Path(__file__).resolve().parents[2] / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
