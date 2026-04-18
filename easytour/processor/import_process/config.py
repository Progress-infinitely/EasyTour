from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Set

from dotenv import load_dotenv

load_dotenv()


"""导入流程配置。

你可以把这个文件理解成“导入链的总参数表”。
所有导入节点共享的阈值、模型名、集合名、远程 API 地址、
基本都从这里统一读取。

建议你用下面这条思路来读它：
1. 先在 `.env` 里看变量名和中文解释。
2. 再回到这里看“这些变量在代码里会变成哪个字段”。
3. 最后去各个节点里看“这个字段到底在哪被使用”。

也就是说，理解顺序最好是：
`.env -> config.py -> 具体节点`
"""


def _get_bool_env(name: str, default: bool = False) -> bool:
    """把环境变量安全地解析成布尔值。

    例如：
    - `true / 1 / yes / on` -> True
    - 没配置 -> 用默认值
    """
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass
class ImportConfig:
    """导入链配置对象。

    这里的字段大体可以分成 4 类：
    1. 文本切分参数
    2. 模型和远程 API 参数
    3. 本地中间件参数
    4. MinerU PDF 解析参数

    当 `get_config()` 被调用时，程序会创建这个对象，
    然后各个导入节点都去读它的字段。
    """

    # ===== 文本切分与内容处理 =====
    # 这组参数主要影响：
    # `document_split_node.py` 和 `md_img_node.py`
    #
    # 它们决定：
    # - 一个 chunk 最长能有多长
    # - 过短的 section 是否需要合并
    # - 图片上下文最多截取多少字符
    max_content_length: int = 2000
    img_content_length: int = 200
    min_content_length: int = 500
    overlap_sentences: int = 1

    # 允许当作图片处理的后缀名集合。
    image_extensions: Set[str] = field(
        default_factory=lambda: {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    )

    # ===== 远程模型与文本模型相关配置 =====
    # 对应 `.env` 里的：
    # - OPENAI_API_BASE
    # - OPENAI_API_KEY
    # - VL_MODEL
    # - LLM_DEFAULT_MODEL
    #
    # 这些字段主要影响：
    # - 图片摘要
    # - 主体名称识别
    # - 其他需要文本模型的地方
    openai_api_base: str = field(default_factory=lambda: os.getenv('OPENAI_API_BASE', ''))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    vl_model: str = field(default_factory=lambda: os.getenv('VL_MODEL', ''))
    default_model: str = field(default_factory=lambda: os.getenv('MODEL', ''))
    llm_default_model: str = field(default_factory=lambda: os.getenv('LLM_DEFAULT_MODEL', os.getenv('MODEL', '')))

    # ===== 本地中间件参数 =====
    # 对应 `.env` 里的：
    # - MILVUS_URL
    # - CHUNKS_COLLECTION
    # - ITEM_NAME_COLLECTION
    # - MINIO_*
    #
    # 它们决定导入结果最终写到哪里。
    milvus_url: str = field(default_factory=lambda: os.getenv('MILVUS_URL', ''))
    # [修改] 和查询链默认 collection 对齐，并切到 EasyTour 独立命名，避免继续写进旧项目表。
    chunks_collection: str = field(default_factory=lambda: os.getenv('CHUNKS_COLLECTION', 'easytour_chunks_v1'))
    item_name_collection: str = field(default_factory=lambda: os.getenv('ITEM_NAME_COLLECTION', 'easytour_item_names_v1'))

    minio_endpoint: str = field(default_factory=lambda: os.getenv('MINIO_ENDPOINT', ''))
    minio_access_key: str = field(default_factory=lambda: os.getenv('MINIO_ACCESS_KEY', ''))
    minio_secret_key: str = field(default_factory=lambda: os.getenv('MINIO_SECRET_KEY', ''))
    minio_bucket: str = field(default_factory=lambda: os.getenv('MINIO_BUCKET_NAME', ''))
    minio_secure: bool = field(default_factory=lambda: _get_bool_env('MINIO_SECURE', False))

    # ===== 向量化参数 =====
    # 对应 `.env` 里的：
    # - EMBEDDING_DIM
    # - EMBEDDING_MODEL
    # - EMBEDDING_PROVIDER
    #
    # 这组参数主要影响：
    # - 当前导入主链的 chunk 向量化
    # - 主体名索引写入 item_name_collection
    embedding_dim: int = field(default_factory=lambda: int(os.getenv('EMBEDDING_DIM', '1024')))
    embedding_model: str = field(default_factory=lambda: os.getenv('EMBEDDING_MODEL', 'text-embedding-v4'))
    embedding_provider: str = field(default_factory=lambda: os.getenv('EMBEDDING_PROVIDER', 'dashscope'))
    embedding_batch_size: int = field(default_factory=lambda: int(os.getenv('EMBEDDING_BATCH_SIZE', '10')))
    rebuild_milvus_collection: bool = field(default_factory=lambda: _get_bool_env('REBUILD_MILVUS_COLLECTION', False))

    # ===== MinerU PDF 解析参数 =====
    # 对应 `.env` 里的：
    # - MINERU_API_KEY
    # - MINERU_API_BASE
    # - MINERU_MODEL_VERSION
    #
    # 这组参数主要影响：
    # - `pdf_to_md_node.py`
    # 也就是“PDF 先转 Markdown”这一步。
    mineru_api_key: str = field(default_factory=lambda: os.getenv('MINERU_API_KEY', ''))
    mineru_api_base: str = field(default_factory=lambda: os.getenv('MINERU_API_BASE', 'https://mineru.net/api/v4'))
    mineru_model_version: str = field(default_factory=lambda: os.getenv('MINERU_MODEL_VERSION', 'vlm'))
    mineru_timeout_seconds: int = field(default_factory=lambda: int(os.getenv('MINERU_TIMEOUT_SECONDS', '600')))
    mineru_poll_seconds: int = field(default_factory=lambda: int(os.getenv('MINERU_POLL_SECONDS', '5')))

    # ===== 其他工程参数 =====
    # 目前主要给图片摘要等场景做简单限流使用。
    # REQUESTS_PER_MINUTE：每分钟最大请求数，会和 VLM_CONCURRENCY 共同限制 VLM 调用速率。
    requests_per_minute: int = field(default_factory=lambda: int(os.getenv('REQUESTS_PER_MINUTE', '15')))

    # ===== 并发参数 =====
    # 控制导入链中 IO 密集型节点的并行度。
    # - VLM_CONCURRENCY：图片摘要节点同时在途的 VLM 请求数，仍受 requests_per_minute 共同约束。
    # - CHUNK_EXTRACT_CONCURRENCY：chunk 级抽取节点批与批之间的并行度（批内仍合并请求）。
    vlm_concurrency: int = field(default_factory=lambda: int(os.getenv('VLM_CONCURRENCY', '5')))
    chunk_extract_concurrency: int = field(default_factory=lambda: int(os.getenv('CHUNK_EXTRACT_CONCURRENCY', '3')))

    @classmethod
    def from_env(cls) -> 'ImportConfig':
        """从环境变量创建配置对象。

        你可以把这一步理解成：
        “把 `.env` 里的文本配置，装配成 Python 里可直接访问的对象”。
        """
        return cls()

    def get_minio_base_url(self) -> str:
        """拼出 MinIO 的访问根地址。"""
        base_protocol = 'https://' if self.minio_secure else 'http://'
        return base_protocol + self.minio_endpoint


_config: Optional[ImportConfig] = None


def get_config() -> ImportConfig:
    """返回全局共享的导入配置。

    这个函数会做一个简单缓存：
    第一次调用时创建 `ImportConfig`，后面都直接复用。
    这样每个节点就不需要反复重新读环境变量。
    """
    global _config
    if _config is None:
        _config = ImportConfig.from_env()
    return _config
