from __future__ import annotations

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.exceptions import StateFieldError
from easytour.processor.query_process.nodes.common import (
    build_milvus_expr,
    hybrid_search,
    normalize_chunk_hits,
)
from easytour.processor.query_process.state import QueryGraphState
from easytour.schema.chunk_schema import CHUNK_SEARCH_OUTPUT_FIELDS
from easytour.utils.providers.base import TEXT_TYPE_QUERY
from easytour.utils.providers.provider_factory import get_embedding_provider


class VectorSearchNode(BaseNode):
    name = 'vector_search_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        if not query:
            raise StateFieldError(node_name=self.name, field_name='rewritten_query', expected_type=str)

        record = get_embedding_provider().embed_texts(
            [query],
            text_type=TEXT_TYPE_QUERY,
            dimension=self.config.embedding_dim,
        )[0]
        expr = build_milvus_expr(
            str(state.get('retrieval_type') or ''),
            state.get('region_filter') or {},
            str(state.get('confirmed_item_name') or ''),
            supports_json_contains=self.config.milvus_supports_json_contains,
        )
        hits = hybrid_search(
            collection_name=self.config.chunks_collection,
            dense_vector=record.dense_vector,
            sparse_vector=record.sparse_vector,
            limit=self.config.embedding_search_limit,
            output_fields=CHUNK_SEARCH_OUTPUT_FIELDS,
            expr=expr,
        )
        embedding_chunks = normalize_chunk_hits(hits, retrieval_source='vector_search')
        return {
            'embedding_chunks': embedding_chunks,
            'retrieval_filters': expr,
            'topk_chunk_ids': [item.get('chunk_id') for item in embedding_chunks],
            'topk_scores': [float(item.get('score') or 0.0) for item in embedding_chunks],
        }
