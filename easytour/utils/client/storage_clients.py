from __future__ import annotations

import logging
import os
import threading
from typing import Any

from dotenv import load_dotenv

load_dotenv()

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

        endpoint = _require_env('MINIO_ENDPOINT')
        access_key = _require_env('MINIO_ACCESS_KEY')
        secret_key = _require_env('MINIO_SECRET_KEY')
        secure = str(os.getenv('MINIO_SECURE', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        bucket_name = os.getenv('MINIO_BUCKET_NAME', '').strip()

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
        return MilvusClient(uri=_require_env('MILVUS_URL'))


def _require_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise EnvironmentError(f'{name} is empty')
    return value
