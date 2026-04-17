from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.schema.meta_schema import AnswerIntent, ContentType
from easytour.utils.providers.provider_factory import get_llm_provider
from easytour.utils.region_normalizer import normalize_region


class IntentRouteNode(BaseNode):
    name = 'intent_route_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        original_query = str(state.get('original_query') or '').strip()
        if not original_query:
            return {
                'retrieval_type': ContentType.ATTRACTION.value,
                'answer_intent': AnswerIntent.GENERIC.value,
                'region_filter': {'province': '', 'city': '', 'region_path': ''},
                'rewritten_query': '',
            }

        # [修改] 二阶段先做意图路由，给后续检索类型、结构化回答和地区过滤提供统一约束。
        route = self._route_with_llm(original_query, state.get('history') or [])
        if route is None:
            route = self._route_heuristically(original_query)

        preset_retrieval_type = str(state.get('retrieval_type') or '').strip()
        preset_region_filter = dict(state.get('region_filter') or {})
        if preset_retrieval_type:
            route['retrieval_type'] = preset_retrieval_type
            # [修改] 当前端显式选了检索类型时，短查询要强制往该类型收敛，避免“成都 + 美食”被回答成泛目的地推荐。
            route = self._apply_preset_type_focus(route, original_query=original_query, preset_retrieval_type=preset_retrieval_type)
        if any(str(preset_region_filter.get(key) or '').strip() for key in ('province', 'city', 'region_path')):
            route['region_filter'] = preset_region_filter

        return route

    def _apply_preset_type_focus(
        self,
        route: QueryGraphState,
        *,
        original_query: str,
        preset_retrieval_type: str,
    ) -> QueryGraphState:
        focused_route = dict(route)
        current_intent = str(focused_route.get('answer_intent') or '').strip()
        current_rewritten_query = str(focused_route.get('rewritten_query') or original_query).strip() or original_query

        if self._needs_type_focus(original_query, current_intent):
            focused_route['answer_intent'] = self._default_answer_intent_for_type(preset_retrieval_type)
            focused_route['rewritten_query'] = self._rewrite_query_for_type_focus(
                current_rewritten_query,
                preset_retrieval_type=preset_retrieval_type,
            )
        return focused_route

    @staticmethod
    def _needs_type_focus(query: str, answer_intent: str) -> bool:
        normalized_query = str(query or '').strip()
        if not normalized_query:
            return False
        if answer_intent and answer_intent != AnswerIntent.GENERIC.value:
            return False
        # [修改] 只对“成都 / 三亚 / 春熙路”这类短而泛的问题加类型聚焦，避免误伤已表达明确意图的问句。
        return len(normalized_query) <= 12

    @staticmethod
    def _default_answer_intent_for_type(retrieval_type: str) -> str:
        type_to_intent = {
            ContentType.ROUTE.value: AnswerIntent.PLANNING.value,
            ContentType.TRANSPORT.value: AnswerIntent.HOWTO.value,
            ContentType.ATTRACTION.value: AnswerIntent.RECOMMENDATION.value,
            ContentType.HOTEL.value: AnswerIntent.RECOMMENDATION.value,
            ContentType.FOOD.value: AnswerIntent.RECOMMENDATION.value,
            ContentType.CULTURE.value: AnswerIntent.RECOMMENDATION.value,
        }
        return type_to_intent.get(str(retrieval_type or '').strip(), AnswerIntent.GENERIC.value)

    @staticmethod
    def _rewrite_query_for_type_focus(query: str, *, preset_retrieval_type: str) -> str:
        normalized_query = str(query or '').strip()
        if not normalized_query:
            return query

        suffix_map = {
            ContentType.ATTRACTION.value: '有哪些值得去的景点？',
            ContentType.ROUTE.value: '适合怎么安排行程？',
            ContentType.HOTEL.value: '住哪里比较合适？',
            ContentType.FOOD.value: '有什么值得推荐的美食？',
            ContentType.TRANSPORT.value: '交通怎么安排更方便？',
            ContentType.CULTURE.value: '有哪些值得体验的文化内容？',
        }
        suffix = suffix_map.get(str(preset_retrieval_type or '').strip())
        if not suffix:
            return normalized_query

        if normalized_query.endswith(('？', '?', '。', '.', '！', '!')):
            normalized_query = normalized_query[:-1].strip()
        return f'{normalized_query}{suffix}'

    def _route_with_llm(self, query: str, history: list[dict[str, Any]]) -> QueryGraphState | None:
        try:
            llm_client = get_llm_provider().get_client(response_format=True)
        except Exception:
            return None

        history_lines = []
        for item in history[-4:]:
            role = str(item.get('role') or '').strip()
            text = str(item.get('text') or '').strip()
            if role and text:
                history_lines.append(f'{role}: {text}')

        prompt = (
            '你是 EasyTour 的查询路由器，请只返回 JSON。\n'
            '必须包含 retrieval_type、answer_intent、rewritten_query、region_filter 四个字段。\n'
            f'可选 retrieval_type: {[item.value for item in ContentType]}\n'
            f'可选 answer_intent: {[item.value for item in AnswerIntent]}\n'
            '如果判断不出来，retrieval_type 用 "attraction"，answer_intent 用 "generic"。\n'
            'region_filter 输出 {province, city, region_path}，没有就填空字符串。\n'
            f'最近历史：\n{chr(10).join(history_lines) or "无历史消息"}\n'
            f'用户问题：\n{query}'
        )
        try:
            response = llm_client.invoke(
                [
                    SystemMessage(content='Return valid JSON only.'),
                    HumanMessage(content=prompt),
                ]
            )
            payload = self._parse_json_payload(response.content)
        except Exception:
            return None

        retrieval_type = str(payload.get('retrieval_type') or '').strip()
        if retrieval_type not in {item.value for item in ContentType}:
            retrieval_type = ContentType.ATTRACTION.value

        answer_intent = str(payload.get('answer_intent') or '').strip()
        if answer_intent not in {item.value for item in AnswerIntent}:
            answer_intent = AnswerIntent.GENERIC.value

        region_filter = payload.get('region_filter') or {}
        if not isinstance(region_filter, dict):
            region_filter = {}

        return {
            'retrieval_type': retrieval_type,
            'answer_intent': answer_intent,
            'region_filter': self._derive_route_region_filter(region_filter, query),
            'rewritten_query': str(payload.get('rewritten_query') or query).strip() or query,
        }

    def _route_heuristically(self, query: str) -> QueryGraphState:
        lowered = query.lower()

        retrieval_type = ContentType.ATTRACTION.value
        if any(keyword in lowered for keyword in ('hotel', '民宿', '酒店', '住宿', '住哪')):
            retrieval_type = ContentType.HOTEL.value
        elif any(keyword in lowered for keyword in ('food', '美食', '餐厅', '小吃', '吃什么')):
            retrieval_type = ContentType.FOOD.value
        elif any(keyword in lowered for keyword in ('交通', '怎么去', '打车', '公交', '地铁', '高铁', '机场')):
            retrieval_type = ContentType.TRANSPORT.value
        elif any(keyword in lowered for keyword in ('路线', '行程', '攻略', '一日游', '两日游')):
            retrieval_type = ContentType.ROUTE.value
        elif any(keyword in lowered for keyword in ('文化', '历史', '博物馆', '非遗', '古迹')):
            retrieval_type = ContentType.CULTURE.value

        answer_intent = AnswerIntent.GENERIC.value
        if any(keyword in lowered for keyword in ('对比', '比较', '区别', '哪个好')):
            answer_intent = AnswerIntent.COMPARISON.value
        elif any(keyword in lowered for keyword in ('计划', '行程安排', ' itinerary ', '路线安排')):
            answer_intent = AnswerIntent.PLANNING.value
        elif any(keyword in lowered for keyword in ('怎么', '如何', '步骤', '指南', '攻略')):
            answer_intent = AnswerIntent.HOWTO.value
        elif any(keyword in lowered for keyword in ('推荐', '必去', '值得', '哪里好玩', '有什么好')):
            answer_intent = AnswerIntent.RECOMMENDATION.value
        elif any(
            keyword in lowered
            for keyword in ('门票', '开放', '营业', '地址', '电话', '几点', '多久', '多少钱', '预约')
        ):
            answer_intent = AnswerIntent.LOOKUP.value

        return {
            'retrieval_type': retrieval_type,
            'answer_intent': answer_intent,
            'region_filter': self._derive_route_region_filter({}, query),
            'rewritten_query': query,
        }

    @staticmethod
    def _derive_route_region_filter(region_filter: dict[str, Any], query: str) -> dict[str, str]:
        region_seed = ' '.join(
            str(region_filter.get(key) or '').strip()
            for key in ('province', 'city', 'region_path')
            if str(region_filter.get(key) or '').strip()
        )

        if region_seed:
            normalized = normalize_region(region_seed)
            if normalized.province or normalized.city:
                return {
                    'province': normalized.province,
                    'city': normalized.city,
                    'region_path': normalized.region_path,
                }

        fallback = normalize_region(query)
        if fallback.province or fallback.city:
            return {
                'province': fallback.province,
                'city': fallback.city,
                'region_path': fallback.region_path,
            }

        # [修改] 没识别出明确地区时直接留空，避免把整句 query 当成 region_path 继续往下过滤。
        return {'province': '', 'city': '', 'region_path': ''}

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
