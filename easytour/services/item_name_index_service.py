from __future__ import annotations

from typing import Any, Mapping

from easytour.processor.import_process.config import get_config
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.item_name_util import collect_entity_item_names, resolve_document_item_name
from easytour.utils.providers.base import TEXT_TYPE_DOCUMENT
from easytour.utils.providers.provider_factory import get_embedding_provider

class ItemNameIndexService:
    """维护 item_name_collection。

    当前查询主链仍依赖 item_name_collection 做主体确认，
    所以这份索引必须由“正在使用的导入主链”负责，而不是继续依赖已经退役的旧节点。
    """

    def __init__(self) -> None:
        self._config = get_config()

    def sync_document_entities(self, document: Mapping[str, Any]) -> None:
        item_names = self._collect_item_names(document)
        if not item_names:
            return

        file_title = str(document.get('file_title') or document.get('document_title') or '').strip()
        if not file_title:
            return

        embedding_provider = get_embedding_provider()
        records = embedding_provider.embed_texts(
            item_names,
            text_type=TEXT_TYPE_DOCUMENT,
            dimension=self._config.embedding_dim,
        )
        if len(records) != len(item_names):
            raise RuntimeError('item name embedding count mismatch')

        client = StorageClients.get_milvus_client()
        self._ensure_collection(client)

        rows: list[dict[str, Any]] = []
        for item_name, record in zip(item_names, records):
            self._delete_existing_row(client, file_title=file_title, item_name=item_name)
            rows.append(
                {
                    'file_title': file_title,
                    'item_name': item_name,
                    'dense_vector': record.dense_vector,
                    'sparse_vector': record.sparse_vector,
                }
            )

        if rows:
            client.insert(collection_name=self._config.item_name_collection, data=rows)

    def _ensure_collection(self, client: Any) -> None:
        if client.has_collection(self._config.item_name_collection):
            return

        from pymilvus import DataType

        schema = client.create_schema()
        schema.add_field(field_name='pk', datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name='file_title', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='item_name', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=self._config.embedding_dim)
        schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)

        index_param = client.prepare_index_params()
        index_param.add_index(
            field_name='dense_vector',
            index_name='dense_vector_index',
            index_type='AUTOINDEX',
            metric_type='COSINE',
        )
        index_param.add_index(
            field_name='sparse_vector',
            index_name='sparse_vector_index',
            index_type='SPARSE_INVERTED_INDEX',
            metric_type='IP',
        )
        client.create_collection(
            collection_name=self._config.item_name_collection,
            schema=schema,
            index_params=index_param,
        )

    def _delete_existing_row(self, client: Any, *, file_title: str, item_name: str) -> None:
        # [修改] 仅删除“同文件名 + 同主体名”的旧索引，避免重导入时重复堆积影响确认分数。
        client.delete(
            collection_name=self._config.item_name_collection,
            filter=(
                f'file_title == {self._quote(file_title)} and '
                f'item_name == {self._quote(item_name)}'
            ),
        )

    @staticmethod
    def _collect_item_names(document: Mapping[str, Any]) -> list[str]:
        item_names = collect_entity_item_names(document, field_names=('main_entities',))
        if item_names:
            return item_names

        fallback_name = resolve_document_item_name(document)
        return [fallback_name] if fallback_name else []

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'


__all__ = ['ItemNameIndexService']
