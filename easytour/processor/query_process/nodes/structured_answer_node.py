from __future__ import annotations

from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import ANSWER_PROMPT
from easytour.schema.meta_schema import AnswerIntent
from easytour.utils.providers.provider_factory import get_llm_provider
from easytour.utils.sse_util import SSEEvent, push_sse_event


class StructuredAnswerNode(BaseNode):
    name = 'structured_answer_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        docs = list(state.get('reranked_docs') or [])
        answer_intent = str(state.get('answer_intent') or AnswerIntent.GENERIC.value)
        prompt = self._build_prompt(
            answer_intent=answer_intent,
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
                },
            )

        return {
            'prompt': prompt,
            'answer': answer,
            'structured_answer': structured_answer,
            'citations': citations,
        }

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
        query: str,
        item_names: list[str],
        history: list[dict[str, Any]],
        docs: list[dict[str, Any]],
    ) -> str:
        intent_instruction = {
            AnswerIntent.LOOKUP.value: '优先给出准确事实，并明确说明这些事实来自哪些上下文。',
            AnswerIntent.RECOMMENDATION.value: '优先给出推荐项，并说明每个推荐的理由和适用场景。',
            AnswerIntent.PLANNING.value: '优先给出可以直接执行的行程或路线安排。',
            AnswerIntent.COMPARISON.value: '优先给出对比维度、差异点和结论。',
            AnswerIntent.HOWTO.value: '优先给出步骤化建议或操作说明。',
        }.get(answer_intent, '优先给出简洁直接的回答。')
        return ANSWER_PROMPT.format(
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
            return {
                'answer': answer,
                'facts': {
                    'matched_items': item_names,
                    'source_count': len(docs),
                },
            }
        if answer_intent == AnswerIntent.RECOMMENDATION.value:
            recommendations = []
            for doc in docs[:3]:
                recommendations.append(
                    {
                        'name': str(doc.get('item_name') or doc.get('primary_item_name') or doc.get('title') or ''),
                        'reason': str(doc.get('content') or '')[:120],
                        'city': str(doc.get('city') or ''),
                    }
                )
            return {
                'answer': answer,
                'recommendations': recommendations,
            }
        if answer_intent == AnswerIntent.PLANNING.value:
            return {'answer': answer, 'itinerary': []}
        if answer_intent == AnswerIntent.COMPARISON.value:
            return {'answer': answer, 'comparison_table': []}
        if answer_intent == AnswerIntent.HOWTO.value:
            return {'answer': answer, 'steps': []}
        return {'answer': answer}

    def _build_citations(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for doc in docs:
            citation = {
                'source_label_display': str(
                    doc.get('source_label_display') or doc.get('file_title') or doc.get('title') or ''
                ),
                'item_name': str(doc.get('item_name') or doc.get('primary_item_name') or ''),
                'city': str(doc.get('city') or ''),
                'document_id': str(doc.get('document_id') or ''),
            }
            key = (
                citation['source_label_display'],
                citation['item_name'],
                citation['city'],
                citation['document_id'],
            )
            if key in seen:
                continue
            if not any(value for value in key):
                continue
            seen.add(key)
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
