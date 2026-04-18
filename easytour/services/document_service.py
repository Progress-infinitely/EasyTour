from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

from easytour.processor.import_process.config import get_config
from easytour.schema.chunk_schema import CHUNK_SCALAR_FIELDS
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.item_name_util import (
    collect_entity_item_names,
    resolve_chunk_item_name,
    resolve_chunk_primary_item_name,
    resolve_document_item_name,
)
from easytour.utils.title_util import (
    resolve_document_title,
    resolve_file_title,
    resolve_source_label_display,
)
from easytour.utils.region_normalizer import RegionInfo, infer_region

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from pymongo import ASCENDING, MongoClient
except Exception:  # pragma: no cover
    ASCENDING = 1
    MongoClient = None


class DocumentServiceError(RuntimeError):
    pass


class DocumentNotFoundError(DocumentServiceError):
    pass


class RequiresReindexError(DocumentServiceError):
    pass


class SnapshotMissingError(DocumentServiceError):
    pass


class DocumentMongoTool:
    def __init__(self) -> None:
        if MongoClient is None:
            raise RuntimeError('pymongo is not installed')

        mongo_url = os.getenv('MONGO_URL', '').strip()
        db_name = os.getenv('MONGO_DB_NAME', '').strip()
        if not mongo_url or not db_name:
            raise ValueError('MONGO_URL or MONGO_DB_NAME is empty')

        self.client = MongoClient(
            mongo_url,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
        )
        self.client.admin.command('ping')
        self.db = self.client[db_name]
        self.documents = self.db['documents']
        self.documents.create_index([('document_id', ASCENDING)], unique=True)


_document_mongo_tool: DocumentMongoTool | None = None
_memory_documents: dict[str, dict[str, Any]] = {}


def _use_mongo() -> bool:
    return bool(os.getenv('MONGO_URL', '').strip() and os.getenv('MONGO_DB_NAME', '').strip() and MongoClient is not None)


def get_document_mongo_tool() -> DocumentMongoTool | None:
    global _document_mongo_tool
    if not _use_mongo():
        return None
    if _document_mongo_tool is None:
        try:
            _document_mongo_tool = DocumentMongoTool()
        except Exception as exc:
            logger.warning('Mongo documents disabled, fallback to memory: %s', exc)
            _document_mongo_tool = None
    return _document_mongo_tool


