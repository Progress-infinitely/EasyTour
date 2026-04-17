from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from easytour.processor.import_process.config import get_config
from easytour.utils.hashing import build_chunk_hash


class _SimpleImportGraph:
    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return _run_import_pipeline(state)


def create_import_graph() -> _SimpleImportGraph:
    return _SimpleImportGraph()


def _run_import_pipeline(state: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    file_path = str(state.get('import_file_path') or '')
    file_name = Path(file_path).name or str(state.get('file_title') or 'uploaded_file')
    file_stem = Path(file_name).stem or file_name
    content = _read_source_content(file_path, file_stem)

    state['file_title'] = str(state.get('file_title') or file_name)
    state['document_title'] = str(state.get('document_title') or file_stem)
    state['item_name'] = str(state.get('item_name') or file_stem)
    state['doc_main_entities'] = list(
        state.get('doc_main_entities')
        or [{'item_name': state['item_name'], 'item_type': state.get('doc_content_type') or 'generic', 'aliases': []}]
    )

    chunks = []
    chunk_size = max(int(config.max_content_length or 1200), 300)
    for index, chunk_text in enumerate(_split_text(content, chunk_size)):
        chunks.append(
            {
                'content': chunk_text,
                'title': state['document_title'],
                'parent_title': state['document_title'],
                'file_title': state['file_title'],
                'item_name': state['item_name'],
                'primary_item_name': state['item_name'],
                'entity_names': [state['item_name']],
                'chunk_index': index,
                'chunk_hash': build_chunk_hash(chunk_text),
                'dense_vector': _build_dense_vector(chunk_text, int(config.embedding_dim or 1024)),
                'sparse_vector': {0: 1.0},
                'tips': '',
                'notes': '',
                'suspected_new_entities': [],
            }
        )

    state['chunks'] = chunks
    state['pending_chunks_snapshot'] = list(state.get('pending_chunks_snapshot') or [])
    state['chunks_snapshot'] = list(state.get('chunks_snapshot') or chunks)
    return state


def _read_source_content(file_path: str, fallback: str) -> str:
    path = Path(file_path)
    if path.suffix.lower() in {'.md', '.markdown', '.txt'}:
        try:
            return path.read_text(encoding='utf-8')
        except Exception:
            return path.read_text(encoding='utf-8', errors='ignore')
    return fallback


def _split_text(text: str, chunk_size: int) -> list[str]:
    normalized = (text or '').strip()
    if not normalized:
        return ['']
    return [normalized[index:index + chunk_size] for index in range(0, len(normalized), chunk_size)]


def _build_dense_vector(text: str, dim: int) -> list[float]:
    dim = max(dim, 8)
    digest = hashlib.sha256(text.encode('utf-8')).digest()
    values: list[float] = []
    while len(values) < dim:
        for byte in digest:
            values.append(byte / 255.0)
            if len(values) >= dim:
                break
    return values
