from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import UploadFile

from easytour.core.paths import get_local_base_dir
from easytour.processor.import_process.main_graph import create_import_graph
from easytour.schema.upload_schema import UploadForceMode, UploadOverride, UploadResponse, UploadStatus
from easytour.services.document_service import DocumentService
from easytour.services.item_name_index_service import ItemNameIndexService
from easytour.services.task_service import TaskService
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.hashing import build_document_id, sha256_upload_file
from easytour.utils.item_name_util import resolve_document_item_name
from easytour.utils.title_util import resolve_document_title, resolve_file_title, resolve_source_label_display
from easytour.utils.region_normalizer import infer_region
from easytour.utils.task_util import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_PROCESSING,
    set_task_result,
)

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UploadRunContext:
    task_id: str
    document_id: str
    file_hash: str
    ingest_batch_id: str
    file_dir: str
    import_file_path: str
    file_name: str
    mode: str
    overrides: dict[str, Any]
    existing_document: dict[str, Any] | None


class ImportFileService:
    def __init__(self, task_service: TaskService, document_service: DocumentService):
        self._task_service = task_service
        self._document_service = document_service
        self._item_name_index_service = ItemNameIndexService()
        self._import_app = create_import_graph()

    def get_date_dir(self) -> str:
        return str(Path(get_local_base_dir()) / datetime.now().strftime('%Y%m%d'))

    def prepare_upload(
        self,
        file: UploadFile,
        overrides: UploadOverride | None = None,
        force: UploadForceMode | None = None,
    ) -> tuple[UploadResponse, UploadRunContext | None]:
        override_payload = (overrides or UploadOverride()).model_dump(exclude_none=True)
        file_hash = sha256_upload_file(file.file)
        document_id = build_document_id(file_hash)
        existing_document = self._document_service.get_document(document_id)

        if existing_document and force is None:
            return (
                UploadResponse(
                    message='Document already imported',
                    status=UploadStatus.ALREADY_IMPORTED,
                    document_id=document_id,
                ),
                None,
            )

        if existing_document and force == UploadForceMode.METADATA_ONLY:
            requested_content_type = str(override_payload.get('content_type') or existing_document.get('content_type') or '')
            current_content_type = str(existing_document.get('content_type') or '')
            if requested_content_type and current_content_type and requested_content_type != current_content_type:
                return (
                    UploadResponse(
                        message='content_type changed, requires reindex',
                        status=UploadStatus.REQUIRES_REINDEX,
                        document_id=document_id,
                        error='content_type changed, requires reindex',
                    ),
                    None,
                )

        task_id = uuid.uuid4().hex
        ingest_batch_id = uuid.uuid4().hex
        file_dir = os.path.join(self.get_date_dir(), task_id)
        import_file_path = self._save_upload_file(file, file_dir)
        self._save_upload_file_to_minio(import_file_path, file.filename or os.path.basename(import_file_path))

        mode = 'import'
        if existing_document and force == UploadForceMode.METADATA_ONLY:
            mode = 'metadata_only'
        elif existing_document and force == UploadForceMode.REINDEX:
            mode = 'reindex'

        self._task_service.update_task_status(task_id, TASK_STATUS_PENDING)
        set_task_result(task_id, 'document_id', document_id)

        return (
            UploadResponse(
                message='File upload submitted',
                status=UploadStatus.PROCESSING,
                document_id=document_id,
                task_id=task_id,
            ),
            UploadRunContext(
                task_id=task_id,
                document_id=document_id,
                file_hash=file_hash,
                ingest_batch_id=ingest_batch_id,
                file_dir=file_dir,
                import_file_path=import_file_path,
                file_name=file.filename or os.path.basename(import_file_path),
                mode=mode,
                overrides=override_payload,
                existing_document=existing_document,
            ),
        )

    def run_upload(self, context: UploadRunContext) -> dict[str, Any]:
        try:
            self._task_service.update_task_status(context.task_id, TASK_STATUS_PROCESSING)
            if context.mode == 'metadata_only':
                self._task_service.mark_node_running(context.task_id, 'metadata_only_apply')
                document = self._document_service.apply_metadata_only(context.document_id, context.overrides)
                self._sync_item_name_index(document)
                self._task_service.mark_node_done(context.task_id, 'metadata_only_apply')
                self._record_document_result(context.task_id, document)
                self._task_service.update_task_status(context.task_id, TASK_STATUS_COMPLETED)
                return document

            final_state = self._run_import_graph(context)
            if context.mode == 'reindex':
                self._task_service.mark_node_running(context.task_id, 'reindex_commit')
                document = self._document_service.commit_reindex(context.document_id, final_state)
                self._task_service.mark_node_done(context.task_id, 'reindex_commit')
            else:
                document = self._document_service.save_import_result(final_state)

            self._sync_item_name_index(document)
            self._record_document_result(context.task_id, document, final_state=final_state)
            self._task_service.update_task_status(context.task_id, TASK_STATUS_COMPLETED)
            return final_state
        except Exception as exc:
            self._task_service.update_task_status(context.task_id, TASK_STATUS_FAILED)
            set_task_result(context.task_id, 'error', str(exc))
            raise

    def _run_import_graph(self, context: UploadRunContext) -> dict[str, Any]:
        state = self._build_initial_state(context)
        final_state = self._import_app.invoke(state)
        final_state.setdefault('task_id', context.task_id)
        final_state.setdefault('document_id', context.document_id)
        final_state.setdefault('file_hash', context.file_hash)
        final_state.setdefault('ingest_batch_id', context.ingest_batch_id)
        final_state.setdefault('created_at', state['created_at'])
        final_state.setdefault('doc_content_type', state['doc_content_type'])
        final_state.setdefault('doc_province', state['doc_province'])
        final_state.setdefault('doc_city', state['doc_city'])
        final_state.setdefault('doc_region_path', state['doc_region_path'])
        final_state.setdefault('document_title', state['document_title'])
        final_state.setdefault('source_uri_internal', state['source_uri_internal'])
        final_state.setdefault('source_label_display', state['source_label_display'])
        final_state.setdefault('doc_main_entities', state['doc_main_entities'])
        final_state.setdefault('override_content_type', state['override_content_type'])
        final_state.setdefault('override_region', state['override_region'])
        final_state.setdefault('chunks_snapshot', final_state.get('pending_chunks_snapshot') or final_state.get('chunks') or [])
        return final_state

    def _build_initial_state(self, context: UploadRunContext) -> dict[str, Any]:
        file_title = resolve_file_title({}, fallback_path=context.file_name or context.import_file_path)
        region = infer_region(context.overrides.get('region'), file_title)
        content_type = self._infer_content_type(file_title, context.overrides.get('content_type'))
        item_name = Path(file_title).stem
        created_at = int(datetime.now().timestamp() * 1000)
        source_uri_internal = str(context.overrides.get('source_path') or context.import_file_path)
        document_title = resolve_document_title(
            {
                'document_title': context.overrides.get('document_title') or '',
                'file_title': file_title,
                'item_name': item_name,
            },
            fallback_file_title=file_title,
        )
        source_label_display = resolve_source_label_display(
            {
                'source_label_display': context.overrides.get('source_label_display') or '',
                'document_title': document_title,
                'file_title': file_title,
            },
            fallback_file_title=file_title,
        )
        main_entities = [{'item_name': item_name, 'item_type': content_type or 'generic', 'aliases': []}]

        return {
            'task_id': context.task_id,
            'file_dir': context.file_dir,
            'import_file_path': context.import_file_path,
            'file_title': file_title,
            'file_hash': context.file_hash,
            'document_id': context.document_id,
            'ingest_batch_id': context.ingest_batch_id,
            'created_at': created_at,
            'source_uri_internal': source_uri_internal,
            'source_label_display': source_label_display,
            'override_content_type': str(context.overrides.get('content_type') or ''),
            'override_region': str(context.overrides.get('region') or ''),
            'override_source_path': str(context.overrides.get('source_path') or ''),
            'override_document_title': str(context.overrides.get('document_title') or ''),
            'override_source_label_display': str(context.overrides.get('source_label_display') or ''),
            'doc_content_type': content_type,
            'doc_province': region.province,
            'doc_city': region.city,
            'doc_region_path': region.region_path,
            'doc_main_entities': main_entities,
            'document_title': document_title,
            'commit_mode': 'offline' if context.mode == 'reindex' else 'direct',
        }

    def _record_document_result(
        self,
        task_id: str,
        document: dict[str, Any],
        *,
        final_state: dict[str, Any] | None = None,
    ) -> None:
        set_task_result(task_id, 'document_id', str(document.get('document_id') or ''))
        set_task_result(task_id, 'file_title', str(document.get('file_title') or ''))
        set_task_result(task_id, 'document_title', str(document.get('document_title') or ''))
        set_task_result(task_id, 'item_name', self._pick_document_item_name(document, final_state))
        set_task_result(task_id, 'chunk_count', int(document.get('chunk_count') or 0))
        set_task_result(task_id, 'region_path', str(document.get('region_path') or ''))
        set_task_result(task_id, 'doc_main_entities', list(document.get('main_entities') or []))

    def _pick_document_item_name(self, document: dict[str, Any], final_state: dict[str, Any] | None) -> str:
        if final_state:
            item_name = resolve_document_item_name(final_state)
            if item_name:
                return item_name
        return resolve_document_item_name(document)

    def _save_upload_file(self, file: UploadFile, file_dir: str) -> str:
        os.makedirs(file_dir, exist_ok=True)
        task_id = os.path.basename(file_dir)
        self._task_service.mark_node_running(task_id, 'upload_file')
        file_name = file.filename or f'upload-{uuid.uuid4().hex}.bin'
        import_file_path = os.path.join(file_dir, file_name)
        file.file.seek(0)
        with open(import_file_path, 'wb') as local_file:
            shutil.copyfileobj(file.file, local_file)
        file.file.seek(0)
        self._task_service.mark_node_done(task_id, 'upload_file')
        return import_file_path

    def _save_upload_file_to_minio(self, import_file_path: str, file_name: str) -> bool:
        bucket_name = os.getenv('MINIO_BUCKET_NAME', '').strip()
        if not bucket_name:
            return False
        try:
            minio_client = StorageClients.get_minio_client()
        except Exception as exc:  # pragma: no cover - depends on runtime infra
            logger.warning('MinIO unavailable, skip source upload: %s', exc)
            return False

        object_name = f"origin_files/{datetime.now().strftime('%Y%m%d')}/{file_name}"
        try:
            minio_client.fput_object(bucket_name, object_name, import_file_path)
            return True
        except Exception as exc:  # pragma: no cover - depends on runtime infra
            logger.warning('Upload origin file to MinIO failed: %s', exc)
            return False

    def _infer_content_type(self, file_name: str, override_content_type: str | None) -> str:
        if override_content_type:
            return str(override_content_type)

        lowered = str(file_name or '').lower()
        if any(keyword in lowered for keyword in ('hotel', '酒店', '民宿', '住宿')):
            return 'hotel'
        if any(keyword in lowered for keyword in ('food', '美食', '餐厅', '小吃')):
            return 'food'
        if any(keyword in lowered for keyword in ('transport', '交通', '地铁', '机场', '高铁')):
            return 'transport'
        if any(keyword in lowered for keyword in ('culture', '文化', '博物馆', '非遗', '演出')):
            return 'culture'
        if any(keyword in lowered for keyword in ('route', '路线', '行程', '一日游', '二日游', '攻略')):
            return 'route'
        return 'attraction'

    def _sync_item_name_index(self, document: dict[str, Any]) -> None:
        try:
            self._item_name_index_service.sync_document_entities(document)
        except Exception as exc:
            # [修改] 主体名索引属于增强能力，失败时先告警，不阻断文档主导入链。
            logger.warning('sync item_name_collection failed: %s', exc)
