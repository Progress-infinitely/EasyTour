from __future__ import annotations

from typing import Any

from easytour.processor.import_process.exceptions import ValidationError
from easytour.processor.import_process.nodes.bge_embedding_chunks_node import BgeEmbeddingChunksNode
from easytour.processor.import_process.nodes.chunk_level_extract_node import ChunkLevelExtractNode
from easytour.processor.import_process.nodes.doc_level_extract_node import DocLevelExtractNode
from easytour.processor.import_process.nodes.document_split_node import DocumentSplitNode
from easytour.processor.import_process.nodes.entry_node import EntryNode
from easytour.processor.import_process.nodes.file_hash_node import FileHashNode
from easytour.processor.import_process.nodes.md_img_node import MarkDownImageNode
from easytour.processor.import_process.nodes.pdf_to_md_node import PdfToMdNode


class _ImportPipeline:
    """导入主图只负责节点编排，不承载具体业务实现。"""

    def __init__(self) -> None:
        self._entry_node = EntryNode()
        self._file_hash_node = FileHashNode()
        self._pdf_to_md_node = PdfToMdNode()
        self._md_img_node = MarkDownImageNode()
        self._doc_level_extract_node = DocLevelExtractNode()
        self._document_split_node = DocumentSplitNode()
        self._embedding_node = BgeEmbeddingChunksNode()
        self._chunk_level_extract_node = ChunkLevelExtractNode()

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current_state = dict(state)
        current_state = self._apply_node(self._entry_node, current_state)
        current_state = self._apply_node(self._file_hash_node, current_state)

        if current_state.get('is_pdf_read_enabled'):
            current_state = self._apply_node(self._pdf_to_md_node, current_state)

        if not str(current_state.get('md_path') or '').strip():
            raise ValidationError('文件分发完成后缺少 md_path', 'main_graph')

        current_state = self._apply_node(self._md_img_node, current_state)
        current_state = self._apply_node(self._doc_level_extract_node, current_state)
        current_state = self._apply_node(self._document_split_node, current_state)
        current_state = self._apply_node(self._embedding_node, current_state)
        current_state = self._apply_node(self._chunk_level_extract_node, current_state)

        current_state.setdefault('pending_chunks_snapshot', [])
        current_state.setdefault('chunks_snapshot', list(current_state.get('chunks') or []))
        return current_state

    @staticmethod
    def _apply_node(node, current_state: dict[str, Any]) -> dict[str, Any]:
        next_state = node(current_state)
        if not isinstance(next_state, dict):
            raise ValidationError(f'节点返回类型非法: {type(next_state).__name__}', 'main_graph')

        # [修改] 导入节点存在“返回完整 state”和“只返回增量字段”两种风格，这里统一做增量合并。
        merged_state = dict(current_state)
        merged_state.update(next_state)
        return merged_state


def create_import_graph() -> _ImportPipeline:
    return _ImportPipeline()


__all__ = ['create_import_graph']
