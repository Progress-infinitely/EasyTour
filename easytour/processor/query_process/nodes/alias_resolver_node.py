from __future__ import annotations

from functools import lru_cache

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.services.document_service import DocumentService, get_document_mongo_tool


class AliasResolverNode(BaseNode):
    name = 'alias_resolver_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        if not query:
            return {'resolved_aliases': [], 'rewritten_query': ''}

        alias_map = self._load_alias_map()
        if not alias_map:
            return {'resolved_aliases': [], 'rewritten_query': query}

        rewritten_query = query
        resolved_aliases: list[dict[str, str]] = []
        seen_aliases: set[tuple[str, str]] = set()
        for alias, canonical_name in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
            if not alias or alias not in rewritten_query:
                continue
            if canonical_name and canonical_name not in rewritten_query:
                # [修改] 命中别名后把规范名补回查询，方便后续 item_name_confirm 和检索过滤稳定工作。
                rewritten_query = rewritten_query.replace(alias, f'{alias}（{canonical_name}）')
            key = (alias, canonical_name)
            if key in seen_aliases:
                continue
            seen_aliases.add(key)
            resolved_aliases.append({'alias': alias, 'canonical_name': canonical_name})

        return {
            'resolved_aliases': resolved_aliases,
            'rewritten_query': rewritten_query,
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_alias_map() -> dict[str, str]:
        alias_map = AliasResolverNode._load_alias_map_from_mongo()
        if alias_map:
            return alias_map
        return AliasResolverNode._load_alias_map_from_documents()

    @staticmethod
    def _load_alias_map_from_mongo() -> dict[str, str]:
        mongo_tool = get_document_mongo_tool()
        if mongo_tool is None:
            return {}

        alias_map: dict[str, str] = {}
        try:
            cursor = mongo_tool.db['entity_aliases'].find({}, {'_id': 0})
        except Exception:
            return {}

        for item in cursor:
            canonical_name = str(item.get('canonical_name') or item.get('item_name') or '').strip()
            for alias in item.get('aliases') or []:
                normalized_alias = str(alias).strip()
                if normalized_alias and canonical_name:
                    alias_map[normalized_alias] = canonical_name
        return alias_map

    @staticmethod
    def _load_alias_map_from_documents() -> dict[str, str]:
        alias_map: dict[str, str] = {}
        try:
            documents = DocumentService().list_documents()
        except Exception:
            return {}

        for document in documents:
            for entity in document.get('main_entities') or []:
                canonical_name = str((entity or {}).get('item_name') or '').strip()
                for alias in (entity or {}).get('aliases') or []:
                    normalized_alias = str(alias).strip()
                    if normalized_alias and canonical_name:
                        alias_map[normalized_alias] = canonical_name
        return alias_map
