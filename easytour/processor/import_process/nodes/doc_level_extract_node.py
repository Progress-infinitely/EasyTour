from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.state import ImportGraphState
from easytour.prompts.upload.import_prompt import DOC_LEVEL_EXTRACT_SYSTEM as _SYSTEM, DOC_LEVEL_EXTRACT_USER_TEMPLATE as _USER_TEMPLATE
from easytour.schema.meta_schema import ContentType
from easytour.utils.item_name_util import resolve_document_item_name
from easytour.utils.title_util import resolve_document_title
from easytour.utils.providers.provider_factory import get_llm_provider
from easytour.utils.region_normalizer import RegionInfo, normalize_region


class DocLevelExtractNode(BaseNode):
    name = 'doc_level_extract_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        override_content_type = str(state.get('override_content_type') or '').strip()
        override_region = str(state.get('override_region') or '').strip()
        override_document_title = str(state.get('override_document_title') or '').strip()

        # 三个 override 都有时，跳过 LLM 直接组装
        if override_content_type and override_region and override_document_title:
            return self._from_override_only(state)

        extracted = self._call_llm(state) or self._heuristic_fallback(state)
        return self._merge(state, extracted)

    def _call_llm(self, state: ImportGraphState) -> dict[str, Any] | None:
        md_content = str(state.get('md_content') or '').strip()
        file_title = str(state.get('file_title') or '').strip()
        content_preview = (md_content or file_title)[:4000]
        if not content_preview:
            return None

        prompt = _USER_TEMPLATE.format(
            content_types=[ct.value for ct in ContentType],
            file_title=file_title,
            content=content_preview,
        )
        try:
            llm = get_llm_provider().get_client(response_format=True)
            resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)])
            return _parse_json(resp.content)
        except Exception as exc:
            self.logger.warning('doc_level_extract LLM failed: %s', exc)
            return None

    def _heuristic_fallback(self, state: ImportGraphState) -> dict[str, Any]:
        file_title = str(state.get('file_title') or '').strip()
        lowered = file_title.lower()
        content_type = 'attraction'
        if any(kw in lowered for kw in ('hotel', '酒店', '民宿', '住宿')):
            content_type = 'hotel'
        elif any(kw in lowered for kw in ('food', '美食', '餐厅', '小吃')):
            content_type = 'food'
        elif any(kw in lowered for kw in ('交通', '地铁', '机场', '高铁')):
            content_type = 'transport'
        elif any(kw in lowered for kw in ('路线', '行程', '攻略', '一日游')):
            content_type = 'route'
        elif any(kw in lowered for kw in ('文化', '博物馆', '非遗', '古迹')):
            content_type = 'culture'

        region = normalize_region(file_title)
        item_name = str(resolve_document_item_name(state) or file_title).strip()
        return {
            'content_type': content_type,
            'province': region.province,
            'city': region.city,
            'region_path': region.region_path,
            'document_title': resolve_document_title(
                {
                    'document_title': state.get('document_title') or '',
                    'file_title': file_title,
                    'item_name': item_name,
                },
                fallback_file_title=file_title,
            ),
            'main_entities': [{'item_name': item_name, 'item_type': content_type}] if item_name else [],
        }

    def _from_override_only(self, state: ImportGraphState) -> ImportGraphState:
        region = normalize_region(str(state.get('override_region') or ''))
        return {
            'doc_content_type': str(state.get('override_content_type') or ''),
            'doc_province': region.province,
            'doc_city': region.city,
            'doc_region_path': region.region_path,
            'document_title': resolve_document_title(
                {
                    'document_title': state.get('override_document_title') or state.get('document_title') or '',
                    'file_title': state.get('file_title') or '',
                },
                fallback_file_title=str(state.get('file_title') or ''),
            ),
            'doc_main_entities': list(state.get('doc_main_entities') or []),
        }

    def _merge(self, state: ImportGraphState, extracted: dict[str, Any]) -> ImportGraphState:
        override_content_type = str(state.get('override_content_type') or '').strip()
        override_region = str(state.get('override_region') or '').strip()
        override_document_title = str(state.get('override_document_title') or '').strip()

        content_type = override_content_type or _normalize_content_type(str(extracted.get('content_type') or '')) or 'attraction'

        if override_region:
            region = normalize_region(override_region)
        else:
            province = str(extracted.get('province') or '')
            city = str(extracted.get('city') or '')
            region_path = str(extracted.get('region_path') or '')
            region_seed = region_path or f'{province}/{city}'.strip('/')
            region = normalize_region(region_seed)
            # LLM 直接给出了字段但 normalize_region 未能识别时，兜底直接使用
            if not region.province and province:
                region = RegionInfo(
                    raw=region_seed,
                    province=province,
                    city=city,
                    region_path=region_path or '/'.join(p for p in (province, city) if p),
                )

        document_title = resolve_document_title(
            {
                'document_title': override_document_title or extracted.get('document_title') or state.get('document_title') or '',
                'file_title': state.get('file_title') or '',
            },
            fallback_file_title=str(state.get('file_title') or ''),
        )

        raw_entities = extracted.get('main_entities') or []
        main_entities: list[dict[str, Any]] = []
        for ent in raw_entities:
            if not isinstance(ent, dict):
                continue
            item_name = str(ent.get('item_name') or '').strip()
            if item_name:
                main_entities.append({
                    'item_name': item_name,
                    'item_type': str(ent.get('item_type') or content_type),
                    'aliases': list(ent.get('aliases') or []),
                })

        if not main_entities:
            fallback_state = dict(state)
            fallback_state['document_title'] = document_title
            item_name = resolve_document_item_name(fallback_state)
            if item_name:
                main_entities = [{'item_name': item_name, 'item_type': content_type, 'aliases': []}]

        return {
            'doc_content_type': content_type,
            'doc_province': region.province,
            'doc_city': region.city,
            'doc_region_path': region.region_path,
            'document_title': document_title,
            'doc_main_entities': main_entities,
        }


def _normalize_content_type(value: str) -> str:
    valid = {ct.value for ct in ContentType}
    return value if value in valid else ''


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
