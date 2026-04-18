from __future__ import annotations

from dotenv import load_dotenv

from easytour.core.config import get_shared_config

from easytour.utils.providers.embedding_provider import DashScopeEmbeddingProvider
from easytour.utils.providers.llm_provider import DashScopeLLMProvider
from easytour.utils.providers.rerank_provider import DashScopeRerankProvider

load_dotenv()


_embedding_provider: DashScopeEmbeddingProvider | None = None
_llm_provider: DashScopeLLMProvider | None = None
_rerank_provider: DashScopeRerankProvider | None = None


def get_embedding_provider() -> DashScopeEmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        provider_name = get_shared_config().embedding_provider
        if provider_name not in {'dashscope', 'api'}:
            raise ValueError(f'Unsupported embedding provider: {provider_name}')
        _embedding_provider = DashScopeEmbeddingProvider()
    return _embedding_provider


def get_llm_provider() -> DashScopeLLMProvider:
    global _llm_provider
    if _llm_provider is None:
        provider_name = get_shared_config().llm_provider
        if provider_name not in {'dashscope', 'api'}:
            raise ValueError(f'Unsupported llm provider: {provider_name}')
        _llm_provider = DashScopeLLMProvider()
    return _llm_provider


def get_rerank_provider() -> DashScopeRerankProvider:
    global _rerank_provider
    if _rerank_provider is None:
        # [修改] 保留统一单例入口，避免查询链每个节点都重复创建 provider 实例。
        provider_name = get_shared_config().rerank_provider
        if provider_name not in {'dashscope', 'api'}:
            raise ValueError(f'Unsupported rerank provider: {provider_name}')
        _rerank_provider = DashScopeRerankProvider()
    return _rerank_provider
