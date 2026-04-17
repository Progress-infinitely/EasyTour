from __future__ import annotations

from typing import Any, Dict, List

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import EmbeddingError, StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.providers.base import TEXT_TYPE_DOCUMENT
from easytour.utils.providers.provider_factory import get_embedding_provider


class BgeEmbeddingChunksNode(BaseNode):
    """把切分后的 chunk 转成向量。"""

    # [修改] 保留历史节点名，避免影响任务状态映射和已有流程配置。
    name = 'beg_embedding_chunks_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """批量生成 dense/sparse 向量并回写到 state。"""
        self.log_step('step1', '校验 chunks 数据结构')
        validated_chunks = self._validate_state(state)

        self.log_step('step2', '获取 embedding provider')
        try:
            embedding_provider = get_embedding_provider()
        except Exception as exc:
            self.logger.error('failed to create embedding provider: %s', exc)
            raise EmbeddingError(
                message=f'创建 embedding provider 失败: {exc}',
                node_name=self.name,
            ) from exc

        batch_size = self.config.embedding_batch_size
        total = len(validated_chunks)
        final_chunks: list[dict[str, Any]] = []
        for index in range(0, total, batch_size):
            batch_chunks = validated_chunks[index:index + batch_size]
            batch_end = index + len(batch_chunks)
            self.logger.info('embedding batch [%s-%s] / %s', index + 1, batch_end, total)
            current_chunks = self._embed_chunks(batch_chunks, embedding_provider)
            final_chunks.extend(current_chunks)

        state['chunks'] = final_chunks
        return state

    def _validate_state(self, state: ImportGraphState) -> List[Dict[str, Any]]:
        """确保 state['chunks'] 是合法的字典列表。"""
        chunks = state.get('chunks')
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name='chunks', expected_type=list)

        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise ValidationError(
                    message=f'[chunk_{index + 1}] 类型错误，期望 dict，实际是 {type(chunk).__name__}',
                    node_name=self.name,
                )
        return chunks

    def _embed_chunks(self, batch_chunks: List[Dict[str, Any]], embedding_provider) -> List[Dict[str, Any]]:
        """调用远程 embedding 服务处理一批 chunk。"""
        embedding_documents = [f"{chunk.get('item_name', '')}\n{chunk.get('content', '')}" for chunk in batch_chunks]

        try:
            embedding_records = embedding_provider.embed_texts(
                embedding_documents,
                text_type=TEXT_TYPE_DOCUMENT,
                dimension=self.config.embedding_dim,
            )
        except Exception as exc:
            raise EmbeddingError(message=f'chunk 向量化失败: {exc}', node_name=self.name) from exc

        if not embedding_records:
            raise EmbeddingError(message='embedding provider 返回空结果', node_name=self.name)

        for chunk, record in zip(batch_chunks, embedding_records):
            chunk['dense_vector'] = record.dense_vector
            chunk['sparse_vector'] = record.sparse_vector

        return batch_chunks


__all__ = ['BgeEmbeddingChunksNode']
