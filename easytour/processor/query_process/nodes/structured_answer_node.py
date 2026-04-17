from __future__ import annotations

from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import ANSWER_PROMPT, get_intent_instruction
from easytour.schema.meta_schema import AnswerIntent
from easytour.services.trace_service import TraceService
from easytour.utils.providers.provider_factory import get_llm_provider
from easytour.utils.sse_util import SSEEvent, push_sse_event

_trace_service = TraceService()


class StructuredAnswerNode(BaseNode):
    name = 'structured_answer_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        docs = list(state.get('reranked_docs') or [])
        answer_intent = str(state.get('answer_intent') or AnswerIntent.GENERIC.value)
        retrieval_type = str(state.get('retrieval_type') or '').strip()
        prompt = self._build_prompt(
            answer_intent=answer_intent,
            retrieval_type=retrieval_type,
            query=query,
            item_names=state.get('item_names') or [],
            history=state.get('history') or [],
            docs=docs,
        )
        citations = self._build_citations(docs)

        answer = self._generate_answer(
            prompt=prompt,
            task_id=str(state.get('task_id') or ''),
            is_stream=bool(state.get('is_stream')),
        )
        structured_answer = self._build_structured_answer(
            answer_intent=answer_intent,
            answer=answer,
            docs=docs,
            item_names=state.get('item_names') or [],
        )

        task_id = str(state.get('task_id') or '')
        if state.get('is_stream') and task_id:
            # [修改] 这里只发送 FINAL_ANSWER，最终完成事件交给 QueryService 统一收口，避免流式重复结束。
            push_sse_event(
                task_id,
                SSEEvent.FINAL_ANSWER,
                {
                    'answer': answer,
                    'structured': structured_answer,
                    'citations': citations,
                    'retrieval_type': retrieval_type,
                    'answer_intent': answer_intent,
                    'region': dict(state.get('region_filter') or {}),
                },
            )

        result: QueryGraphState = {
            'prompt': prompt,
            'answer': answer,
            'structured_answer': structured_answer,
            'citations': citations,
        }

        _trace_service.record({
            'task_id': str(state.get('task_id') or ''),
            'session_id': str(state.get('session_id') or ''),
            'original_query': str(state.get('original_query') or ''),
            'rewritten_query': query,
            'retrieval_type': str(state.get('retrieval_type') or ''),
            'answer_intent': answer_intent,
            'region_filter': dict(state.get('region_filter') or {}),
            'milvus_expr': str(state.get('retrieval_filters') or ''),
            'topk_chunk_ids': list(state.get('topk_chunk_ids') or []),
            'topk_scores': list(state.get('topk_scores') or []),
            'reranked_chunk_ids': list(state.get('reranked_chunk_ids') or []),
            'model_name': str(self.config.default_model or ''),
            'latency_ms': dict(state.get('latency_ms') or {}),
        })

        return result

    def _generate_answer(self, *, prompt: str, task_id: str, is_stream: bool) -> str:
        try:
            llm_client = get_llm_provider().get_client(response_format=False)
        except Exception:
            return self._fallback_answer(prompt)

        if is_stream and task_id:
            chunks: list[str] = []
            for chunk in llm_client.stream(prompt):
                delta = self._extract_chunk_text(chunk)
                if not delta:
                    continue
                chunks.append(delta)
                push_sse_event(task_id, SSEEvent.DELTA, {'delta': delta})
            return ''.join(chunks).strip()

        try:
            response = llm_client.invoke(prompt)
            return str(getattr(response, 'content', '') or '').strip()
        except Exception:
            return self._fallback_answer(prompt)

    def _build_prompt(
        self,
        *,
        answer_intent: str,
        retrieval_type: str,
        query: str,
        item_names: list[str],
        history: list[dict[str, Any]],
        docs: list[dict[str, Any]],
    ) -> str:
        intent_instruction = get_intent_instruction(answer_intent)
        return ANSWER_PROMPT.format(
            retrieval_focus=self._build_retrieval_focus_instruction(retrieval_type),
            answer_intent=answer_intent,
            intent_instruction=intent_instruction,
            history=self._format_history(history),
            context=self._format_context(docs) or '没有检索到可用上下文。',
            item_names=', '.join(item_names) or '未识别主体',
            question=query,
        )

    def _build_structured_answer(
        self,
        *,
        answer_intent: str,
        answer: str,
        docs: list[dict[str, Any]],
        item_names: list[str],
    ) -> dict[str, Any]:
        if answer_intent == AnswerIntent.LOOKUP.value:
            # 从命中的 chunk 中聚合事实字段（取首个非空值）
            facts: dict[str, Any] = {'matched_items': item_names, 'source_count': len(docs)}
            for field in ('opening_hours', 'ticket_price', 'best_season', 'price_range'):
                for doc in docs:
                    val = doc.get(field)
                    if val and str(val).strip():
                        facts[field] = str(val).strip()
                        break
            for list_field in ('tips', 'notes'):
                merged: list[str] = []
                seen_tips: set[str] = set()
                for doc in docs:
                    for item in (doc.get(list_field) or []):
                        s = str(item).strip()
                        if s and s not in seen_tips:
                            merged.append(s)
                            seen_tips.add(s)
                if merged:
                    facts[list_field] = merged[:5]
            return {'answer': answer, 'facts': facts}

        if answer_intent == AnswerIntent.RECOMMENDATION.value:
            seen_names: set[str] = set()
            recommendations: list[dict[str, Any]] = []
            for doc in docs:
                name = str(doc.get('primary_item_name') or doc.get('item_name') or doc.get('title') or '').strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                rec: dict[str, Any] = {
                    'name': name,
                    'reason': str(doc.get('content') or '')[:150].strip(),
                    'city': str(doc.get('city') or ''),
                }
                if doc.get('best_season'):
                    rec['best_season'] = str(doc['best_season'])
                suitable = doc.get('suitable_for') or []
                if suitable:
                    rec['suitable_for'] = list(suitable)[:3]
                if doc.get('attraction_features'):
                    rec['features'] = list(doc['attraction_features'])[:3]
                recommendations.append(rec)
                if len(recommendations) >= 5:
                    break
            return {'answer': answer, 'recommendations': recommendations}

        if answer_intent == AnswerIntent.PLANNING.value:
            route_info: dict[str, Any] = {}
            for doc in docs:
                if doc.get('route_days') and not route_info.get('days'):
                    route_info['days'] = str(doc['route_days'])
                if doc.get('route_budget') and not route_info.get('budget'):
                    route_info['budget'] = str(doc['route_budget'])
            result: dict[str, Any] = {'answer': answer, 'itinerary': []}
            if route_info:
                result.update(route_info)
            return result

        if answer_intent == AnswerIntent.COMPARISON.value:
            return {'answer': answer, 'comparison_table': []}

        if answer_intent == AnswerIntent.HOWTO.value:
            all_tips: list[str] = []
            seen_t: set[str] = set()
            for doc in docs:
                for t in (doc.get('tips') or []):
                    s = str(t).strip()
                    if s and s not in seen_t:
                        all_tips.append(s)
                        seen_t.add(s)
            return {'answer': answer, 'steps': [], 'tips': all_tips[:5]}

        return {'answer': answer}

    @staticmethod
    def _build_retrieval_focus_instruction(retrieval_type: str) -> str:
        focus_map = {
            'attraction': '景点：优先回答景点、片区玩法和游览体验，不要扩展成酒店或美食推荐。',
            'route': '路线：优先回答行程安排和路线组合，不要扩展成泛目的地介绍。',
            'hotel': '酒店：优先回答住哪里、住宿区域和酒店选择，不要扩展成景点推荐。',
            'food': '美食：优先回答吃什么、哪里吃、觅食片区和口味建议，不要把景点当主推荐项。',
            'transport': '交通：优先回答怎么去、怎么转场和交通方式，不要扩展成景点推荐。',
            'culture': '文化：优先回答历史、人文、民俗和文化体验，不要扩展成泛旅游推荐。',
        }
        return focus_map.get(str(retrieval_type or '').strip(), '未限定：根据上下文聚焦回答。')

    def _build_citations(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for doc in docs:
            # [修改] 引用补充来源类型/网页链接/chunk_id，前端才能区分网页跳转和本地命中片段预览。
            source_type = 'web_search' if str(doc.get('retrieval_source') or '').strip() == 'web_search' else 'document'
            citation = {
                'source_label_display': str(
                    doc.get('source_label_display') or doc.get('file_title') or doc.get('title') or ''
                ),
                'item_name': str(doc.get('item_name') or doc.get('primary_item_name') or ''),
                'city': str(doc.get('city') or ''),
                'document_id': str(doc.get('document_id') or ''),
                'source_type': source_type,
                'source_url': str(doc.get('url') or ''),
                'chunk_id': str(doc.get('chunk_id') or ''),
            }
            if not any(
                citation.get(field)
                for field in ('source_label_display', 'item_name', 'city', 'document_id', 'source_url', 'chunk_id')
            ):
                continue
            citations.append(citation)
        return citations

    def _format_context(self, docs: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        used_chars = 0
        for index, doc in enumerate(docs, start=1):
            content = str(doc.get('content') or doc.get('snippet') or '').strip()
            if not content:
                continue
            title = str(doc.get('title') or doc.get('file_title') or '').strip()
            item_name = str(doc.get('item_name') or doc.get('primary_item_name') or '').strip()
            header_parts = [f'[{index}]']
            if item_name:
                header_parts.append(f'item={item_name}')
            if title:
                header_parts.append(f'title={title}')
            entry = ' '.join(header_parts) + '\n' + content
            if used_chars + len(entry) > self.config.max_context_chars:
                break
            lines.append(entry)
            used_chars += len(entry) + 2
        return '\n\n'.join(lines)

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in history[-6:]:
            role = str(message.get('role', '')).strip()
            text = str(message.get('text', '')).strip()
            if role and text:
                lines.append(f'{role}: {text}')
        return '\n'.join(lines) or '无历史消息。'

    @staticmethod
    def _fallback_answer(prompt: str) -> str:
        prompt_lines = [line.strip() for line in prompt.splitlines() if line.strip()]
        if not prompt_lines:
            return ''
        fallback = prompt_lines[-1]
        fallback = fallback.replace('用户问题:', '').replace('用户问题：', '').strip()
        return fallback

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        content = getattr(chunk, 'content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict) and item.get('text'):
                    parts.append(str(item['text']))
            return ''.join(parts)
        return str(content or '')
