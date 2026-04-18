from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.nodes.common import (
    build_milvus_expr,
    hybrid_search,
    normalize_chunk_hits,
)
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import USER_HYDE_PROMPT_TEMPLATE
from easytour.schema.chunk_schema import CHUNK_SEARCH_OUTPUT_FIELDS
from easytour.utils.providers.base import TEXT_TYPE_QUERY
from easytour.utils.providers.provider_factory import get_embedding_provider, get_llm_provider


class HyDeSearchNode(BaseNode):
    name = 'hyde_search_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        if not self.config.enable_hyde:
            return {
                'hyde_document': '',
                'hyde_embedding_chunks': [],
            }

        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        if not query:
            return {
                'hyde_document': '',
                'hyde_embedding_chunks': [],
            }

        hyde_document = self._generate_hyde_document(query, state.get('item_names') or [])
        if not hyde_document:
            return {
                'hyde_document': '',
                'hyde_embedding_chunks': [],
            }

        record = get_embedding_provider().embed_texts(
            [f'{query}\n{hyde_document}'],
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
            limit=self.config.hyde_search_limit,
            output_fields=CHUNK_SEARCH_OUTPUT_FIELDS,
            expr=expr,
        )
        return {
            'hyde_document': hyde_document,
            'hyde_embedding_chunks': normalize_chunk_hits(hits, retrieval_source='hyde_search'),
        }

    def _generate_hyde_document(self, query: str, item_names: list[str]) -> str:
        try:
            llm_client = get_llm_provider().get_client(response_format=False)
        except Exception:
            return ''

        user_prompt = USER_HYDE_PROMPT_TEMPLATE.format(
            # [修改] 使用干净的 fallback 文案，避免历史乱码直接进入 HyDE 提示词。
            item_hint=', '.join(item_names) if item_names else '未识别主体',
            rewritten_query=query,
        )
        try:
            response = llm_client.invoke(
                [
                    SystemMessage(content='Write a concise travel-domain pseudo document.'),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception:
            return ''
        return str(response.content or '').strip()
