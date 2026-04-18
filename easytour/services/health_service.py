from __future__ import annotations

import os

from easytour.utils.client.storage_clients import StorageClients


def check_milvus_connected() -> bool:
    try:
        StorageClients.get_milvus_client().list_collections()
        return True
    except Exception:
        return False


def check_minio_connected() -> bool:
    try:
        client = StorageClients.get_minio_client()
        bucket_name = os.getenv('MINIO_BUCKET_NAME', '').strip()
        if bucket_name:
            client.bucket_exists(bucket_name)
        else:
            client.list_buckets()
        return True
    except Exception:
        return False
