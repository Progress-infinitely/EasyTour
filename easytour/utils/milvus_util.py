from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pymilvus import AnnSearchRequest, MilvusClient, WeightedRanker

load_dotenv()

logger = logging.getLogger(__name__)

milvus_client: Optional[MilvusClient] = None


"""Milvus 轻量工具。

这一层和 `StorageClients` 的区别，很多初学者第一次看会混。
你可以先这样分：

- `StorageClients`：负责“创建和复用 Milvus 客户端”
- `milvus_util.py`：负责“围绕 Milvus 常用操作写便捷函数”

也就是说：
- client 层更像“发工具的人”
- util 层更像“拿着工具帮你快速做常见动作的人”

这个文件主要解决三类小问题：
1. 懒加载一个可复用的 Milvus 客户端
2. 帮你快速拼 hybrid search 请求对象
3. 批量读回已有 chunk 数据
"""


def get_milvus_client() -> Optional[MilvusClient]:
    """获取全局 Milvus 客户端。

    这里采用懒加载：
    - 第一次调用时才真正创建客户端
    - 后面直接复用

    如果 `MILVUS_URL` 没配置好，或者初始化失败，会返回 `None`。
    这是一个偏学习项目的设计：
    让上层有机会自己决定是报错还是降级，而不是这里直接强行终止整个程序。
    """
    global milvus_client

    if milvus_client is not None:
        return milvus_client

    try:
        milvus_uri = os.getenv('MILVUS_URL', '').strip()
        if not milvus_uri:
            logger.warning('MILVUS_URL is empty, skip Milvus client initialization')
            return None
        timeout_seconds = float(os.getenv('MILVUS_TIMEOUT_SECONDS', '8'))
        milvus_client = MilvusClient(uri=milvus_uri, timeout=timeout_seconds)
        return milvus_client
    except Exception as exc:
        logger.error('Failed to initialize Milvus client: %s', exc)
        return None


def create_hybrid_search_requests(
    dense_vector,
    sparse_vector,
    dense_params=None,
    sparse_params=None,
    expr=None,
    limit=5,
):
    """构造 Milvus hybrid search 所需的两路检索请求。

    为什么是“两路”？
    因为当前项目的混合检索会同时使用：
    - dense_vector：语义相似信号
    - sparse_vector：关键词信号

    你可以把这个函数理解成：
    “把一场混合检索要用的两张答卷先准备好”。
    返回值是一个请求列表，之后可以直接交给 `hybrid_search`。
    """
    dense_params = dense_params or {'metric_type': 'COSINE'}
    sparse_params = sparse_params or {'metric_type': 'IP'}

    dense_req = AnnSearchRequest(
        data=[dense_vector],
        anns_field='dense_vector',
        param=dense_params,
        expr=expr,
        limit=limit,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vector],
        anns_field='sparse_vector',
        param=sparse_params,
        expr=expr,
        limit=limit,
    )
    return [dense_req, sparse_req]


def execute_hybrid_search_query(
    milvus_client: MilvusClient,
    collection_name,
    search_requests,
    ranker_weights=(0.5, 0.5),
    norm_score=False,
    limit=5,
    output_fields=None,
    search_params=None,
):
    """执行一次 Milvus 混合检索查询。

    这一步本质上是在做：
    - 让 Milvus 同时看 dense 路和 sparse 路的结果
    - 再按权重把两路结果融合成一份排序
    """
    if milvus_client is None:
        return None

    try:
        # WeightedRanker 会把 dense 路和 sparse 路的分数按权重合并。
        rerank = WeightedRanker(ranker_weights[0], ranker_weights[1], norm_score=norm_score)
        return milvus_client.hybrid_search(
            collection_name=collection_name,
            reqs=search_requests,
            ranker=rerank,
            limit=limit,
            output_fields=output_fields or ['item_name'],
            search_params=search_params,
        )
    except Exception as exc:
        logger.error('Milvus hybrid search failed: %s', exc)
        return None


def fetch_chunks_by_chunk_ids(
    collection_name: str,
    chunk_ids,
    *,
    output_fields=None,
    batch_size: int = 100,
):
    """根据 chunk_id 批量取回原始 chunk 数据。

    这个函数适合那种场景：
    你手里已经有一组 chunk_id，
    现在想把它们对应的完整内容再读回来。
    """
    client = get_milvus_client()
    if client is None or not collection_name or not chunk_ids:
        return []

    output_fields = output_fields or ['chunk_id', 'content', 'title', 'file_title', 'item_name']
    results = []
    for index in range(0, len(chunk_ids), batch_size):
        batch = chunk_ids[index : index + batch_size]
        try:
            fetched = client.get(collection_name=collection_name, ids=batch, output_fields=output_fields)
            if fetched:
                results.extend(fetched)
        except Exception as exc:
            logger.error('Milvus get failed: %s', exc)
    return results


__all__ = [
    'create_hybrid_search_requests',
    'execute_hybrid_search_query',
    'fetch_chunks_by_chunk_ids',
    'get_milvus_client',
    'milvus_client',
]
