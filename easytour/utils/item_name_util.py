from __future__ import annotations

from typing import Any, Mapping, Sequence

_ENTITY_FIELD_NAMES = ('doc_main_entities', 'main_entities')


def collect_entity_item_names(
    payload: Mapping[str, Any],
    *,
    field_names: Sequence[str] = _ENTITY_FIELD_NAMES,
) -> list[str]:
    names: list[str] = []
    for field_name in field_names:
        for entity in payload.get(field_name) or []:
            item_name = str((entity or {}).get('item_name') or '').strip()
            if item_name and item_name not in names:
                names.append(item_name)
    return names


def resolve_document_item_name(payload: Mapping[str, Any]) -> str:
    item_name = str(payload.get('item_name') or '').strip()
    if item_name:
        return item_name

    entity_names = collect_entity_item_names(payload)
    if entity_names:
        return entity_names[0]

    return str(payload.get('document_title') or payload.get('file_title') or '').strip()


def resolve_chunk_item_name(
    payload: Mapping[str, Any],
    *,
    default_document_item_name: str = '',
) -> str:
    item_name = str(payload.get('item_name') or '').strip()
    if item_name:
        return item_name

    return str(default_document_item_name or resolve_document_item_name(payload)).strip()


def resolve_chunk_primary_item_name(
    payload: Mapping[str, Any],
    *,
    default_document_item_name: str = '',
) -> str:
    primary_item_name = str(payload.get('primary_item_name') or '').strip()
    if primary_item_name:
        return primary_item_name

    return resolve_chunk_item_name(
        payload,
        default_document_item_name=default_document_item_name,
    )


def resolve_chunk_display_item_name(
    payload: Mapping[str, Any],
    *,
    default_document_item_name: str = '',
) -> str:
    display_name = resolve_chunk_primary_item_name(
        payload,
        default_document_item_name=default_document_item_name,
    )
    if display_name:
        return display_name

    return str(
        payload.get('title')
        or payload.get('parent_title')
        or payload.get('document_title')
        or payload.get('file_title')
        or ''
    ).strip()


__all__ = [
    'collect_entity_item_names',
    'resolve_document_item_name',
    'resolve_chunk_item_name',
    'resolve_chunk_primary_item_name',
    'resolve_chunk_display_item_name',
]
