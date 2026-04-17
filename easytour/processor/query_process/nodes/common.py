from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from pymilvus import AnnSearchRequest, WeightedRanker

from easytour.utils.client.storage_clients import StorageClients


def build_item_name_expr(item_names: Sequence[str]) -> str:
    normalized_names = [str(name).strip() for name in item_names if str(name).strip()]
    if not normalized_names:
        return ''
    quoted = ', '.join(json_quote(name) for name in normalized_names)
    return f'item_name in [{quoted}]'


def build_milvus_expr(
    retrieval_type: str,
    region: Mapping[str, Any] | None,
    confirmed_item_name: str,
    *,
    supports_json_contains: bool,
) -> str:
    parts: list[str] = []
    normalized_type = str(retrieval_type or '').strip()
    if normalized_type and normalized_type != 'generic':
        parts.append(f'content_type == {json_quote(normalized_type)}')

    normalized_item_name = str(confirmed_item_name or '').strip()
    if normalized_item_name:
        if supports_json_contains:
            parts.append(
                f'(primary_item_name == {json_quote(normalized_item_name)} '
                f'or json_contains(entity_names, {json_quote(normalized_item_name)}))'
            )
        else:
            parts.append(f'primary_item_name == {json_quote(normalized_item_name)}')

    region = dict(region or {})
    city = str(region.get('city') or '').strip()
    region_path = str(region.get('region_path') or '').strip()
    province = str(region.get('province') or '').strip()
    if city:
        parts.append(f'city == {json_quote(city)}')
    elif region_path:
        parts.append(f'region_path like {json_quote(region_path + "%")}')
    elif province:
        parts.append(f'province == {json_quote(province)}')

    return ' and '.join(parts)


def json_quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def hybrid_search(
    *,
    collection_name: str,
    dense_vector: list[float],
    sparse_vector: dict[int, float],
    limit: int,
    output_fields: Sequence[str],
    expr: str = '',
    dense_weight: float = 0.5,
    sparse_weight: float = 0.5,
) -> list[dict[str, Any]]:
    client = StorageClients.get_milvus_client()
    requests = [
        AnnSearchRequest(
            data=[dense_vector],
            anns_field='dense_vector',
            param={'metric_type': 'COSINE', 'params': {}},
            limit=limit,
            expr=expr or None,
        ),
        AnnSearchRequest(
            data=[sparse_vector],
            anns_field='sparse_vector',
            param={'metric_type': 'IP', 'params': {}},
            limit=limit,
            expr=expr or None,
        ),
    ]
    response = client.hybrid_search(
        collection_name=collection_name,
        reqs=requests,
        ranker=WeightedRanker(dense_weight, sparse_weight),
        limit=limit,
        output_fields=list(output_fields),
    )
    if not response:
        return []
    return response[0]


def normalize_chunk_hits(hits: Sequence[dict[str, Any]], *, retrieval_source: str) -> list[dict[str, Any]]:
    normalized_docs: list[dict[str, Any]] = []
    for hit in hits:
        entity = hit.get('entity') or {}
        content = str(entity.get('content', '')).strip()
        if not content:
            continue
        score = hit.get('distance')
        if score is None:
            score = hit.get('score')
        primary_item_name = str(entity.get('primary_item_name') or '').strip()
        item_name = str(entity.get('item_name') or primary_item_name).strip()
        normalized_docs.append(
            {
                'chunk_id': entity.get('chunk_id', hit.get('id')),
                'content': content,
                'title': entity.get('title', ''),
                'parent_title': entity.get('parent_title', ''),
                'file_title': entity.get('file_title', ''),
                'item_name': item_name,
                'primary_item_name': primary_item_name,
                'entity_names': _parse_json_list(entity.get('entity_names')),
                'score': float(score or 0.0),
                'retrieval_source': retrieval_source,
                'source': 'milvus',
                'document_id': str(entity.get('document_id') or ''),
                'source_label_display': str(entity.get('source_label_display') or entity.get('file_title') or ''),
                'city': str(entity.get('city') or ''),
            }
        )
    return normalized_docs


def normalize_item_name_hits(hits: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for hit in hits:
        entity = hit.get('entity') or {}
        item_name = str(entity.get('item_name', '')).strip()
        if not item_name:
            continue
        score = hit.get('distance')
        if score is None:
            score = hit.get('score')
        normalized.append(
            {
                'item_name': item_name,
                'file_title': entity.get('file_title', ''),
                'score': float(score or 0.0),
            }
        )
    return normalized


def boost_by_entity_hit(
    chunks: list[dict[str, Any]],
    candidates: list[str],
    confirmed: str | None,
    *,
    fallback_mode: bool,
    factor: float = 1.2,
    fallback_factor: float = 1.5,
) -> list[dict[str, Any]]:
    hit_targets = {str(item).strip() for item in candidates if str(item).strip()}
    normalized_confirmed = str(confirmed or '').strip()
    if normalized_confirmed and fallback_mode:
        hit_targets.add(normalized_confirmed)
    if not hit_targets:
        return list(chunks)

    boosted: list[dict[str, Any]] = []
    for chunk in chunks:
        current = dict(chunk)
        current['_pre_rerank_score'] = float(current.get('_pre_rerank_score') or current.get('score') or 1.0)
        entities = {str(item).strip() for item in current.get('entity_names') or [] if str(item).strip()}
        primary = str(current.get('primary_item_name') or '').strip()
        if primary:
            entities.add(primary)
        matched = entities & hit_targets
        if matched:
            use_factor = fallback_factor if (normalized_confirmed and normalized_confirmed in matched and fallback_mode) else factor
            current['_pre_rerank_score'] *= use_factor
        boosted.append(current)
    return sorted(boosted, key=lambda item: float(item.get('_pre_rerank_score') or 0.0), reverse=True)


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [stripped]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    return []
