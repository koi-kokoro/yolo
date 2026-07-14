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

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rsod-agent-images"
    MINIO_SECURE: bool = False

    JWT_SECRET_KEY: str = "rsod-dev-secret-key-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "production", "prod"}:
            return False
        return value

    SEMANTIC_DEPLOY_DIR: str = "../training/loveda_semantic/artifacts/current/deploy"
    MODEL_MANAGEMENT_TRUSTED_ROOT: str = "../training/loveda_semantic"
    MODEL_MANAGEMENT_DEPLOY_DIR: str = "artifacts/current/deploy"
    MODEL_MANAGEMENT_TRAINING_RUN_DIR: str = "runs/v2_hr1024_yolo26s_sem_full_e50_b4_m1_20260713T0336Z"
    MODEL_MANAGEMENT_STALE_SECONDS: int = 1800
    MODEL_MANAGEMENT_MAX_TEXT_BYTES: int = 2 * 1024 * 1024
    MODEL_MANAGEMENT_MAX_CSV_ROWS: int = 1000
    SEMANTIC_ENGINE: str = "onnx"
    SEMANTIC_FALLBACK_TO_ONNX: bool = True
    SEMANTIC_VERIFY_SHA256: bool = True
    SEMANTIC_ONNX_SHA256: str = "3a074b683f89c0c7a153efc6e9cdf81ac840e0b324cfefc3abc9f8022805d24c"
    SEMANTIC_PT_SHA256: str = "c147eff5a13d63183b4efb7d89417f7ace5354f708befd019908b5b8c2196ad9"
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

    # ── LLM 配置（Day 8 智能对话）─────────────────────
    OPENAI_API_KEY: str = "sk-your-openai-api-key"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    QWEN_API_KEY: str = "sk-your-qwen-api-key"
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    USE_LOCAL_LLM: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    def _backend_relative_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        return (Path(__file__).resolve().parents[2] / path).resolve()

    @property
    def semantic_deploy_path(self) -> Path:
        return self._backend_relative_path(self.SEMANTIC_DEPLOY_DIR)

    @property
    def model_management_trusted_root_path(self) -> Path:
        return self._backend_relative_path(self.MODEL_MANAGEMENT_TRUSTED_ROOT)

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
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
