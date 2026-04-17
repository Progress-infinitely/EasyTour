from __future__ import annotations

"""鏂囨。鍒囧垎鑺傜偣銆?
杩欎釜鑺傜偣鐨勪换鍔℃槸鎶婁竴浠借緝闀跨殑 Markdown 鏂囨湰锛屾暣鐞嗘垚鍚庣画鍙互鍋?embedding 鐨勫涓?chunk銆?
涓轰粈涔堝鍏ラ摼閲屼竴瀹氳鏈夎繖涓€姝ワ紵
- 鍘熷鏂囨。閫氬父澶暱锛屼笉鑳芥暣绡囩洿鎺ユ嬁鍘绘绱€?- 鐢ㄦ埛鎻愰棶鏃讹紝寰€寰€鍙細鍛戒腑鍏朵腑鏌愬嚑涓珷鑺傘€?- 鍒囨垚 chunk 鍚庯紝妫€绱㈢矑搴︽洿缁嗭紝鍛戒腑鏇村噯纭€?
褰撳墠鍒囧垎绛栫暐鍒嗕笁姝ワ細
1. 鍏堟寜 Markdown 鏍囬鍒囨垚鈥滅珷鑺?section鈥濄€?2. 濡傛灉鏌愪釜 section 澶暱锛屽氨缁х画浜屾鍒囧垎銆?3. 濡傛灉鏌愪釜 section 澶煭锛屽氨鍜屽悓鐖舵爣棰樹笅鐨勭浉閭?section 鍚堝苟銆?"""

import json
import os
import re
from typing import Any, Dict, List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.markdown_util import MarkdownTableLinearizer


