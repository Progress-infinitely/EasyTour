"""文件哈希节点：计算 file_hash / document_id，补全 ingest_batch_id / created_at。

此节点是导入链的第一个节点。当 import_file_service 在图外已完成计算并通过 state
注入时，节点直接透传；若 state 中缺少这些字段（如独立测试场景），则从文件路径重新计算。
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.hashing import build_document_id, sha256_file


class FileHashNode(BaseNode):
    name = 'file_hash_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        result: ImportGraphState = {}

        # file_hash 已由 import_file_service 注入时直接透传，无需重算
        file_hash = str(state.get('file_hash') or '').strip()
        if not file_hash:
            file_path = str(state.get('import_file_path') or '').strip()
            if file_path and Path(file_path).exists():
                file_hash = sha256_file(file_path)
                self.logger.info('computed file_hash from path: %s -> %s', file_path, file_hash[:8] + '...')
            else:
                self.logger.warning('file_hash missing and import_file_path not found, using empty hash')
                file_hash = ''

        result['file_hash'] = file_hash
        result['document_id'] = str(state.get('document_id') or '') or (
            build_document_id(file_hash) if file_hash else ''
        )

        # ingest_batch_id：每次上传独立生成，与 document_id 正交（见方案 7.5）
        result['ingest_batch_id'] = str(state.get('ingest_batch_id') or '') or uuid.uuid4().hex

        # created_at：unix 毫秒时间戳
        result['created_at'] = int(state.get('created_at') or 0) or int(time.time() * 1000)

        # source 字段
        file_path_str = str(state.get('import_file_path') or '').strip()
        result['source_uri_internal'] = str(state.get('source_uri_internal') or '') or file_path_str
        file_name = Path(file_path_str).name if file_path_str else str(state.get('file_title') or '')
        result['source_label_display'] = str(state.get('source_label_display') or '') or file_name

        return result
