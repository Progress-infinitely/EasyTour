from __future__ import annotations

import json
from pathlib import Path

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.exceptions import ValidationError
from easytour.processor.import_process.state import ImportGraphState


class EntryNode(BaseNode):
    """导入链入口节点。"""

    name = 'Entry'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """检查输入文件，并写入后续节点需要的基础字段。"""
        # [修改] 清理历史乱码文案，保留原始入口分流逻辑。
        self.log_step('step1', '获取导入文件路径')
        file_dir = state.get('file_dir')
        import_file_path = state.get('import_file_path')

        self.log_step('step2', '校验输入文件')
        if not file_dir or not import_file_path:
            raise ValidationError('file_dir 或 import_file_path 缺失', self.name)

        path = Path(import_file_path).absolute()
        suffix = path.suffix.lower()

        if suffix == '.pdf':
            state['is_pdf_read_enabled'] = True
            state['pdf_path'] = import_file_path
        elif suffix == '.md':
            state['is_md_read_enabled'] = True
            state['md_path'] = import_file_path
        else:
            self.logger.debug('unsupported file type: %s', suffix)
            raise ValidationError(f'不支持的文件类型: {suffix}', self.name)

        state['file_title'] = path.stem
        return state


if __name__ == '__main__':
    setup_logging()
    node = EntryNode()
    demo_state: ImportGraphState = {
        'file_dir': '.',
        'import_file_path': 'demo.pdf',
    }
    print(json.dumps(node.process(demo_state), ensure_ascii=False, indent=2))