class DocumentSplitNode(BaseNode):
    name = 'document_split_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """鏂囨。鍒囧垎鐨勬牳蹇冨叆鍙ｃ€?
        鎵ц椤哄簭锛?        1. 璇诲彇骞舵牎楠?state 閲岀殑 Markdown 鍐呭涓庨槇鍊奸厤缃€?        2. 鍏堟寜鏍囬鍒囨垚澶氫釜 section銆?        3. 瀵硅繃闀?section 缁х画鍒囷紝瀵硅繃鐭?section 鍋氬悎骞躲€?        4. 鎶?section 缁勮鎴愭渶缁?chunk 鍒楄〃銆?        5. 澶囦唤鍒版湰鍦?JSON锛屾柟渚胯皟璇曡瀵熴€?        6. 鍐欏洖 `state['chunks']`銆?        """
        config = self.config
        md_content, file_title, max_content_length, min_content_length = self._validate_state(state, config)

        sections: List[Dict[str, Any]] = self._split_by_headings(md_content, file_title)
        final_sections = self._split_and_merge(sections, max_content_length, min_content_length)
        final_chunks = self._assemble_chunks(final_sections)

        self._back_up(final_chunks, state)
        state['chunks'] = final_chunks
        return state

    def _validate_state(self, state: ImportGraphState, config) -> Tuple[str, str, int, int]:
        """璇诲彇骞舵牎楠屽垏鍒嗘墍闇€杈撳叆銆?""
        self.log_step('step1', '鍒囧垎鍓嶅弬鏁版牎楠?)

        md_content = state.get('md_content')
        if md_content:
            # 缁熶竴鎹㈣绗︼紝閬垮厤涓嶅悓绯荤粺浜х敓鐨?`\r\n / \r / \n` 宸紓褰卞搷鍒囧垎銆?            md_content = md_content.replace('\r\n', '\n').replace('\r', '\n')

        file_title = state.get('file_title')

        if config.max_content_length <= 0 or config.min_content_length <= 0 or config.max_content_length <= config.min_content_length:
            raise ValueError('鍒囩墖闀垮害鍙傛暟鏍￠獙澶辫触')

        return md_content, file_title, config.max_content_length, config.min_content_length

    def _split_by_headings(self, md_content: str, file_title: str) -> List[Dict[str, Any]]:
        """鍏堟寜 Markdown 鏍囬鍒囧垎鍑轰竴绾?section銆?
        杩欓噷鐢熸垚鐨?section 杩樹笉鏄渶缁?chunk锛岃€屾槸涓€涓腑闂寸粨鏋勩€?        瀹冮櫎浜嗘鏂囦互澶栵紝杩樹細棰濆淇濈暀锛?        - `title`锛氬綋鍓?section 鏍囬
        - `parent_title`锛氬綋鍓?section 鐨勭埗鏍囬
        - `file_title`锛氭暣浠芥枃妗ｆ爣棰?
        涔嬫墍浠ヤ繚鐣?`parent_title`锛屾槸涓轰簡鍚庨潰鍚堝苟鐭?section 鏃讹紝
        鑳戒紭鍏堟妸鈥滃悓涓€涓埗鏍囬涓嬮潰鐨勫唴瀹光€濆悎鍦ㄤ竴璧凤紝閬垮厤鎶婃棤鍏崇珷鑺傜‖鎷煎埌涓€璧枫€?        """
        in_fence = False
        body_lines: List[str] = []
        sections: List[Dict[str, Any]] = []
        current_title = ''
        hierarchy = [''] * 7
        current_level = 0

        def _flush() -> None:
            """鎶婂綋鍓嶇紦瀛樼殑鏍囬鍜屾鏂囧皝瑁呮垚涓€涓?section銆?""
            body = '\n'.join(body_lines)
            if current_title or body:
                parent_title = ''
                for i in range(current_level - 1, 0, -1):
                    if hierarchy[i]:
                        parent_title = hierarchy[i]
                        break

                if not parent_title:
                    parent_title = current_title if current_title else file_title

                sections.append(
                    {
                        'body': body,
                        'title': current_title if current_title else file_title,
                        'parent_title': parent_title,
                        'file_title': file_title,
                    }
                )

        md_lines = md_content.split('\n')
        heading_re = re.compile(r'^\s*(#{1,6})\s+(.+)')

        for md_line in md_lines:
            # 浠ｇ爜鍧椾腑鐨?`#` 涓嶅簲璇ヨ璇垽鎴愭爣棰橈紝鎵€浠ヨ鍏堣瘑鍒?fenced code block銆?            if md_line.strip().startswith('```') or md_line.strip().startswith('~~~'):
                in_fence = not in_fence

            match = heading_re.match(md_line) if not in_fence else None
            if match:
                _flush()
                current_title = md_line
                level = len(match.group(1))
                current_level = level
                hierarchy[level] = current_title

                # 閬囧埌鏇存祬灞傜殑鏂版爣棰樺悗锛屽師鏉ユ洿娣卞眰鐨勬爣棰樿矾寰勫凡缁忓け鏁堬紝瑕佹竻绌恒€?                for i in range(level + 1, 7):
                    hierarchy[i] = ''
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
        """鍏堝垏鍒嗚繃闀?section锛屽啀鍚堝苟杩囩煭 section銆?""
        current_sections: List[Dict[str, Any]] = []
        for section in sections:
            current_sections.extend(self._split_long_section(section, max_content_length))

        final_sections = self._merger_short_section(current_sections, min_content_length)
        return final_sections

    def _split_long_section(self, section: Dict[str, Any], max_content_length: int) -> List[Dict[str, Any]]:
        """鎶婁竴涓繃闀?section 缁х画鎷嗘垚澶氫釜鏇村皬鐨?section銆?""
        body = section.get('body')
        title = section.get('title')
        parent_title = section.get('parent_title')
        file_title = section.get('file_title')

        if len(title) > 80:
            # 鏍囬鏋佺杩囬暱鏃讹紝鍏堣涓€鍒€锛岄伩鍏嶆爣棰樻湰韬妸 chunk 閰嶉鍗犳帀澶銆?            title = title[:80]

        if '<table>' in body:
            self.logger.info('妫€鏌ュ埌 section 涓湁琛ㄦ牸锛屽厛鍋氱嚎鎬у寲澶勭悊')
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
            separators=['\n\n', '\n', '銆?, '锛?, '锛?, '锛?, '.', '?', '!', ';', ' ', ''],
            keep_separator=True,
        )
        split_sections = text_splitter.split_text(body)
        if len(split_sections) == 1:
            return [section]

        sub_sections: List[Dict[str, Any]] = []
        for index, sub_body in enumerate(split_sections):
            sub_sections.append(
                {
                    'body': sub_body,
                    'title': f'{title}_{index + 1}',
                    'parent_title': parent_title,
                    'file_title': file_title,
                }
            )
        return sub_sections

    def _merger_short_section(self, current_sections: List[Dict[str, Any]], min_content_length: int) -> List[Dict[str, Any]]:
        """鍚堝苟杩囩煭鐨?section銆?
        鍚堝苟鏉′欢锛?        - 褰撳墠 section 鐨勬鏂囬暱搴﹀皬浜庢渶灏忛槇鍊?        - 骞朵笖涓嬩竴涓?section 涓庡畠鍚岀埗鏍囬

        杩欐牱鍋氱殑鍘熷洜锛?        - 澶煭鐨?section 寰€寰€淇℃伅閲忎笉瓒筹紝涓嶉€傚悎鐙珛浣滀负妫€绱㈠崟鍏?        - 浣嗕篃涓嶈兘涔卞苟锛屾墍浠ヨ浼樺厛淇濊瘉鈥滃悓婧愨€?        """
        if not current_sections:
            return []

        current_section = current_sections[0]
        final_sections: List[Dict[str, Any]] = []

        for next_section in current_sections[1:]:
            same_parent = current_section['parent_title'] == next_section['parent_title']
            if same_parent and len(current_section.get('body')) < min_content_length:
                current_section['body'] = current_section.get('body').rstrip() + '\n\n' + next_section.get('body').lstrip()
                # 鍚堝苟鍚庯紝鐢ㄧ埗鏍囬浣滀负鏍囬鏇寸ǔ锛岄伩鍏嶅嚭鐜?`_1/_2` 杩欑杩囩粏纰庢爣棰樼户缁繚鐣欎笅鏉ャ€?                current_section['title'] = current_section['parent_title']
            else:
                final_sections.append(current_section)
                current_section = next_section

        final_sections.append(current_section)
        return final_sections

    def _assemble_chunks(self, final_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """鎶婃渶缁?section 鍒楄〃缁勮鎴愮粺涓€ chunk 缁撴瀯銆?""
        final_chunks: List[Dict[str, Any]] = []
        for section in final_sections:
            body = section.get('body')
            title = section.get('title')
            parent_title = section.get('parent_title')
            file_title = section.get('file_title')

            content = f'{title}\n\n{body}'
            final_chunks.append(
                {
                    'content': content,
                    'title': title,
                    'parent_title': parent_title,
                    'file_title': file_title,
                }
            )
        self.logger.info('鏈€缁堝垏鍒嗗悗杩涘叆 embedding 鑺傜偣鐨?chunk 涓暟: %s', len(final_chunks))
        return final_chunks

    def _back_up(self, final_chunks: List[Dict[str, Any]], state: ImportGraphState):
        """鎶婂垏鍒嗙粨鏋滃浠藉埌浠诲姟鐩綍涓殑 `chunks.json`銆?""
        local_dir = state.get('file_dir', '')
        if not local_dir:
            return
        try:
            os.makedirs(local_dir, exist_ok=True)
            output_path = os.path.join(local_dir, 'chunks.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_chunks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning('鍒囧垎缁撴灉澶囦唤澶辫触: %s', e)


__all__ = ['DocumentSplitNode']


if __name__ == '__main__':
    setup_logging()

