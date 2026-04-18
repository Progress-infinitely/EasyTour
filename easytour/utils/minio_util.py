from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import quote, unquote, urlsplit

from dotenv import load_dotenv
from minio import Minio

from easytour.core.config import get_shared_config
from easytour.utils.client.storage_clients import StorageClients

load_dotenv()

logger = logging.getLogger(__name__)


"""MinIO 便捷工具。

这一层和 `StorageClients` 的边界，也很值得单独讲清楚：

- `StorageClients`：负责“创建和复用 MinIO 客户端”
- `minio_util.py`：负责“围绕对象 URL / 对象名 / 访问地址做便捷处理”

所以这个文件更像：
“给对象存储这一层准备的小工具箱”。

它主要解决这类问题：
- 怎么拿到 MinIO 客户端
- 怎么拼一个对象 URL
- 怎么从 URL 反推出对象名
- 怎么生成浏览器可直接访问的图片链接
"""


def get_minio_client() -> Minio | None:
    """获取 MinIO 客户端。"""
    try:
        return StorageClients.get_minio_client()
    except Exception as exc:
        logger.error('MinIO client init failed: %s', exc)
        return None


def get_minio_bucket_name() -> str:
    """读取当前 bucket 名称。"""
    return get_shared_config().minio_bucket_name.strip().strip('/')


def get_minio_base_url() -> str:
    """拼出 MinIO 对外访问根地址。"""
    config = get_shared_config()
    endpoint = config.minio_endpoint.rstrip('/')
    if not endpoint:
        return ''
    secure = config.minio_secure
    scheme = 'https' if secure else 'http'
    return f'{scheme}://{endpoint}'


def build_minio_object_url(object_name: str) -> str:
    """把对象名拼成一个 URL。

    你可以把对象名理解成：
    “桶里面某个文件的内部路径”。

    这个函数的作用是：
    把这个内部路径，转换成可访问的完整 URL。
    """
    base_url = get_minio_base_url()
    bucket_name = get_minio_bucket_name()
    clean_object_name = str(object_name or '').strip().lstrip('/')
    if not base_url or not bucket_name or not clean_object_name:
        return ''
    return f"{base_url}/{bucket_name}/{quote(clean_object_name, safe='/')}"


def extract_object_name_from_minio_url(url: str) -> str:
    """从 MinIO URL 中反推出对象名。"""
    raw_url = str(url or '').strip()
    if not raw_url:
        return ''

    bucket_name = get_minio_bucket_name()
    endpoint = get_shared_config().minio_endpoint.rstrip('/')
    if not bucket_name or not endpoint:
        return ''

    parts = urlsplit(raw_url)
    if parts.netloc != endpoint:
        return ''

    clean_path = parts.path.lstrip('/')
    bucket_prefix = f'{bucket_name}/'
    if not clean_path.startswith(bucket_prefix):
        return ''

    return unquote(clean_path[len(bucket_prefix) :])


def get_browser_image_url(url: str, expires_seconds: int = 3600) -> str:
    """把内部对象地址转成浏览器更容易直接访问的图片 URL。

    优先返回带过期时间的预签名 URL；
    如果生成失败，再退回普通对象 URL。

    这样做的原因是：
    有些对象地址前端直接访问不了，
    但带签名的临时地址通常更适合浏览器直接打开。
    """
    raw_url = str(url or '').strip()
    object_name = extract_object_name_from_minio_url(raw_url)
    if not object_name:
        return raw_url

    client = get_minio_client()
    bucket_name = get_minio_bucket_name()
    if client is None or not bucket_name:
        return build_minio_object_url(object_name) or raw_url

    try:
        expire_seconds = max(int(expires_seconds), 1)
        return client.presigned_get_object(
            bucket_name,
            object_name,
            expires=timedelta(seconds=expire_seconds),
        )
    except Exception as exc:
        logger.error('Failed to build presigned MinIO URL: %s', exc)
        return build_minio_object_url(object_name) or raw_url


__all__ = [
    'build_minio_object_url',
    'extract_object_name_from_minio_url',
    'get_browser_image_url',
    'get_minio_base_url',
    'get_minio_bucket_name',
    'get_minio_client',
]