class DocumentService:
    def __init__(self) -> None:
        self._chunks_collection = get_config().chunks_collection

    def is_mongo_connected(self) -> bool:
        return get_document_mongo_tool() is not None

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        document_id = str(document_id or '').strip()
        if not document_id:
            return None

        mongo_tool = get_document_mongo_tool()
        if mongo_tool is not None:
            document = mongo_tool.documents.find_one({'document_id': document_id}, {'_id': 0})
            return copy.deepcopy(document) if document else None

        document = _memory_documents.get(document_id)
        return copy.deepcopy(document) if document else None

    def upsert_document(self, document: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_for_document_store(copy.deepcopy(document))
        normalized.pop('_id', None)
        document_id = str(normalized.get('document_id') or '').strip()
        if not document_id:
            raise DocumentServiceError('document_id is required')

        mongo_tool = get_document_mongo_tool()
        if mongo_tool is not None:
            mongo_tool.documents.update_one({'document_id': document_id}, {'$set': normalized}, upsert=True)
            stored = mongo_tool.documents.find_one({'document_id': document_id}, {'_id': 0}) or normalized
            return copy.deepcopy(stored)

        _memory_documents[document_id] = normalized
        return copy.deepcopy(normalized)

    def save_import_result(self, state: dict[str, Any]) -> dict[str, Any]:
        document = self._build_document_record(state)
        existing = self.get_document(str(document.get('document_id') or ''))
        if existing is not None:
            self._delete_collection_rows(str(document.get('document_id') or ''))
        # [修改] 插入 Milvus 生成的 chunk_id 需要写回 chunks_snapshot，否则后续按 chunk_id 预览会找不到。
        inserted_snapshot = copy.deepcopy(document.get('chunks_snapshot') or [])
        self._insert_collection_rows(inserted_snapshot)
        document['chunks_snapshot'] = inserted_snapshot
        document['chunk_count'] = len(inserted_snapshot)
        return self.upsert_document(document)

    def apply_metadata_only(self, document_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        current = self.get_document(document_id)
        if current is None:
            raise DocumentNotFoundError(f'document not found: {document_id}')

        new_content_type = str(overrides.get('content_type') or current.get('content_type') or '').strip()
        current_content_type = str(current.get('content_type') or '').strip()
        if new_content_type and current_content_type and new_content_type != current_content_type:
            raise RequiresReindexError('content_type changed, requires reindex')

        chunks_snapshot = copy.deepcopy(current.get('chunks_snapshot') or [])
        if not chunks_snapshot:
            raise SnapshotMissingError('chunks_snapshot is missing, requires reindex')

        region = infer_region(overrides.get('region'), current.get('region_path'))
        updated = copy.deepcopy(current)
        if region.province:
            updated['province'] = region.province
        if region.city:
            updated['city'] = region.city
        if region.region_path:
            updated['region_path'] = region.region_path

        if overrides.get('source_path'):
            updated['source_uri_internal'] = str(overrides['source_path'])
        if overrides.get('source_label_display'):
            updated['source_label_display'] = str(overrides['source_label_display'])
        if overrides.get('document_title'):
            updated['document_title'] = str(overrides['document_title'])

        updated_snapshot = [self._apply_chunk_document_fields(chunk, updated) for chunk in chunks_snapshot]
        self._replace_collection_rows(document_id, updated_snapshot)

        updated['chunks_snapshot'] = updated_snapshot
        updated['chunk_count'] = len(updated_snapshot)
        updated['last_ingest_at'] = _now_ms()
        return self.upsert_document(updated)

    def commit_reindex(self, document_id: str, state: dict[str, Any]) -> dict[str, Any]:
        new_document = self._build_document_record(state)
        new_snapshot = copy.deepcopy(new_document.get('chunks_snapshot') or [])

        current = self.get_document(document_id)
        if current is None:
            self._insert_collection_rows(new_snapshot)
            new_document['chunks_snapshot'] = new_snapshot
            new_document['chunk_count'] = len(new_snapshot)
            return self.upsert_document(new_document)

        staged = copy.deepcopy(current)
        staged['pending_chunks_snapshot'] = copy.deepcopy(new_snapshot)
        staged['rollback_snapshot'] = copy.deepcopy(current.get('chunks_snapshot') or [])
        self.upsert_document(staged)

        rollback_snapshot = copy.deepcopy(staged.get('rollback_snapshot') or [])
        self._delete_collection_rows(document_id)
        try:
            self._insert_collection_rows(new_snapshot)
        except Exception:
            if rollback_snapshot:
                self._delete_collection_rows(document_id)
                self._insert_collection_rows(rollback_snapshot)
            self.upsert_document(current)
            raise

        # [修改] reindex 成功后也要把 Milvus 返回的 chunk_id 同步回文档快照。
        new_document['chunks_snapshot'] = new_snapshot
        new_document['chunk_count'] = len(new_snapshot)
        new_document['rollback_snapshot'] = None
        new_document['pending_chunks_snapshot'] = None
        return self.upsert_document(new_document)

    def list_regions(self) -> list[dict[str, str]]:
        documents = self.list_documents()
        region_paths = sorted({str(item.get('region_path') or '').strip() for item in documents if item.get('region_path')})
        return [{'label': region_path, 'value': region_path} for region_path in region_paths]

    def list_items(self) -> list[dict[str, str]]:
        values: set[str] = set()
        for document in self.list_documents():
            for item_name in collect_entity_item_names(document, field_names=('main_entities',)):
                if item_name:
                    values.add(item_name)
        return [{'label': item_name, 'value': item_name} for item_name in sorted(values)]

    def list_documents(self) -> list[dict[str, Any]]:
        mongo_tool = get_document_mongo_tool()
        if mongo_tool is not None:
            cursor = mongo_tool.documents.find({}, {'_id': 0}).sort('last_ingest_at', -1)
            return [copy.deepcopy(item) for item in cursor]
        return [copy.deepcopy(item) for item in _memory_documents.values()]

    def _build_document_record(self, state: dict[str, Any]) -> dict[str, Any]:
        region = self._resolve_region_from_state(state)
        file_title = resolve_file_title(state)
        document_title = resolve_document_title(state, fallback_file_title=file_title)
        source_label_display = resolve_source_label_display(
            state,
            fallback_file_title=file_title,
        )
        chunks_snapshot = copy.deepcopy(
            state.get('pending_chunks_snapshot')
            or state.get('chunks_snapshot')
            or state.get('chunks')
            or []
        )
        normalized_chunks = [self._apply_chunk_document_fields(chunk, state) for chunk in chunks_snapshot]

        main_entities = state.get('doc_main_entities') or []
        if not main_entities:
            item_name = resolve_document_item_name(state)
            if item_name:
                main_entities = [{'item_name': item_name, 'item_type': state.get('doc_content_type') or 'generic', 'aliases': []}]

        return {
            'document_id': str(state.get('document_id') or ''),
            'file_hash': str(state.get('file_hash') or ''),
            'file_title': file_title,
            'document_title': document_title,
            'content_type': str(state.get('doc_content_type') or state.get('override_content_type') or 'attraction'),
            'province': region.province,
            'city': region.city,
            'region_path': region.region_path,
            'main_entities': copy.deepcopy(main_entities),
            'chunk_count': len(normalized_chunks),
            'last_ingest_batch_id': str(state.get('ingest_batch_id') or ''),
            'last_ingest_at': int(state.get('created_at') or _now_ms()),
            'source_uri_internal': str(state.get('source_uri_internal') or ''),
            'source_label_display': source_label_display,
            'chunks_snapshot': normalized_chunks,
            'rollback_snapshot': None,
            'pending_chunks_snapshot': None,
        }

    def _resolve_region_from_state(self, state: dict[str, Any]) -> RegionInfo:
        if state.get('doc_region_path') or state.get('doc_city') or state.get('doc_province'):
            return RegionInfo(
                raw=str(state.get('override_region') or state.get('doc_region_path') or ''),
                province=str(state.get('doc_province') or ''),
                city=str(state.get('doc_city') or ''),
                region_path=str(state.get('doc_region_path') or ''),
            )
        return infer_region(state.get('override_region'), state.get('file_title'))

    def _apply_chunk_document_fields(self, chunk: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(chunk)
        document_item_name = resolve_document_item_name(source)
        # [修改] ingest_batch_id / source_uri_internal 是文档级元数据，不再向每个 chunk 冗余复制。
        merged.pop('ingest_batch_id', None)
        merged.pop('source_uri_internal', None)
        merged['file_title'] = resolve_file_title(
            {
                'file_title': source.get('file_title') or merged.get('file_title') or '',
            }
        )
        merged['document_id'] = str(source.get('document_id') or merged.get('document_id') or '')
        merged['file_hash'] = str(source.get('file_hash') or merged.get('file_hash') or '')
        merged['content_type'] = str(source.get('doc_content_type') or source.get('content_type') or merged.get('content_type') or 'attraction')
        merged['document_title'] = resolve_document_title(
            {
                'document_title': source.get('document_title') or merged.get('document_title') or '',
                'file_title': merged.get('file_title') or '',
                'item_name': document_item_name,
            },
            fallback_file_title=str(merged.get('file_title') or ''),
        )
        merged['province'] = str(source.get('doc_province') or source.get('province') or merged.get('province') or '')
        merged['city'] = str(source.get('doc_city') or source.get('city') or merged.get('city') or '')
        merged['region_path'] = str(source.get('doc_region_path') or source.get('region_path') or merged.get('region_path') or '')
        merged['source_label_display'] = resolve_source_label_display(
            {
                'source_label_display': source.get('source_label_display') or merged.get('source_label_display') or '',
                'document_title': merged.get('document_title') or '',
                'file_title': merged.get('file_title') or '',
            },
            fallback_file_title=str(merged.get('file_title') or ''),
        )
        merged['item_name'] = resolve_chunk_item_name(merged, default_document_item_name=document_item_name)
        merged['primary_item_name'] = resolve_chunk_primary_item_name(
            merged,
            default_document_item_name=document_item_name,
        )
        merged['entity_names'] = list(merged.get('entity_names') or ([merged['primary_item_name']] if merged['primary_item_name'] else []))
        return merged

    def _delete_collection_rows(self, document_id: str) -> None:
        client = StorageClients.get_milvus_client()
        client.delete(collection_name=self._chunks_collection, filter=f'document_id == "{document_id}"')

    def _insert_collection_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        client = StorageClients.get_milvus_client()
        # [修改] chunks collection 由当前主导入链在保存文档时兜底创建，避免首次写入时缺表。
        self._ensure_chunks_collection(client, rows)
        inserted = client.insert(
            collection_name=self._chunks_collection,
            data=[self._serialize_row_for_milvus(row) for row in rows],
        )
        for chunk_id, row in zip(inserted.get('ids', []), rows):
            row['chunk_id'] = chunk_id

    def _replace_collection_rows(self, document_id: str, rows: list[dict[str, Any]]) -> None:
        self._delete_collection_rows(document_id)
        self._insert_collection_rows(rows)

    def _ensure_chunks_collection(self, client: Any, rows: list[dict[str, Any]]) -> None:
        if client.has_collection(collection_name=self._chunks_collection):
            return
        if not rows:
            return

        from pymilvus import DataType

        dense_vector = rows[0].get('dense_vector') or []
        dim = len(dense_vector) if isinstance(dense_vector, list) else 1024
        dim = max(dim, 8)

        schema = client.create_schema(enable_dynamic_field=True)
        schema.add_field(field_name='chunk_id', datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)

        for spec in CHUNK_SCALAR_FIELDS:
            schema.add_field(field_name=spec.field_name, datatype=DataType.VARCHAR, max_length=spec.max_length)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name='dense_vector',
            index_name='dense_vector_index',
            index_type='AUTOINDEX',
            metric_type='COSINE',
        )
        index_params.add_index(
            field_name='sparse_vector',
            index_name='sparse_vector_index',
            index_type='SPARSE_INVERTED_INDEX',
            metric_type='IP',
        )
        client.create_collection(
            collection_name=self._chunks_collection,
            schema=schema,
            index_params=index_params,
        )

    def _serialize_row_for_milvus(self, row: dict[str, Any]) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for key, value in row.items():
            if key in {'chunk_id', 'ingest_batch_id', 'source_uri_internal'}:
                continue
            # [修改] Milvus 的向量字段必须保持原生 list/dict，不能统一转成 JSON 字符串。
            if key in {'dense_vector', 'sparse_vector'}:
                serialized[key] = self._normalize_for_milvus_vector_field(key, value)
                continue
            if isinstance(value, (list, dict)):
                serialized[key] = json.dumps(value, ensure_ascii=False)
            else:
                serialized[key] = value
        return serialized

    def _normalize_for_document_store(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._normalize_for_document_store(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._normalize_for_document_store(item) for item in value]
        return value

    def _normalize_for_milvus_vector_field(self, field_name: str, value: Any) -> Any:
        if field_name != 'sparse_vector' or not isinstance(value, dict):
            return value
        normalized: dict[int, float] = {}
        for key, item in value.items():
            normalized[int(key)] = float(item)
        return normalized


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
