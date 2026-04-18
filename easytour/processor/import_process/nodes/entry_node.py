from __future__ import annotations

import json
from pathlib import Path

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.exceptions import ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.title_util import resolve_file_title


class EntryNode(BaseNode):
    """导入链入口节点，负责按文件类型分发后续处理路径。"""

    name = 'entry_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        self.log_step('step1', '获取导入文件路径')
        file_dir = str(state.get('file_dir') or '').strip()
        import_file_path = str(state.get('import_file_path') or '').strip()

        self.log_step('step2', '校验输入文件')
        if not file_dir or not import_file_path:
            raise ValidationError('file_dir 或 import_file_path 缺失', self.name)

        path = Path(import_file_path).absolute()
        suffix = path.suffix.lower()

        next_state: ImportGraphState = {
            'file_dir': file_dir,
            'import_file_path': import_file_path,
            'file_title': resolve_file_title(state, fallback_path=path.name) or path.name,
            'is_pdf_read_enabled': False,
            'is_md_read_enabled': False,
            'pdf_path': '',
            'md_path': '',
        }

        if suffix == '.pdf':
            next_state['is_pdf_read_enabled'] = True
            next_state['pdf_path'] = import_file_path
        elif suffix in {'.md', '.markdown', '.txt'}:
            next_state['is_md_read_enabled'] = True
            next_state['md_path'] = import_file_path
        else:
            raise ValidationError(f'不支持的文件类型: {suffix}', self.name)

        merged_state = dict(state)
        merged_state.update(next_state)
        return merged_state


if __name__ == '__main__':
    setup_logging()
    node = EntryNode()
    demo_state: ImportGraphState = {
        'file_dir': '.',
        'import_file_path': 'demo.pdf',
    }
    print(json.dumps(node.process(demo_state), ensure_ascii=False, indent=2))
