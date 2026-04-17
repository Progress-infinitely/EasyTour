from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.exceptions import StateFieldError
from easytour.processor.query_process.nodes.common import hybrid_search, normalize_item_name_hits
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import (
    ITEM_NAME_EXTRACT_SYSTEM_PROMPT,
    ITEM_NAME_EXTRACT_TEMPLATE,
)
from easytour.utils.providers.base import TEXT_TYPE_QUERY
from easytour.utils.providers.provider_factory import get_embedding_provider, get_llm_provider


class ItemNameConfirmNode(BaseNode):
    name = 'item_name_confirm_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        base_query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        if not base_query:
            raise StateFieldError(node_name=self.name, field_name='original_query', expected_type=str)

        seed_names = [
            str(item.get('canonical_name') or '').strip()
            for item in state.get('resolved_aliases') or []
            if str(item.get('canonical_name') or '').strip()
        ]
        # [修改] 先把别名解析产出的规范名作为种子带入，减少“这家/它”这类指代导致的漏识别。
        extracted_item_names, rewritten_query = self._extract_item_names(
            base_query,
            state.get('history') or [],
            seed_names,
        )
        confirmed_item_name, candidate_item_names, candidates = self._align_item_names(extracted_item_names)

        item_names: list[str] = []
        if confirmed_item_name:
            item_names.append(confirmed_item_name)
        for item_name in candidate_item_names:
            if item_name not in item_names:
                item_names.append(item_name)

        return {
            'rewritten_query': rewritten_query or base_query,
            'item_names': item_names,
            'confirmed_item_name': confirmed_item_name,
            'candidate_item_names': candidate_item_names,
            'item_name_candidates': candidates,
        }

    def _extract_item_names(
        self,
        query: str,
        history: list[dict[str, Any]],
        seed_names: list[str],
    ) -> tuple[list[str], str]:
        try:
            llm_client = get_llm_provider().get_client(response_format=True)
        except Exception:
            return list(seed_names), query

        history_lines = []
        for message in history[-6:]:
            role = str(message.get('role', '')).strip() or 'unknown'
            text = str(message.get('text', '')).strip()
            if text:
                history_lines.append(f'{role}: {text}')

        user_prompt = ITEM_NAME_EXTRACT_TEMPLATE.format(
            history_text='\n'.join(history_lines) or '无历史消息',
            query=query,
        )
        if seed_names:
            user_prompt += f'\n优先关注这些主体：{", ".join(seed_names)}'

        try:
            response = llm_client.invoke(
                [
                    SystemMessage(content=ITEM_NAME_EXTRACT_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )
            payload = self._parse_json_payload(response.content)
        except Exception:
            payload = {}

        raw_item_names = list(payload.get('item_names') or [])
        item_names: list[str] = []
        for item_name in [*seed_names, *raw_item_names]:
            normalized_name = str(item_name).strip()
            if normalized_name and normalized_name not in item_names:
                item_names.append(normalized_name)

        rewritten_query = str(payload.get('rewritten_query') or query).strip() or query
        return item_names, rewritten_query

    def _align_item_names(self, extracted_item_names: list[str]) -> tuple[str, list[str], list[dict[str, Any]]]:
        if not extracted_item_names:
            return '', [], []

        embedding_provider = get_embedding_provider()
        records = embedding_provider.embed_texts(
            extracted_item_names,
            text_type=TEXT_TYPE_QUERY,
            dimension=self.config.embedding_dim,
        )

        confirmed_item_name = ''
        candidate_item_names: list[str] = []
        candidates: list[dict[str, Any]] = []
        for extracted_name, record in zip(extracted_item_names, records):
            hits = hybrid_search(
                collection_name=self.config.item_name_collection,
                dense_vector=record.dense_vector,
                sparse_vector=record.sparse_vector,
                limit=self.config.item_name_top_k,
                output_fields=['item_name', 'file_title'],
                dense_weight=self.config.item_name_dense_weight,
                sparse_weight=self.config.item_name_sparse_weight,
            )
            normalized_hits = normalize_item_name_hits(hits)
            if not normalized_hits:
                continue

            candidates.append(
                {
                    'extracted_name': extracted_name,
                    'matches': normalized_hits[: self.config.item_name_max_options],
                }
            )
            best_item_name = normalized_hits[0]['item_name']
            best_score = float(normalized_hits[0]['score'])
            second_score = float(normalized_hits[1]['score']) if len(normalized_hits) > 1 else None
            score_gap = best_score - second_score if second_score is not None else best_score

            if not confirmed_item_name and self._is_confirmed(best_score, score_gap):
                confirmed_item_name = best_item_name
                continue

            if best_score >= self.config.item_name_mid_confidence and best_item_name not in candidate_item_names:
                candidate_item_names.append(best_item_name)

        if confirmed_item_name:
            candidate_item_names = [item_name for item_name in candidate_item_names if item_name != confirmed_item_name]
        return confirmed_item_name, candidate_item_names, candidates

    def _is_confirmed(self, best_score: float, score_gap: float) -> bool:
        if best_score >= self.config.item_name_high_confidence:
            return True
        return best_score >= self.config.item_name_mid_confidence and score_gap >= self.config.item_name_score_gap

    @staticmethod
    def _parse_json_payload(content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            content = ''.join(str(part) for part in content)
        text = str(content or '').strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
            raise
