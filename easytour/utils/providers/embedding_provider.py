from __future__ import annotations

from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

from easytour.core.config import get_shared_config

from easytour.utils.http_client import JsonHttpClient
from easytour.utils.providers.base import (
    EmbeddingRecord,
    ProviderConfigError,
    ProviderResponseError,
    VALID_TEXT_TYPES,
)

load_dotenv()


class DashScopeEmbeddingProvider:
    _MAX_BATCH_SIZE = 10

    def __init__(self, http_client: JsonHttpClient | None = None):
        config = get_shared_config()
        self._http_client = http_client or JsonHttpClient()
        self._api_key = config.provider_api_key
        self._base_url = self._resolve_base_url()
        self._model_name = config.embedding_model or 'text-embedding-v4'

        if not self._api_key:
            raise ProviderConfigError('OPENAI_API_KEY or DASHSCOPE_API_KEY is required')

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        text_type: str,
        dimension: int = 1024,
    ) -> list[EmbeddingRecord]:
        if text_type not in VALID_TEXT_TYPES:
            raise ValueError(f'text_type must be one of {sorted(VALID_TEXT_TYPES)}')
        if dimension != 1024:
            raise ValueError('Final implementation requires EMBEDDING_DIM=1024')
        if not texts:
            return []

        normalized_texts = [self._normalize_text(text) for text in texts]
        records: list[EmbeddingRecord] = []

        for start in range(0, len(normalized_texts), self._MAX_BATCH_SIZE):
            batch = normalized_texts[start : start + self._MAX_BATCH_SIZE]
            payload = {
                'model': self._model_name,
                'input': {'texts': batch},
                'parameters': {
                    'text_type': text_type,
                    'dimension': dimension,
                    'output_type': 'dense&sparse',
                },
            }
            response = self._http_client.post_json(
                f'{self._base_url}/services/embeddings/text-embedding/text-embedding',
                payload,
                headers={'Authorization': f'Bearer {self._api_key}'},
            )
            records.extend(self._parse_response(response, dimension))

        if len(records) != len(normalized_texts):
            raise ProviderResponseError(
                f'Embedding record count mismatch: expected {len(normalized_texts)}, got {len(records)}'
            )
        return records

    def _parse_response(self, payload: Mapping[str, Any], dimension: int) -> list[EmbeddingRecord]:
        if payload.get('code'):
            raise ProviderResponseError(
                f"Embedding API returned error: {payload.get('code')} {payload.get('message', '')}".strip()
            )

        raw_embeddings = payload.get('output', {}).get('embeddings')
        if not isinstance(raw_embeddings, list):
            raise ProviderResponseError('Embedding API response missing output.embeddings')

        # [修改] 按 text_index 排序，保证 provider 返回顺序和输入文本顺序一致。
        sorted_embeddings = sorted(raw_embeddings, key=lambda item: item.get('text_index', 0))
        records: list[EmbeddingRecord] = []
        for item in sorted_embeddings:
            dense_vector = item.get('embedding')
            if not isinstance(dense_vector, list) or len(dense_vector) != dimension:
                raise ProviderResponseError('Embedding API returned invalid dense vector')

            records.append(
                EmbeddingRecord(
                    dense_vector=[float(value) for value in dense_vector],
                    sparse_vector=self._parse_sparse_vector(item.get('sparse_embedding')),
                    provider_model=self._model_name,
                    dimension=dimension,
                )
            )
        return records

    @staticmethod
    def _parse_sparse_vector(raw_sparse_vector: Any) -> dict[int, float]:
        if raw_sparse_vector is None:
            return {}
        if isinstance(raw_sparse_vector, dict):
            return {int(key): float(value) for key, value in raw_sparse_vector.items()}
        if not isinstance(raw_sparse_vector, list):
            raise ProviderResponseError('Embedding API returned invalid sparse vector')

        sparse_vector: dict[int, float] = {}
        for item in raw_sparse_vector:
            if not isinstance(item, dict):
                continue
            index = item.get('index')
            value = item.get('value')
            if index is None or value is None:
                continue
            sparse_vector[int(index)] = float(value)
        return sparse_vector

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        normalized = '' if text is None else str(text)
        if not normalized.strip():
            return ' '
        return normalized

    @staticmethod
    def _resolve_base_url() -> str:
        config = get_shared_config()
        explicit_base_url = (
            config.dashscope_embedding_api_base
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
