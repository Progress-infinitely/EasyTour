from __future__ import annotations

import time
import uuid
from typing import Any

from easytour.processor.query_process.main_graph import create_query_graph
from easytour.processor.query_process.state import create_default_state
from easytour.utils.mongo_history_util import clear_history, get_recent_messages, save_chat_message
from easytour.utils.region_normalizer import infer_region
from easytour.utils.sse_util import SSEEvent, create_sse_queue, push_sse_event
from easytour.utils.task_util import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    set_task_result,
    update_task_status,
)


class QueryService:
    def __init__(self) -> None:
        self._query_app = create_query_graph()

    def generate_session_id(self) -> str:
        return uuid.uuid4().hex

    def generate_task_id(self) -> str:
        return uuid.uuid4().hex

    def submit_query(self, task_id: str, is_stream: bool) -> None:
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        set_task_result(task_id, 'is_stream', is_stream)
        if is_stream:
            create_sse_queue(task_id)

    def run_query(
        self,
        *,
        query: str,
        session_id: str,
        task_id: str,
        message_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
        is_stream: bool = False,
        retrieval_type: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        normalized_history = list(history or self.get_history(session_id, 20))
        user_message_id = save_chat_message(
            session_id=session_id,
            role='user',
            text=query,
            message_id=message_id,
        )

        initial_state = create_default_state(
            original_query=query,
            rewritten_query=query,
            session_id=session_id,
            task_id=task_id,
            message_id=user_message_id,
            history=normalized_history,
            is_stream=is_stream,
            latency_ms={},
        )
        if retrieval_type:
            initial_state['retrieval_type'] = str(retrieval_type)
        if region:
            initial_state['region_filter'] = infer_region(region, region).to_dict()

        try:
            started_at = time.perf_counter()
            final_state = self._query_app.invoke(initial_state)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            final_state.setdefault('latency_ms', {})
            final_state['latency_ms']['query_total'] = elapsed_ms

            answer = str(final_state.get('answer') or '')
            citations = list(final_state.get('citations') or [])
            assistant_message_id = save_chat_message(
                session_id=session_id,
                role='assistant',
                text=answer,
                rewritten_query=str(final_state.get('rewritten_query') or query),
                item_names=list(final_state.get('item_names') or []),
                image_urls=list(final_state.get('image_urls') or []),
                citations=citations,
            )

            update_task_status(task_id, TASK_STATUS_COMPLETED)
            set_task_result(task_id, 'answer', answer)
            set_task_result(task_id, 'message_id', assistant_message_id)
            set_task_result(task_id, 'image_urls', list(final_state.get('image_urls') or []))
            set_task_result(task_id, 'rewritten_query', str(final_state.get('rewritten_query') or query))
            set_task_result(task_id, 'item_names', list(final_state.get('item_names') or []))
            set_task_result(task_id, 'structured_answer', dict(final_state.get('structured_answer') or {}))
            set_task_result(task_id, 'citations', citations)

            if is_stream:
                push_sse_event(
                    task_id,
                    SSEEvent.FINAL,
                    {
                        'answer': answer,
                        'image_urls': list(final_state.get('image_urls') or []),
                        'citations': citations,
                    },
                )
            return final_state
        except Exception as exc:
            update_task_status(task_id, TASK_STATUS_FAILED)
            set_task_result(task_id, 'error', str(exc))
            if is_stream:
                push_sse_event(task_id, SSEEvent.ERROR, {'error': str(exc)})
            raise

    def run_query_graph(
        self,
        task_id: str,
        session_id: str,
        query: str,
        is_stream: bool,
        message_id: str = '',
        history: list[dict[str, Any]] | None = None,
        retrieval_type: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        return self.run_query(
            query=query,
            session_id=session_id,
            task_id=task_id,
            message_id=message_id or None,
            history=history,
            is_stream=is_stream,
            retrieval_type=retrieval_type,
            region=region,
        )

    def get_history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return get_recent_messages(session_id, limit)

    def clear_history(self, session_id: str) -> int:
        return clear_history(session_id)
