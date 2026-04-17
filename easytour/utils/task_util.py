from __future__ import annotations

from collections import defaultdict
from typing import Any


TASK_STATUS_PENDING = 'pending'
TASK_STATUS_PROCESSING = 'processing'
TASK_STATUS_COMPLETED = 'completed'
TASK_STATUS_FAILED = 'failed'


_tasks_running_list: dict[str, list[str]] = defaultdict(list)
_tasks_done_list: dict[str, list[str]] = defaultdict(list)
_tasks_result: dict[str, dict[str, Any]] = defaultdict(dict)
_tasks_status: dict[str, str] = {}

_NODE_LABELS: dict[str, str] = {
    'upload_file': '保存上传文件',
    'entry_node': '入口检查',
    'pdf_to_md_node': 'PDF 转 Markdown',
    'md_img_node': '图片理解',
    'document_split_node': '文档切分',
    'file_hash_node': '文件哈希',
    'doc_level_extract_node': '文档级抽取',
    'chunk_level_extract_node': 'Chunk 级抽取',
    'item_name_rec_node': '主体识别',
    'item_name_recognition_node': '主体识别',
    'embedding_chunk_node': '向量化',
    'beg_embedding_chunks_node': '向量化',
    'bge_embedding_chunks_node': '向量化',
    'import_milvus_node': '写入 Milvus',
    'metadata_only_apply': '应用元数据纠错',
    'reindex_commit': '提交重建版本',
    'rollback_restore': '回滚旧版本',
    'intent_route_node': '意图识别',
    'alias_resolver_node': '别名归一',
    'item_name_confirm_node': '主体确认',
    'vector_search_node': '向量检索',
    'hyde_search_node': 'HyDE 检索',
    'mcp_search_node': 'Web 搜索',
    'rrf_node': '结果融合',
    'rerank_node': '重排',
    'answer_output_node': '答案生成',
    'structured_answer_node': '结构化答案',
    '__end__': '完成',
}


def _label(node_name: str) -> str:
    return _NODE_LABELS.get(node_name, node_name)


def add_running_task(task_id: str, node_name: str) -> None:
    if not task_id:
        return
    running = _tasks_running_list[task_id]
    if node_name in _tasks_done_list[task_id]:
        _tasks_done_list[task_id].remove(node_name)
    if node_name not in running:
        running.append(node_name)


def add_done_task(task_id: str, node_name: str) -> None:
    if not task_id:
        return
    if node_name in _tasks_running_list[task_id]:
        _tasks_running_list[task_id].remove(node_name)
    done = _tasks_done_list[task_id]
    if node_name not in done:
        done.append(node_name)


def get_running_task_list(task_id: str) -> list[str]:
    return [_label(node_name) for node_name in _tasks_running_list.get(task_id, [])]


def get_done_task_list(task_id: str) -> list[str]:
    return [_label(node_name) for node_name in _tasks_done_list.get(task_id, [])]


def get_task_status(task_id: str) -> str:
    return _tasks_status.get(task_id, '')


def update_task_status(task_id: str, status_name: str) -> None:
    if not task_id:
        return
    _tasks_status[task_id] = status_name


def set_task_result(task_id: str, key: str, value: Any) -> None:
    if not task_id:
        return
    _tasks_result[task_id][key] = value


def get_task_result(task_id: str, key: str, default: Any = None) -> Any:
    return _tasks_result.get(task_id, {}).get(key, default)


def get_task_payload(task_id: str) -> dict[str, Any]:
    return dict(_tasks_result.get(task_id, {}))


def clear_task(task_id: str, *, keep_result: bool = True) -> None:
    _tasks_running_list.pop(task_id, None)
    _tasks_done_list.pop(task_id, None)
    _tasks_status.pop(task_id, None)
    if not keep_result:
        _tasks_result.pop(task_id, None)
