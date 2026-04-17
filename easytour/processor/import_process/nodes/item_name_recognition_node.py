from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pymilvus import DataType

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.prompts.upload.import_prompt import ITEM_NAME_SYSTEM_PROMPT, ITEM_NAME_USER_PROMPT_TEMPLATE
from easytour.utils.client.ai_clients import AIClients
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.providers.base import TEXT_TYPE_DOCUMENT
from easytour.utils.providers.provider_factory import get_embedding_provider


class ItemNameRecognitionNode(BaseNode):
    """识别文档主体名称，并写回向量库和 chunk。"""

    name = 'item_name_recognition_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """提取 item_name，生成向量并回填到 state/chunks。"""
        file_title, chunks, item_name_chunks_k, item_name_chunk_size = self._validate_state(state)
        item_name_recognition_context = self._prepare_item_name_recognition_context(
            chunks,
            item_name_chunks_k,
            item_name_chunk_size,
        )
        item_name = self._recognition_name(file_title, item_name_recognition_context)
        dense_vector, sparse_vector = self._embedding_item_name(item_name)
        self._insert_milvus(
            file_title,
            item_name,
            dense_vector,
            sparse_vector,
            self.config.item_name_collection,
        )
        self._fill_item_name(item_name, state, chunks)
        return state

    def _validate_state(self, state: ImportGraphState):
        """校验主体名称识别需要的输入和配置。"""
        file_title = state.get('file_title')
        chunks = state.get('chunks')

        if not file_title or not isinstance(file_title, str):
            raise StateFieldError(node_name=self.name, field_name='file_title', expected_type=str)
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name='chunks', expected_type=list)

        item_name_chunks_k = self.config.item_name_chunk_k
        if not item_name_chunks_k or item_name_chunks_k <= 0:
            raise ValidationError(message='item_name_chunk_k 不能为空且必须大于 0', node_name=self.name)

        item_name_chunk_size = self.config.item_name_chunk_size
        if not item_name_chunk_size or item_name_chunk_size <= 0:
            raise ValidationError(message='item_name_chunk_size 不能为空且必须大于 0', node_name=self.name)

        return file_title, chunks, item_name_chunks_k, item_name_chunk_size

    def _prepare_item_name_recognition_context(self, chunks, item_name_chunks_k, item_name_chunk_size):
        """从前几个 chunk 里截取一段上下文给模型识别主体名称。"""
        total = 0
        final_context: list[str] = []
        for index, chunk in enumerate(chunks[:item_name_chunks_k], start=1):
            if not isinstance(chunk, dict):
                continue
            chunk_content = str(chunk.get('content') or '').strip()
            if not chunk_content:
                continue

            context = f'【切片 {index}】\n{chunk_content}'
            if total + len(context) > item_name_chunk_size:
                break

            total += len(context)
            final_context.append(context)

        return '\n\n'.join(final_context)

    def _recognition_name(self, file_title, item_name_recognition_context):
        """调用 LLM 识别文档主体名称，失败时回退到文件标题。"""
        try:
            llm_client = AIClients.get_llm_client(response_format=False)
            user_prompt = ITEM_NAME_USER_PROMPT_TEMPLATE.format(
                file_title=file_title,
                context=item_name_recognition_context,
            )

            llm_response = llm_client.invoke(
                [
                    SystemMessage(content=ITEM_NAME_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )

            llm_result = str(llm_response.content).strip()
            if not llm_result or llm_result == 'UNKNOWN':
                self.logger.info('LLM 未识别出主体名称，回退到标题: %s', file_title)
                return file_title

            self.logger.info('recognized item_name: %s', llm_result)
            return llm_result
        except Exception as exc:
            self.logger.error('LLM item_name recognition failed, fallback title=%s error=%s', file_title, exc)
            return file_title

    def _embedding_item_name(self, item_name) -> tuple[Optional[list[float]], Optional[dict[int, float]]]:
        """给 item_name 生成 dense/sparse 向量。"""
        try:
            embedding_provider = get_embedding_provider()
            records = embedding_provider.embed_texts(
                [item_name],
                text_type=TEXT_TYPE_DOCUMENT,
                dimension=self.config.embedding_dim,
            )
            if not records:
                return None, None
            return records[0].dense_vector, records[0].sparse_vector
        except Exception as exc:
            self.logger.error('item_name embedding failed: %s', exc)
            return None, None

    def _insert_milvus(self, file_title, item_name, dense_vector, sparse_vector, item_name_collection):
        """把主体名称写入 item_name_collection。"""
        if not dense_vector or sparse_vector is None:
            self.logger.error('item_name vector is incomplete, skip insert. file=%s item=%s', file_title, item_name)
            return

        try:
            milvus_client = StorageClients.get_milvus_client()
        except Exception as exc:
            self.logger.error('failed to create Milvus client: %s', exc)
            return

        try:
            if not milvus_client.has_collection(item_name_collection):
                self._create_item_name_collection(item_name_collection, milvus_client)

            data = {
                'file_title': file_title,
                'item_name': item_name,
                'dense_vector': dense_vector,
                'sparse_vector': sparse_vector,
            }
            result = milvus_client.insert(collection_name=item_name_collection, data=[data])
            self.logger.info('saved item_name into Milvus, id=%s', result['ids'][0])
        except Exception as exc:
            self.logger.error('Milvus item_name insert failed: %s', exc)

    def _create_item_name_collection(self, collection_name, milvus_client):
        """按项目约定创建 item_name 集合。"""
        schema = milvus_client.create_schema()

        schema.add_field(field_name='pk', datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name='file_title', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='item_name', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=self.config.embedding_dim)
        schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)

        index_param = milvus_client.prepare_index_params()
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

        milvus_client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_param,
        )
        self.logger.info('created Milvus collection for item names: %s', collection_name)

    def _fill_item_name(self, item_name, state, chunks):
        """把识别结果写回 chunk 和 state。"""
        for chunk in chunks:
            chunk['item_name'] = item_name
        state['item_name'] = item_name
