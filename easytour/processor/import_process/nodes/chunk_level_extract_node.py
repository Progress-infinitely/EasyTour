from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.config import get_config
from easytour.processor.import_process.state import ImportGraphState
from easytour.prompts.upload.import_prompt import (
    CHUNK_LEVEL_EXTRACT_SYSTEM as _SYSTEM,
    CHUNK_LEVEL_EXTRACT_COMMON_FIELDS as _COMMON_FIELDS_DESC,
    CHUNK_LEVEL_EXTRA_FIELDS as _EXTRA_FIELDS,
    CHUNK_LEVEL_EXTRACT_USER_TEMPLATE as _USER_TEMPLATE,
)
from easytour.utils.item_name_util import resolve_chunk_primary_item_name
from easytour.utils.providers.provider_factory import get_llm_provider

_BATCH_SIZE = 5

_TOURIST_SUFFIXES = ('景区', '寺', '湾', '岛', '塔', '山', '海', '酒店', '街', '馆', '园', '洞', '峰', '湖', '瀑')


class ChunkLevelExtractNode(BaseNode):
    name = 'chunk_level_extract_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = list(state.get('chunks') or [])
        if not chunks:
            return {}

        content_type = str(state.get('doc_content_type') or 'attraction').strip()
        main_entities = list(state.get('doc_main_entities') or [])
        known_names = {str(e.get('item_name') or '').strip() for e in main_entities if e.get('item_name')}

        enriched = self._enrich_all(chunks, content_type, known_names)
        suspected = _collect_suspected(enriched, known_names)
        return {'chunks': enriched, 'suspected_new_entities': suspected}

    def _enrich_all(self, chunks: list[dict[str, Any]], content_type: str, known_names: set[str]) -> list[dict[str, Any]]:
        result = list(chunks)
        batches = [
            (batch_start, chunks[batch_start:batch_start + _BATCH_SIZE])
            for batch_start in range(0, len(chunks), _BATCH_SIZE)
        ]
        # [修改] 批与批之间并行调用 LLM，提高吞吐；批内仍保留 _BATCH_SIZE 个 chunk 的合并请求。
        concurrency = max(1, min(get_config().chunk_extract_concurrency, len(batches) or 1))

        def run(indexed_batch: tuple[int, list[dict[str, Any]]]) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
            batch_start, batch = indexed_batch
            extracted = self._extract_batch(batch, content_type)
            return batch_start, batch, extracted

        if concurrency == 1:
            iter_results = (run(item) for item in batches)
        else:
            pool = ThreadPoolExecutor(max_workers=concurrency)
            try:
                iter_results = list(pool.map(run, batches))
            finally:
                pool.shutdown(wait=True)

        for batch_start, batch, extracted_list in iter_results:
            for offset, (chunk, fields) in enumerate(zip(batch, extracted_list)):
                merged = dict(chunk)
                if fields:
                    for key, val in fields.items():
                        if val not in ('', None, 0, [], {}):
                            merged[key] = val
                    # 只在 LLM 给出了更好的 primary_item_name 时更新
                    llm_primary = str(fields.get('primary_item_name') or '').strip()
                    if llm_primary:
                        merged['primary_item_name'] = llm_primary
                merged['entity_names'] = _build_entity_names(merged, known_names)
                result[batch_start + offset] = merged
        return result

    def _extract_batch(self, batch: list[dict[str, Any]], content_type: str) -> list[dict[str, Any]]:
        extra = _EXTRA_FIELDS.get(content_type, '')
        sep = ', ' if extra else ''
        chunks_text = '\n\n'.join(
            f'[{i + 1}] {str(chunk.get("content") or "")[:800]}'
            for i, chunk in enumerate(batch)
        )
        prompt = _USER_TEMPLATE.format(
            content_type=content_type,
            common_fields=_COMMON_FIELDS_DESC,
            sep=sep,
            extra_fields=extra,
            count=len(batch),
            chunks_text=chunks_text,
        )
        try:
            llm = get_llm_provider().get_client(response_format=True)
            resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)])
            payload = _parse_json(resp.content)
            items = payload.get('items') or []
            if isinstance(items, list):
                return [dict(item) if isinstance(item, dict) else {} for item in items[:len(batch)]]
        except Exception as exc:
            self.logger.warning('chunk_level_extract batch [%d] failed: %s', len(batch), exc)
        return [{} for _ in batch]


def _build_entity_names(chunk: dict[str, Any], known_names: set[str]) -> list[str]:
    names: list[str] = []
    primary = resolve_chunk_primary_item_name(chunk)
    if primary:
        names.append(primary)

    content = str(chunk.get('content') or '')
    for name in known_names:
        if name and name in content and name not in names:
            names.append(name)

    for title_field in ('title', 'parent_title'):
        title = str(chunk.get(title_field) or '').strip()
        if 2 <= len(title) <= 20 and any(s in title for s in _TOURIST_SUFFIXES):
            if title not in names and title not in known_names:
                names.append(title)

    return list(dict.fromkeys(names))


def _collect_suspected(chunks: list[dict[str, Any]], known_names: set[str]) -> list[str]:
    suspected: list[str] = []
    for chunk in chunks:
        for name in (chunk.get('entity_names') or []):
            name_str = str(name or '').strip()
            if name_str and name_str not in known_names and name_str not in suspected:
                suspected.append(name_str)
    return suspected


def _parse_json(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    text = str(content or '').strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                return result if isinstance(result, dict) else {}
            except JSONDecodeError:
                pass
    return {}
