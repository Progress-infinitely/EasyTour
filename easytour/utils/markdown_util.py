from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup


class MarkdownTableLinearizer:
    """把复杂表格转换成更适合检索的文本描述。

    为什么需要这个工具？
    - 原始 Markdown / HTML 表格，对向量检索并不友好。
    - 尤其是合并单元格、交叉表头、无表头 KV 表，直接拿去做 chunk 会很难理解。

    所以这里会把表格“线性化”：
    把表格内容改写成更像自然语言条目的文本，
    让后续 embedding 和检索更容易抓住信息点。
    """

    HTML_TABLE_PATTERN = re.compile(r'<table.*?>.*?</table>', re.IGNORECASE | re.DOTALL)
    MD_TABLE_PATTERN = re.compile(
        r'((?:^[ \t]*\|.*\|[ \t]*\n)'
        r'(?:^[ \t]*\|[ \t]*[-:]+[-| :]*\|[ \t]*\n)'
        r'(?:^[ \t]*\|.*\|[ \t]*(?:\n|$))*)',
        re.MULTILINE,
    )

    @classmethod
    def process(cls, content: str) -> str:
        """同时处理 HTML 表格和原生 Markdown 表格。"""
        if not content:
            return content

        if '<table' in content.lower():
            content = cls.HTML_TABLE_PATTERN.sub(cls._replace_html_table, content)

        if '|' in content:
            content = cls.MD_TABLE_PATTERN.sub(cls._replace_md_table, content)

        return content

    @classmethod
    def _replace_html_table(cls, match) -> str:
        """把 HTML 表格替换成线性化文本。"""
        html_content = match.group(0)
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        if not table:
            return html_content

        rows = table.find_all('tr')
        if not rows:
            return html_content

        has_th = len(table.find_all('th')) > 0

        grid = []
        for _ in range(len(rows)):
            grid.append([])

        for row_idx, row in enumerate(rows):
            col_idx = 0
            for cell in row.find_all(['td', 'th']):
                while col_idx < len(grid[row_idx]) and grid[row_idx][col_idx] is not None:
                    col_idx += 1

                rowspan = int(cell.get('rowspan', 1))
                colspan = int(cell.get('colspan', 1))
                text = cell.get_text(separator=' ', strip=True)

                for r in range(row_idx, row_idx + rowspan):
                    while len(grid) <= r:
                        grid.append([])
                    while len(grid[r]) < col_idx + colspan:
                        grid[r].append(None)
                    for c in range(col_idx, col_idx + colspan):
                        grid[r][c] = text
                col_idx += colspan

        return cls._grid_to_text(grid, is_md=False, has_th=has_th)

    @classmethod
    def _replace_md_table(cls, match) -> str:
        """把原生 Markdown 表格替换成线性化文本。"""
        md_text = match.group(0).strip()
        lines = md_text.split('\n')
        grid = []
        for line in lines:
            if re.match(r'^[ \t]*\|[ \t\-|:]+\|[ \t]*$', line):
                continue
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            grid.append(cells)

        # Markdown 表格天然带表头结构。
        return cls._grid_to_text(grid, is_md=True, has_th=False)

    @classmethod
    def _grid_to_text(cls, grid: List[List[str]], is_md: bool, has_th: bool) -> str:
        """把二维表格网格转换成自然语言条目。"""
        if not grid or not grid[0]:
            return ''

        cols_count = max(len(r) for r in grid)
        for r in grid:
            while len(r) < cols_count:
                r.append('')

        is_header_row = False
        if is_md or has_th:
            is_header_row = True
        elif grid[0][0] == '':
            # 左上角为空时，通常意味着这是一种交叉表头。
            is_header_row = True
        elif cols_count > 2:
            is_header_row = True

        res = []

        if not is_header_row and cols_count == 2:
            # 纯 K-V 表格，例如“参数 | 数值”这种结构。
            for r in grid:
                k, v = r[0], r[1]
                if k or v:
                    k_str = k if k else '未知属性'
                    v_str = v if v else '无'
                    res.append(f'- 【{k_str}】：{v_str}。')
        else:
            headers = grid[0]
            for r in grid[1:]:
                if not any(r):
                    continue

                subject = r[0] if r[0] else '未知项目'
                subject_header = headers[0] if headers[0] else ''

                props = []
                for c in range(1, cols_count):
                    head = headers[c] if headers[c] else f'属性{c}'
                    val = r[c] if r[c] else ''

                    if val and val not in ('-', '/', '\\', '无'):
                        props.append(f'{head}为{val}')

                if props:
                    prop_str = '，'.join(props)
                    if subject_header:
                        res.append(f'- 【{subject}】(对应{subject_header})：{prop_str}。')
                    else:
                        res.append(f'- 【{subject}】：{prop_str}。')
                else:
                    if subject != '未知项目':
                        res.append(f'- 【{subject}】')

        return '\n\n' + '\n'.join(res) + '\n\n'
