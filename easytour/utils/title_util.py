from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def resolve_file_title(payload: Mapping[str, Any], *, fallback_path: str = '') -> str:
    file_title = str(payload.get('file_title') or '').strip()
    if file_title:
        return file_title

    normalized_path = str(fallback_path or '').strip()
    if not normalized_path:
        return ''

    return Path(normalized_path).name or normalized_path


def derive_document_title_from_file_title(file_title: str) -> str:
    normalized = str(file_title or '').strip()
    if not normalized:
        return ''

    path = Path(normalized)
    if path.suffix:
        return path.stem or normalized
    return normalized


def resolve_document_title(payload: Mapping[str, Any], *, fallback_file_title: str = '') -> str:
    document_title = str(payload.get('document_title') or '').strip()
    if document_title:
        return document_title

    file_title = resolve_file_title(payload, fallback_path=fallback_file_title)
    derived = derive_document_title_from_file_title(file_title)
    if derived:
        return derived

    return str(payload.get('item_name') or '').strip()


def resolve_source_label_display(payload: Mapping[str, Any], *, fallback_file_title: str = '') -> str:
    source_label_display = str(payload.get('source_label_display') or '').strip()
    if source_label_display:
        return source_label_display

    document_title = resolve_document_title(payload, fallback_file_title=fallback_file_title)
    if document_title:
        return document_title

    return resolve_file_title(payload, fallback_path=fallback_file_title)


def resolve_chunk_title(
    payload: Mapping[str, Any],
    *,
    default_document_title: str = '',
    fallback_file_title: str = '',
) -> str:
    title = str(payload.get('title') or '').strip()
    if title:
        return title

    parent_title = str(payload.get('parent_title') or '').strip()
    if parent_title:
        return parent_title

    fallback_payload = dict(payload)
    if default_document_title and not fallback_payload.get('document_title'):
        fallback_payload['document_title'] = default_document_title
    return resolve_document_title(fallback_payload, fallback_file_title=fallback_file_title)


__all__ = [
    'derive_document_title_from_file_title',
    'resolve_chunk_title',
    'resolve_document_title',
    'resolve_file_title',
    'resolve_source_label_display',
]
