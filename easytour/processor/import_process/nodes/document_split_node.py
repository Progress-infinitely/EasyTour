from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.exceptions import StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.markdown_util import MarkdownTableLinearizer


class DocumentSplitNode(BaseNode):
    """把 Markdown 文档整理成适合检索的 chunks。"""

    name = 'document_split_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """先按标题切 section，再对 section 做拆分和合并。"""
        config = self.config
        md_content, file_title, max_content_length, min_content_length = self._validate_state(state, config)

        sections = self._split_by_headings(md_content, file_title)
        final_sections = self._split_and_merge(sections, max_content_length, min_content_length)
        final_chunks = self._assemble_chunks(final_sections)

        self._back_up(final_chunks, state)
        state['chunks'] = final_chunks
        return state

    def _validate_state(self, state: ImportGraphState, config) -> Tuple[str, str, int, int]:
        """读取并校验文档切分需要的输入。"""
        self.log_step('step1', '校验切分参数')

        md_content = state.get('md_content')
        if not md_content or not isinstance(md_content, str):
            raise StateFieldError(node_name=self.name, field_name='md_content', expected_type=str)

        file_title = state.get('file_title')
        if not file_title or not isinstance(file_title, str):
            raise StateFieldError(node_name=self.name, field_name='file_title', expected_type=str)

        md_content = md_content.replace('\r\n', '\n').replace('\r', '\n')

        if config.max_content_length <= 0 or config.min_content_length <= 0:
            raise ValidationError('切分长度参数必须大于 0', self.name)
        if config.max_content_length <= config.min_content_length:
            raise ValidationError('max_content_length 必须大于 min_content_length', self.name)

        return md_content, file_title, config.max_content_length, config.min_content_length

    def _split_by_headings(self, md_content: str, file_title: str) -> List[Dict[str, Any]]:
        """按 Markdown 标题拆成基础 section。"""
        in_fence = False
        body_lines: List[str] = []
        sections: List[Dict[str, Any]] = []
        current_title = ''
        hierarchy = [''] * 7
        current_level = 0

        def _flush() -> None:
            body = '\n'.join(body_lines)
            if not current_title and not body:
                return

            parent_title = ''
            for index in range(current_level - 1, 0, -1):
                if hierarchy[index]:
                    parent_title = hierarchy[index]
                    break

            if not parent_title:
                parent_title = current_title or file_title

            sections.append(
                {
                    'body': body,
                    'title': current_title or file_title,
                    'parent_title': parent_title,
                    'file_title': file_title,
                }
            )

        heading_re = re.compile(r'^\s*(#{1,6})\s+(.+)')
        for md_line in md_content.split('\n'):
            stripped_line = md_line.strip()
            if stripped_line.startswith('```') or stripped_line.startswith('~~~'):
                in_fence = not in_fence

            match = heading_re.match(md_line) if not in_fence else None
            if match:
                _flush()
                current_title = md_line
                current_level = len(match.group(1))
                hierarchy[current_level] = current_title
                for index in range(current_level + 1, 7):
                    hierarchy[index] = ''
                body_lines = []
            else:
                body_lines.append(md_line)

        _flush()
        return sections

    def _split_and_merge(
        self,
        sections: List[Dict[str, Any]],
        max_content_length: int,
        min_content_length: int,
    ) -> List[Dict[str, Any]]:
        """先拆长 section，再合并过短 section。"""
        current_sections: List[Dict[str, Any]] = []
        for section in sections:
            current_sections.extend(self._split_long_section(section, max_content_length))
        return self._merger_short_section(current_sections, min_content_length)

    def _split_long_section(self, section: Dict[str, Any], max_content_length: int) -> List[Dict[str, Any]]:
        """把过长的 section 继续拆分成更小的片段。"""
        body = str(section.get('body') or '')
        title = str(section.get('title') or '')
        parent_title = str(section.get('parent_title') or '')
        file_title = str(section.get('file_title') or '')

        if len(title) > 80:
            title = title[:80]

        if '<table>' in body:
            self.logger.info('detected table in section, run linearizer first')
            body = MarkdownTableLinearizer.process(body)

        title_prefix = f'{title}\n\n'
        total_length = len(title_prefix) + len(body)
        if total_length <= max_content_length:
            return [section]

        body_length = max_content_length - len(title_prefix)
        if body_length <= 0:
            return [section]

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=body_length,
            chunk_overlap=0,
            separators=['\n\n', '\n', '。', '！', '？', '；', '.', '?', '!', ';', ' ', ''],
            keep_separator=True,
        )
        split_sections = text_splitter.split_text(body)
        if len(split_sections) == 1:
            return [section]

        sub_sections: List[Dict[str, Any]] = []
        for index, sub_body in enumerate(split_sections, start=1):
            sub_sections.append(
                {
                    'body': sub_body,
                    'title': f'{title}_{index}',
                    'parent_title': parent_title,
                    'file_title': file_title,
                }
            )
        return sub_sections

    def _merger_short_section(self, current_sections: List[Dict[str, Any]], min_content_length: int) -> List[Dict[str, Any]]:
        """把过短 section 优先和同父标题的后续 section 合并。"""
        if not current_sections:
            return []

        final_sections: List[Dict[str, Any]] = []
        current_section = current_sections[0]

        for next_section in current_sections[1:]:
            same_parent = current_section.get('parent_title') == next_section.get('parent_title')
            current_body = str(current_section.get('body') or '')
            if same_parent and len(current_body) < min_content_length:
                next_body = str(next_section.get('body') or '')
                current_section['body'] = current_body.rstrip() + '\n\n' + next_body.lstrip()
                current_section['title'] = current_section.get('parent_title') or current_section.get('title')
            else:
                final_sections.append(current_section)
                current_section = next_section

        final_sections.append(current_section)
        return final_sections

    def _assemble_chunks(self, final_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把最终 section 组装成统一 chunk 结构。"""
        final_chunks: List[Dict[str, Any]] = []
        for section in final_sections:
            body = str(section.get('body') or '')
            title = str(section.get('title') or '')
            parent_title = str(section.get('parent_title') or '')
            file_title = str(section.get('file_title') or '')

            final_chunks.append(
                {
                    'content': f'{title}\n\n{body}',
                    'title': title,
                    'parent_title': parent_title,
                    'file_title': file_title,
                }
            )
        self.logger.info('generated %s chunks for embedding', len(final_chunks))
        return final_chunks

    def _back_up(self, final_chunks: List[Dict[str, Any]], state: ImportGraphState) -> None:
        """把切分结果备份到任务目录中的 chunks.json。"""
        local_dir = state.get('file_dir', '')
        if not local_dir:
            return
        try:
            os.makedirs(local_dir, exist_ok=True)
            output_path = os.path.join(local_dir, 'chunks.json')
            with open(output_path, 'w', encoding='utf-8') as file_obj:
                json.dump(final_chunks, file_obj, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.logger.warning('failed to backup chunks.json: %s', exc)


__all__ = ['DocumentSplitNode']


if __name__ == '__main__':
    setup_logging()
