from __future__ import annotations

from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState


class RrfNode(BaseNode):
    name = 'rrf_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        inputs = [
            (state.get('embedding_chunks') or [], self.config.rrf_vector_weight),
            (state.get('hyde_embedding_chunks') or [], self.config.rrf_hyde_weight),
        ]
        score_map: dict[str, float] = {}
        doc_map: dict[str, dict[str, Any]] = {}
        source_map: dict[str, set[str]] = {}

        for docs, weight in inputs:
            for rank, doc in enumerate(docs, start=1):
                doc_key = self._build_doc_key(doc)
                score_map[doc_key] = score_map.get(doc_key, 0.0) + weight / (self.config.rrf_k + rank)
                if doc_key not in doc_map:
                    doc_map[doc_key] = dict(doc)
                source_map.setdefault(doc_key, set()).add(str(doc.get('retrieval_source', 'unknown')))

        ranked_docs: list[dict[str, Any]] = []
        for doc_key, score in sorted(score_map.items(), key=lambda item: item[1], reverse=True):
            doc = dict(doc_map[doc_key])
            doc['rrf_score'] = float(score)
            doc['score'] = float(score)
            doc['retrieval_sources'] = sorted(source_map.get(doc_key, set()))
            ranked_docs.append(doc)

        return {
            'rrf_chunks': ranked_docs[: self.config.rrf_max_results],
        }

    @staticmethod
    def _build_doc_key(doc: dict[str, Any]) -> str:
        chunk_id = doc.get('chunk_id')
        if chunk_id not in (None, ''):
            return f'chunk:{chunk_id}'
        content = str(doc.get('content') or doc.get('snippet') or '').strip()
        item_name = str(doc.get('item_name', '')).strip()
        url = str(doc.get('url', '')).strip()
        return f'text:{item_name}:{url}:{content}'
