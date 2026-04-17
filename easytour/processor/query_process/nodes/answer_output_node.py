from __future__ import annotations

from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import ANSWER_PROMPT
from easytour.utils.providers.provider_factory import get_llm_provider
from easytour.utils.sse_util import SSEEvent, push_sse_event


class AnswerOutputNode(BaseNode):
    """根据最终上下文生成答案。"""

    name = 'answer_output_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """构造 prompt，并以流式或非流式方式输出答案。"""
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        context = self._format_context(state.get('reranked_docs') or [])
        prompt = ANSWER_PROMPT.format(
            context=context or 'No matched context was found.',
            history=self._format_history(state.get('history') or []),
            item_names=', '.join(state.get('item_names') or []) or 'No confirmed item names.',
            question=query,
        )

        llm_client = get_llm_provider().get_client(response_format=False)
        task_id = str(state.get('task_id') or '')
        is_stream = bool(state.get('is_stream'))

        if is_stream and task_id:
            # [修改] 保留原始 SSE 协议，只修复乱码和语法问题。
            chunks: list[str] = []
            for chunk in llm_client.stream(prompt):
                delta = self._extract_chunk_text(chunk)
                if not delta:
                    continue
                chunks.append(delta)
                push_sse_event(task_id, SSEEvent.DELTA, {'delta': delta})
            return {
                'prompt': prompt,
                'answer': ''.join(chunks).strip(),
            }

        response = llm_client.invoke(prompt)
        return {
            'prompt': prompt,
            'answer': str(getattr(response, 'content', '') or '').strip(),
        }

    def _format_context(self, docs: list[dict[str, Any]]) -> str:
        """把精排后的文档拼成模型可读的上下文文本。"""
        lines: list[str] = []
        used_chars = 0
        for index, doc in enumerate(docs, start=1):
            content = str(doc.get('content', '')).strip()
            if not content:
                continue
            title = str(doc.get('title') or doc.get('file_title') or '').strip()
            item_name = str(doc.get('item_name', '')).strip()
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
        """只保留最近几轮对话，避免 prompt 过长。"""
        lines: list[str] = []
        for message in history[-6:]:
            role = str(message.get('role', '')).strip()
            text = str(message.get('text', '')).strip()
            if role and text:
                lines.append(f'{role}: {text}')
        return '\n'.join(lines) or 'No history.'

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        """兼容不同 SDK 的流式返回结构。"""
        content = getattr(chunk, 'content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get('text')
                    if text:
                        parts.append(str(text))
            return ''.join(parts)
        return str(content or '')
