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
class QueryConfig:
    max_context_chars: int = field(default_factory=lambda: int(os.getenv('MAX_CONTEXT_CHARS', '12000')))
    embedding_dim: int = field(default_factory=lambda: int(os.getenv('EMBEDDING_DIM', '1024')))

    embedding_search_limit: int = field(default_factory=lambda: int(os.getenv('EMBEDDING_SEARCH_LIMIT', '10')))
    hyde_search_limit: int = field(default_factory=lambda: int(os.getenv('HYDE_SEARCH_LIMIT', '5')))

    enable_hyde: bool = field(default_factory=lambda: _get_bool_env('ENABLE_HYDE', True))
    enable_web_search: bool = field(default_factory=lambda: _get_bool_env('ENABLE_WEB_SEARCH', True))
    enable_rerank: bool = field(default_factory=lambda: _get_bool_env('ENABLE_RERANK', True))
    enable_cliff_cutoff: bool = field(default_factory=lambda: _get_bool_env('ENABLE_CLIFF_CUTOFF', False))
    milvus_supports_json_contains: bool = field(
        default_factory=lambda: _get_bool_env('MILVUS_SUPPORTS_JSON_CONTAINS', False)
    )

    rerank_pre_top_k: int = field(default_factory=lambda: int(os.getenv('RERANK_PRE_TOP_K', '20')))
    rerank_max_top_k: int = field(default_factory=lambda: int(os.getenv('RERANK_MAX_TOP_K', '10')))
    rerank_min_top_k: int = field(default_factory=lambda: int(os.getenv('RERANK_MIN_TOP_K', '3')))
    rerank_gap_ratio: float = field(default_factory=lambda: float(os.getenv('RERANK_GAP_RATIO', '0.25')))
    rerank_gap_abs: float = field(default_factory=lambda: float(os.getenv('RERANK_GAP_ABS', '0.5')))
    entity_boost_factor: float = field(default_factory=lambda: float(os.getenv('ENTITY_BOOST_FACTOR', '1.2')))
    entity_boost_factor_fallback: float = field(
        default_factory=lambda: float(os.getenv('ENTITY_BOOST_FACTOR_FALLBACK', '1.5'))
    )

    rrf_k: int = field(default_factory=lambda: int(os.getenv('RRF_K', '60')))
    rrf_vector_weight: float = field(default_factory=lambda: float(os.getenv('RRF_VECTOR_WEIGHT', '1.0')))
    rrf_hyde_weight: float = field(default_factory=lambda: float(os.getenv('RRF_HYDE_WEIGHT', '0.7')))
    rrf_max_results: int = field(default_factory=lambda: int(os.getenv('RRF_MAX_RESULTS', '20')))

    item_name_top_k: int = field(
        default_factory=lambda: int(os.getenv('ITEM_NAME_TOP_K', os.getenv('ITEM_NAME_MAX_OPTIONS', '5')))
    )
    item_name_max_options: int = field(
        default_factory=lambda: int(os.getenv('ITEM_NAME_MAX_OPTIONS', os.getenv('ITEM_NAME_TOP_K', '5')))
    )
    item_name_high_confidence: float = field(
        default_factory=lambda: float(os.getenv('ITEM_NAME_HIGH_CONFIDENCE', '0.7'))
    )
    item_name_mid_confidence: float = field(
        default_factory=lambda: float(os.getenv('ITEM_NAME_MID_CONFIDENCE', '0.6'))
    )
    item_name_score_gap: float = field(default_factory=lambda: float(os.getenv('ITEM_NAME_SCORE_GAP', '0.15')))
    item_name_dense_weight: float = field(default_factory=lambda: float(os.getenv('ITEM_NAME_DENSE_WEIGHT', '0.5')))
    item_name_sparse_weight: float = field(default_factory=lambda: float(os.getenv('ITEM_NAME_SPARSE_WEIGHT', '0.5')))

    openai_api_base: str = field(default_factory=lambda: os.getenv('OPENAI_API_BASE', ''))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    default_model: str = field(default_factory=lambda: os.getenv('LLM_DEFAULT_MODEL', os.getenv('MODEL', '')))
    item_model: str = field(default_factory=lambda: os.getenv('ITEM_MODEL', ''))
    embedding_model: str = field(default_factory=lambda: os.getenv('EMBEDDING_MODEL', 'text-embedding-v4'))
    rerank_model: str = field(default_factory=lambda: os.getenv('RERANK_MODEL', 'qwen3-rerank'))
    embedding_provider: str = field(default_factory=lambda: os.getenv('EMBEDDING_PROVIDER', 'dashscope'))
    rerank_provider: str = field(default_factory=lambda: os.getenv('RERANK_PROVIDER', 'dashscope'))

    milvus_url: str = field(default_factory=lambda: os.getenv('MILVUS_URL', ''))
    chunks_collection: str = field(default_factory=lambda: os.getenv('CHUNKS_COLLECTION', 'kb_chunks_api_v1'))
    item_name_collection: str = field(default_factory=lambda: os.getenv('ITEM_NAME_COLLECTION', 'kb_item_names_api_v1'))
    entity_name_collection: str = field(default_factory=lambda: os.getenv('ENTITY_NAME_COLLECTION', 'kb_entity_names_api_v1'))

    mcp_dashscope_base_url: str = field(default_factory=lambda: os.getenv('MCP_DASHSCOPE_BASE_URL', ''))
    query_time_budget_ms: int = field(default_factory=lambda: int(os.getenv('QUERY_TIME_BUDGET_MS', '10000')))

    @classmethod
    def from_env(cls) -> 'QueryConfig':
        return cls()


_config: QueryConfig | None = None


def get_config() -> QueryConfig:
    global _config
    if _config is None:
        _config = QueryConfig.from_env()
    return _config
