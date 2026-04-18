from __future__ import annotations

import logging
import threading
from typing import Any

from easytour.core.config import get_shared_config

logger = logging.getLogger(__name__)

try:
    from minio import Minio
except Exception:  # pragma: no cover
    Minio = None

try:
    from pymilvus import MilvusClient
except Exception:  # pragma: no cover
    MilvusClient = None


class StorageClients:
    _minio_client: Any | None = None
    _minio_lock = threading.Lock()

    _milvus_client: Any | None = None
    _milvus_lock = threading.Lock()

    @classmethod
    def get_minio_client(cls):
        with cls._minio_lock:
            if cls._minio_client is None:
                cls._minio_client = cls._create_minio_client()
            return cls._minio_client

    @classmethod
    def get_milvus_client(cls):
        with cls._milvus_lock:
            if cls._milvus_client is None:
                cls._milvus_client = cls._create_milvus_client()
            return cls._milvus_client

    @classmethod
    def _create_minio_client(cls):
        if Minio is None:
            raise RuntimeError('minio is not installed')

        config = get_shared_config()
        endpoint = _require_config_value(config.minio_endpoint, 'MINIO_ENDPOINT')
        access_key = _require_config_value(config.minio_access_key, 'MINIO_ACCESS_KEY')
        secret_key = _require_config_value(config.minio_secret_key, 'MINIO_SECRET_KEY')
        secure = config.minio_secure
        bucket_name = config.minio_bucket_name

        client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if bucket_name:
            try:
                if not client.bucket_exists(bucket_name):
                    client.make_bucket(bucket_name)
            except Exception as exc:  # pragma: no cover - infra dependent
                logger.warning('MinIO bucket check failed: %s', exc)
        return client

    @classmethod
    def _create_milvus_client(cls):
        if MilvusClient is None:
            raise RuntimeError('pymilvus is not installed')
        config = get_shared_config()
        milvus_url = _require_config_value(config.milvus_url, 'MILVUS_URL')
        return MilvusClient(uri=milvus_url)


def _require_config_value(value: str, name: str) -> str:
    normalized = str(value or '').strip()
    if not normalized:
        raise EnvironmentError(f'{name} is empty')
    return normalized
