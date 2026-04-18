from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass
class SharedConfig:
    mongo_url: str = field(default_factory=lambda: os.getenv('MONGO_URL', '').strip())
    mongo_db_name: str = field(default_factory=lambda: os.getenv('MONGO_DB_NAME', '').strip())

    minio_endpoint: str = field(default_factory=lambda: os.getenv('MINIO_ENDPOINT', '').strip())
    minio_access_key: str = field(default_factory=lambda: os.getenv('MINIO_ACCESS_KEY', '').strip())
    minio_secret_key: str = field(default_factory=lambda: os.getenv('MINIO_SECRET_KEY', '').strip())
    minio_bucket_name: str = field(default_factory=lambda: os.getenv('MINIO_BUCKET_NAME', '').strip())
    minio_secure: bool = field(default_factory=lambda: _get_bool_env('MINIO_SECURE', False))

    milvus_url: str = field(default_factory=lambda: os.getenv('MILVUS_URL', '').strip())
    milvus_timeout_seconds: float = field(default_factory=lambda: float(os.getenv('MILVUS_TIMEOUT_SECONDS', '8')))

    http_timeout_seconds: float = field(default_factory=lambda: float(os.getenv('HTTP_TIMEOUT_SECONDS', '30')))
    http_max_retries: int = field(default_factory=lambda: int(os.getenv('HTTP_MAX_RETRIES', '3')))
    http_retry_base_seconds: float = field(default_factory=lambda: float(os.getenv('HTTP_RETRY_BASE_SECONDS', '0.6')))
    http_retry_max_seconds: float = field(default_factory=lambda: float(os.getenv('HTTP_RETRY_MAX_SECONDS', '8')))
    http_max_concurrency: int = field(default_factory=lambda: int(os.getenv('HTTP_MAX_CONCURRENCY', '4')))

    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', '').strip())
    dashscope_api_key: str = field(default_factory=lambda: os.getenv('DASHSCOPE_API_KEY', '').strip())

    openai_api_base: str = field(default_factory=lambda: os.getenv('OPENAI_API_BASE', '').strip())
    dashscope_compatible_api_base: str = field(default_factory=lambda: os.getenv('DASHSCOPE_COMPATIBLE_API_BASE', '').strip())
    dashscope_api_base: str = field(default_factory=lambda: os.getenv('DASHSCOPE_API_BASE', '').strip())
    dashscope_http_api_base: str = field(default_factory=lambda: os.getenv('DASHSCOPE_HTTP_API_BASE', '').strip())
    dashscope_embedding_api_base: str = field(default_factory=lambda: os.getenv('DASHSCOPE_EMBEDDING_API_BASE', '').strip())
    dashscope_rerank_api_base: str = field(default_factory=lambda: os.getenv('DASHSCOPE_RERANK_API_BASE', '').strip())
    dashscope_rerank_compatible_api_base: str = field(
        default_factory=lambda: os.getenv('DASHSCOPE_RERANK_COMPATIBLE_API_BASE', '').strip()
    )

    embedding_provider: str = field(default_factory=lambda: os.getenv('EMBEDDING_PROVIDER', 'dashscope').strip().lower())
    llm_provider: str = field(default_factory=lambda: os.getenv('LLM_PROVIDER', 'dashscope').strip().lower())
    rerank_provider: str = field(default_factory=lambda: os.getenv('RERANK_PROVIDER', 'dashscope').strip().lower())

    model: str = field(default_factory=lambda: os.getenv('MODEL', '').strip())
    llm_default_model: str = field(default_factory=lambda: os.getenv('LLM_DEFAULT_MODEL', '').strip())
    item_model: str = field(default_factory=lambda: os.getenv('ITEM_MODEL', '').strip())
    embedding_model: str = field(default_factory=lambda: os.getenv('EMBEDDING_MODEL', 'text-embedding-v4').strip())
    rerank_model: str = field(default_factory=lambda: os.getenv('RERANK_MODEL', 'qwen3-rerank').strip())

    @property
    def provider_api_key(self) -> str:
        return self.openai_api_key or self.dashscope_api_key


_config: SharedConfig | None = None


def get_shared_config() -> SharedConfig:
    global _config
    if _config is None:
        _config = SharedConfig()
    return _config
