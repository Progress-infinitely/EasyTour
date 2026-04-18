from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

from easytour.core.config import get_shared_config

from easytour.utils.http_client import JsonHttpClient
from easytour.utils.providers.base import (
    ProviderConfigError,
    ProviderResponseError,
    RerankResult,
)

load_dotenv()


class DashScopeRerankProvider:
    def __init__(self, http_client: JsonHttpClient | None = None):
        config = get_shared_config()
        self._http_client = http_client or JsonHttpClient()
        self._api_key = config.provider_api_key
        self._base_url = self._resolve_base_url()
        self._model_name = config.rerank_model or 'qwen3-rerank'
        if not self._api_key:
            raise ProviderConfigError('OPENAI_API_KEY or DASHSCOPE_API_KEY is required')

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
        task_instruction: str,
    ) -> list[RerankResult]:
        if not documents:
            return []

        payload = self._build_payload(
            query=query,
            documents=documents,
            top_n=top_n,
            task_instruction=task_instruction,
        )
        response = self._http_client.post_json(
            self._build_request_url(),
            payload,
            headers={'Authorization': f'Bearer {self._api_key}'},
        )
        return self._parse_response(response, documents)

    def estimate_tokens(self, query: str, documents: Sequence[str]) -> int:
        query_tokens = self._estimate_text_tokens(query)
        document_tokens = [self._estimate_text_tokens(document) for document in documents]
        request_tokens = query_tokens * len(document_tokens) + sum(document_tokens) + 200
        return int(request_tokens * 1.2)

    def _parse_response(
        self,
        payload: Mapping[str, Any],
        documents: Sequence[str],
    ) -> list[RerankResult]:
        if payload.get('code'):
            raise ProviderResponseError(
                f"Rerank API returned error: {payload.get('code')} {payload.get('message', '')}".strip()
            )

        raw_results = payload.get('output', {}).get('results')
        if not isinstance(raw_results, list):
            raw_results = payload.get('results')
        if not isinstance(raw_results, list):
            raise ProviderResponseError('Rerank API response missing output.results')

        results: list[RerankResult] = []
        for item in raw_results:
            index = item.get('index')
            score = item.get('relevance_score')
            if score is None:
                score = item.get('score')
            if index is None or score is None:
                continue
            normalized_index = int(index)
            document = documents[normalized_index] if 0 <= normalized_index < len(documents) else ''
            results.append(
                RerankResult(
                    index=normalized_index,
                    document=document,
                    score=float(score),
                )
            )
        return results

    def _build_payload(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
        task_instruction: str,
    ) -> dict[str, Any]:
        normalized_top_n = max(1, top_n)
        if self._model_name.startswith('qwen3-rerank'):
            return {
                'model': self._model_name,
                'query': query,
                'documents': list(documents),
                'top_n': normalized_top_n,
                'instruct': task_instruction,
            }
        return {
            'model': self._model_name,
            'input': {
                'query': query,
                'documents': list(documents),
            },
            'parameters': {
                'top_n': normalized_top_n,
                'return_documents': False,
            },
        }

    def _build_request_url(self) -> str:
        if self._model_name.startswith('qwen3-rerank'):
            return f'{self._resolve_compatible_rerank_base_url()}/reranks'
        return f'{self._base_url}/services/rerank/text-rerank/text-rerank'

    @staticmethod
    def _estimate_text_tokens(text: str) -> float:
        if not text:
            return 0.0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[A-Za-z0-9_]+', text))
        other_chars = max(len(text) - chinese_chars, 0)
        return chinese_chars * 1.5 + english_words * 1.3 + other_chars * 0.2

    @staticmethod
    def _resolve_base_url() -> str:
        config = get_shared_config()
        explicit_base_url = (
            config.dashscope_rerank_api_base
            or config.dashscope_http_api_base
            or config.dashscope_api_base
        )
        if explicit_base_url:
            return explicit_base_url.rstrip('/')

        compatible_base_url = config.openai_api_base.rstrip('/')
        if compatible_base_url.endswith('/compatible-mode/v1'):
            return compatible_base_url[: -len('/compatible-mode/v1')] + '/api/v1'
        if compatible_base_url:
            return compatible_base_url
        return 'https://dashscope.aliyuncs.com/api/v1'

    @staticmethod
    def _resolve_compatible_rerank_base_url() -> str:
        config = get_shared_config()
        explicit_base_url = (
            config.dashscope_rerank_compatible_api_base
            or config.dashscope_compatible_api_base
        )
        if explicit_base_url:
            return explicit_base_url.rstrip('/')

        compatible_base_url = config.openai_api_base.rstrip('/')
        if compatible_base_url.endswith('/compatible-mode/v1'):
            return compatible_base_url[: -len('/compatible-mode/v1')] + '/compatible-api/v1'
        if compatible_base_url.endswith('/compatible-api/v1'):
            return compatible_base_url
        return 'https://dashscope.aliyuncs.com/compatible-api/v1'
