from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from pymilvus import DataType, MilvusClient

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import MilvusError, StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.hashing import build_chunk_hash


@dataclass(frozen=True)
class _ScalarFieldSpec:
    field_name: str
    datatype: DataType
    max_length: int | None = None


_SCALAR_FIELDS: tuple[_ScalarFieldSpec, ...] = (
    _ScalarFieldSpec('content', DataType.VARCHAR, 65535),
    _ScalarFieldSpec('title', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('parent_title', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('file_title', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('item_name', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('primary_item_name', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('document_id', DataType.VARCHAR, 64),
    _ScalarFieldSpec('document_title', DataType.VARCHAR, 1024),
    _ScalarFieldSpec('content_type', DataType.VARCHAR, 64),
    _ScalarFieldSpec('province', DataType.VARCHAR, 128),
    _ScalarFieldSpec('city', DataType.VARCHAR, 128),
    _ScalarFieldSpec('region_path', DataType.VARCHAR, 256),
    _ScalarFieldSpec('ingest_batch_id', DataType.VARCHAR, 64),
    _ScalarFieldSpec('source_uri_internal', DataType.VARCHAR, 2048),
    _ScalarFieldSpec('source_label_display', DataType.VARCHAR, 1024),
)


class ImportMilvusNode(BaseNode):
    name = 'import_milvus_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        chunks = self._validate_chunks(state)
        enriched_chunks = self._enrich_chunks(state, chunks)

        if str(state.get('commit_mode') or 'direct') == 'offline':
            state['pending_chunks_snapshot'] = copy.deepcopy(enriched_chunks)
            state['chunks'] = enriched_chunks
            return state

        dim = len(enriched_chunks[0]['dense_vector'])
        try:
            milvus_client = StorageClients.get_milvus_client()
        except Exception as exc:  # pragma: no cover - depends on runtime infra
            raise MilvusError(message=f'Milvus unavailable: {exc}', node_name=self.name) from exc

        self._create_chunks_collection(milvus_client, dim)
        insert_rows = [self._serialize_row_for_milvus(chunk) for chunk in enriched_chunks]
        inserted = milvus_client.insert(collection_name=self.config.chunks_collection, data=insert_rows)
        for chunk_id, chunk in zip(inserted.get('ids', []), enriched_chunks):
            chunk['chunk_id'] = chunk_id

        state['chunks'] = enriched_chunks
        state['chunks_snapshot'] = copy.deepcopy(enriched_chunks)
        return state

    def _validate_chunks(self, state: ImportGraphState) -> list[dict[str, Any]]:
        chunks = state.get('chunks')
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError('chunks is required', self.name)

        validated: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise ValidationError(message=f'chunks[{index}] must be dict', node_name=self.name)
            if not chunk.get('dense_vector') or chunk.get('sparse_vector') is None:
                raise ValidationError(message=f'chunks[{index}] missing embedding vectors', node_name=self.name)
            validated.append(copy.deepcopy(chunk))

        if not validated:
            raise ValidationError(message='no valid chunks to insert', node_name=self.name)
        return validated

    def _enrich_chunks(self, state: ImportGraphState, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        document_id = str(state.get('document_id') or '')
        file_hash = str(state.get('file_hash') or '')
        ingest_batch_id = str(state.get('ingest_batch_id') or '')
        content_type = str(state.get('doc_content_type') or state.get('override_content_type') or 'attraction')
        document_title = str(state.get('document_title') or state.get('file_title') or '')
        province = str(state.get('doc_province') or '')
        city = str(state.get('doc_city') or '')
        region_path = str(state.get('doc_region_path') or '')
        source_uri_internal = str(state.get('source_uri_internal') or '')
        source_label_display = str(state.get('source_label_display') or state.get('file_title') or '')
        default_item_name = str(state.get('item_name') or '')

        enriched_chunks: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            current = copy.deepcopy(chunk)
            primary_item_name = str(current.get('primary_item_name') or current.get('item_name') or default_item_name)
            current['chunk_index'] = int(current.get('chunk_index') or index)
            current['chunk_hash'] = str(current.get('chunk_hash') or build_chunk_hash(str(current.get('content') or '')))
            current['document_id'] = document_id
            current['file_hash'] = file_hash
            current['ingest_batch_id'] = ingest_batch_id
            current['content_type'] = content_type
            current['document_title'] = document_title
            current['province'] = province
            current['city'] = city
            current['region_path'] = region_path
            current['source_uri_internal'] = source_uri_internal
            current['source_label_display'] = source_label_display
            current['primary_item_name'] = primary_item_name
            current['item_name'] = str(current.get('item_name') or primary_item_name)
            current['entity_names'] = list(current.get('entity_names') or ([primary_item_name] if primary_item_name else []))
            current['suspected_new_entities'] = list(current.get('suspected_new_entities') or [])
            current['tips'] = current.get('tips') or ''
            current['notes'] = current.get('notes') or ''
            enriched_chunks.append(current)
        return enriched_chunks

    def _create_chunks_collection(self, milvus_client: MilvusClient, dim: int) -> None:
        collection_name = self.config.chunks_collection
        if milvus_client.has_collection(collection_name):
            if self.config.rebuild_milvus_collection:
                milvus_client.drop_collection(collection_name=collection_name)
            else:
                return

        schema = milvus_client.create_schema(enable_dynamic_field=True)
        schema.add_field(field_name='chunk_id', datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)
        for spec in _SCALAR_FIELDS:
            params: dict[str, Any] = {'field_name': spec.field_name, 'datatype': spec.datatype}
            if spec.max_length:
                params['max_length'] = spec.max_length
            schema.add_field(**params)

        index_params = milvus_client.prepare_index_params()
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
        milvus_client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)

    def _serialize_row_for_milvus(self, chunk: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for key, value in chunk.items():
            if key == 'chunk_id':
                continue
            if isinstance(value, (list, dict)):
                row[key] = json.dumps(value, ensure_ascii=False)
            else:
                row[key] = value
        return row
