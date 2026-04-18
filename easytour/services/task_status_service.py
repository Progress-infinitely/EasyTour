from __future__ import annotations

from easytour.utils.task_util import (
    get_done_task_list,
    get_running_task_list,
    get_task_result,
    get_task_status,
)


def build_task_status_payload(task_id: str) -> dict[str, object]:
    return {
        'task_id': task_id,
        'status': get_task_status(task_id),
        'done_list': get_done_task_list(task_id),
        'running_list': get_running_task_list(task_id),
        'answer': str(get_task_result(task_id, 'answer', '') or ''),
        'error': str(get_task_result(task_id, 'error', '') or ''),
        'image_urls': list(get_task_result(task_id, 'image_urls', []) or []),
        'citations': list(get_task_result(task_id, 'citations', []) or []),
        'file_title': str(get_task_result(task_id, 'file_title', '') or ''),
        'document_title': str(get_task_result(task_id, 'document_title', '') or ''),
        'item_name': str(get_task_result(task_id, 'item_name', '') or ''),
        'chunk_count': int(get_task_result(task_id, 'chunk_count', 0) or 0),
        'document_id': str(get_task_result(task_id, 'document_id', '') or ''),
        'region_path': str(get_task_result(task_id, 'region_path', '') or ''),
        'retrieval_type': str(get_task_result(task_id, 'retrieval_type', '') or ''),
        'answer_intent': str(get_task_result(task_id, 'answer_intent', '') or ''),
        'region': dict(get_task_result(task_id, 'region', {}) or {}),
        'doc_main_entities': list(get_task_result(task_id, 'doc_main_entities', []) or []),
    }
