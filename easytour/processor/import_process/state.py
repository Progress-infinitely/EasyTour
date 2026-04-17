from __future__ import annotations

import copy
from typing import Any, TypedDict


class ImportGraphState(TypedDict, total=False):
    task_id: str

    is_md_read_enabled: bool
    is_pdf_read_enabled: bool

    import_file_path: str
    file_dir: str
    pdf_path: str
    md_path: str

    file_title: str
    md_content: str
    item_name: str

    # [修改] EasyTour 第一阶段新增的稳定文档标识与导入批次信息。
    file_hash: str
    document_id: str
    ingest_batch_id: str
    created_at: int
    source_uri_internal: str
    source_label_display: str

    # [修改] 上传接口 override 字段。
    override_content_type: str
    override_region: str
    override_source_path: str
    override_document_title: str
    override_source_label_display: str

    # [修改] 文档级抽取结果。
    doc_content_type: str
    doc_province: str
    doc_city: str
    doc_region_path: str
    doc_main_entities: list[dict[str, Any]]
    document_title: str

    # [修改] 提交模式与快照字段，供 metadata_only / reindex 使用。
    commit_mode: str
    pending_chunks_snapshot: list[dict[str, Any]]
    chunks_snapshot: list[dict[str, Any]]
    rollback_snapshot: list[dict[str, Any]]
    suspected_new_entities: list[str]

    chunks: list[dict[str, Any]]


GRAPH_DEFAULT_STATE: ImportGraphState = {
    'task_id': '',
    'is_pdf_read_enabled': False,
    'is_md_read_enabled': False,
    'file_dir': '',
    'import_file_path': '',
    'pdf_path': '',
    'md_path': '',
    'file_title': '',
    'md_content': '',
    'chunks': [],
    'item_name': '',
    'file_hash': '',
    'document_id': '',
    'ingest_batch_id': '',
    'created_at': 0,
    'source_uri_internal': '',
    'source_label_display': '',
    'override_content_type': '',
    'override_region': '',
    'override_source_path': '',
    'override_document_title': '',
    'override_source_label_display': '',
    'doc_content_type': '',
    'doc_province': '',
    'doc_city': '',
    'doc_region_path': '',
    'doc_main_entities': [],
    'document_title': '',
    'commit_mode': 'direct',
    'pending_chunks_snapshot': [],
    'chunks_snapshot': [],
    'rollback_snapshot': [],
    'suspected_new_entities': [],
}


def create_default_state(**overrides: Any) -> ImportGraphState:
    state = copy.deepcopy(GRAPH_DEFAULT_STATE)
    state.update(overrides)
    return state


def get_default_state() -> ImportGraphState:
    return copy.deepcopy(GRAPH_DEFAULT_STATE)
