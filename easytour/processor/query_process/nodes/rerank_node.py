from __future__ import annotations

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.nodes.common import boost_by_entity_hit
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import RERANK_TASK_INSTRUCTION
from easytour.utils.providers.provider_factory import get_rerank_provider


class RerankNode(BaseNode):
    name = 'rerank_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        docs = list(state.get('rrf_chunks') or [])

        docs = boost_by_entity_hit(
            docs,
            state.get('candidate_item_names') or [],
            state.get('confirmed_item_name'),
            fallback_mode=not self.config.milvus_supports_json_contains,
            factor=self.config.entity_boost_factor,
            fallback_factor=self.config.entity_boost_factor_fallback,
        )
        docs.extend(self._normalize_web_docs(state.get('web_search_docs') or []))
        if not docs:
            return {'reranked_docs': [], 'reranked_chunk_ids': []}

        docs = sorted(
            docs,
            key=lambda item: float(item.get('_pre_rerank_score') or item.get('score') or 0.0),
            reverse=True,
        )[: self.config.rerank_pre_top_k]

        if not self.config.enable_rerank or len(docs) == 1:
            reranked_docs = docs[: self.config.rerank_max_top_k]
            return {
                'reranked_docs': reranked_docs,
                'reranked_chunk_ids': [item.get('chunk_id') for item in reranked_docs if item.get('chunk_id') is not None],
            }

        rerank_provider = get_rerank_provider()
        rerank_documents = [self._build_document_text(doc) for doc in docs]
        rerank_results = rerank_provider.rerank(
            query=query,
            documents=rerank_documents,
            top_n=min(len(rerank_documents), self.config.rerank_pre_top_k),
            task_instruction=RERANK_TASK_INSTRUCTION,
        )

        reranked_docs = []
        for result in rerank_results:
            if result.index < 0 or result.index >= len(docs):
                continue
            doc = dict(docs[result.index])
            base_factor = float(doc.get('_pre_rerank_score') or 1.0)
            doc['rerank_score'] = float(result.score)
            doc['score'] = float(result.score) * base_factor
            reranked_docs.append(doc)

        reranked_docs.sort(key=lambda item: float(item.get('score') or 0.0), reverse=True)
        if self.config.enable_cliff_cutoff:
            reranked_docs = self._cliff_cutoff(reranked_docs)

        reranked_docs = reranked_docs[: self.config.rerank_max_top_k]
        return {
            'reranked_docs': reranked_docs,
            'reranked_chunk_ids': [item.get('chunk_id') for item in reranked_docs if item.get('chunk_id') is not None],
        }

    @staticmethod
    def _normalize_web_docs(web_docs: list[dict]) -> list[dict]:
        normalized = []
        for doc in web_docs:
            normalized.append(
                {
                    'title': str(doc.get('title') or '').strip(),
                    'content': str(doc.get('snippet') or doc.get('content') or '').strip(),
                    'snippet': str(doc.get('snippet') or '').strip(),
                    'url': str(doc.get('url') or '').strip(),
                    'retrieval_source': 'web_search',
                    '_pre_rerank_score': float(doc.get('_pre_rerank_score') or 1.0),
                }
            )
        return normalized

    @staticmethod
    def _build_document_text(doc: dict) -> str:
        title = str(doc.get('title') or doc.get('file_title') or '').strip()
        content = str(doc.get('content') or doc.get('snippet') or '').strip()
        if title:
            return f'title: {title}\ncontent: {content}'
        return content

    def _cliff_cutoff(self, ranked_docs: list[dict]) -> list[dict]:
        if not ranked_docs:
            return []
        upper_bound = min(self.config.rerank_max_top_k, len(ranked_docs))
        lower_bound = min(self.config.rerank_min_top_k, upper_bound)
        cutoff_pos = upper_bound
        for index in range(lower_bound - 1, upper_bound - 1):
            current_score = ranked_docs[index].get('score')
            next_score = ranked_docs[index + 1].get('score')
            if current_score is None or next_score is None:
                continue
            abs_gap = float(current_score) - float(next_score)
            rel_gap = abs_gap / (abs(float(current_score)) + 1e-6)
            if abs_gap >= self.config.rerank_gap_abs or rel_gap >= self.config.rerank_gap_ratio:
                cutoff_pos = index + 1
                break
        return ranked_docs[:cutoff_pos]
