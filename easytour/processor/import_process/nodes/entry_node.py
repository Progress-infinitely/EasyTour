from __future__ import annotations

import json
from pathlib import Path

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.exceptions import ValidationError
from easytour.processor.import_process.state import ImportGraphState


class EntryNode(BaseNode):
    """瀵煎叆鍥剧殑鍏ュ彛鑺傜偣銆?
    杩欎釜鑺傜偣闈炲父鍍忊€滃畨妫€鍙ｂ€濇垨鈥滃垎娴佸彴鈥濄€?    瀹冧笉浼氬仛澶嶆潅涓氬姟锛屼絾瀹冭礋璐ｅ厛鎶婃渶鍩虹鐨勯棶棰樼‘璁ゆ竻妤氾細

    1. 涓婁紶鏂囦欢璺緞鍒板簳鏈夋病鏈変紶杩涙潵
    2. 杩欎釜鏂囦欢鏄笉鏄」鐩敮鎸佺殑绫诲瀷
    3. 鍚庣画搴旇璧?PDF 鍒嗘敮杩樻槸 Markdown 鍒嗘敮
    4. 杩欎唤鏂囨。鐨勫熀纭€鏍囬鏄粈涔?
    鎵€浠ュ悗闈㈢殑寰堝閫昏緫鑳藉惁椤哄埄鎵ц锛岄鍏堝氨鍙栧喅浜庤繖閲屾湁娌℃湁鎶婂熀纭€淇℃伅鍑嗗濂姐€?    """

    name = 'Entry'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """妫€鏌ヨ緭鍏ユ枃浠讹紝骞舵妸瀵煎叆閾惧悗缁渶瑕佺殑鍩虹淇℃伅鍐欒繘 state銆?""
        self.log_step('Step 1', '鑾峰彇鏂囦欢璺緞')
        file_dir = state.get('file_dir')
        import_file_path = state.get('import_file_path')

        self.log_step('Step 2', '妫€娴嬫枃浠惰矾寰?)
        if not file_dir or not import_file_path:
            raise ValidationError('鏂囦欢鐩綍鎴栬€呮枃浠朵笉瀛樺湪', self.name)

        path = Path(import_file_path).absolute()
        suffix = path.suffix.lower()

        if suffix == '.pdf':
            # PDF 涓嶈兘鐩存帴杩涘叆鍚庣画鏍囧噯澶勭悊娴佺▼锛?            # 蹇呴』鍏堢粡杩?`pdf_to_md_node` 杞垚 Markdown銆?            state['is_pdf_read_enabled'] = True
            state['pdf_path'] = import_file_path
        elif suffix == '.md':
            # Markdown 宸茬粡鏄悗缁鐞嗛摼鍙互鐩存帴娑堣垂鐨勭粺涓€鏂囨湰鏍煎紡銆?            state['is_md_read_enabled'] = True
            state['md_path'] = import_file_path
        else:
            self.logger.debug('鏂囦欢绫诲瀷 %s 涓嶆敮鎸?, suffix)
            raise ValidationError(f'鏂囦欢绫诲瀷 {suffix} 涓嶆敮鎸?)

        # `stem` 灏辨槸涓嶅甫鎵╁睍鍚嶇殑鏂囦欢鍚嶃€?        # 渚嬪 `manual.pdf` 鐨?stem 鏄?`manual`銆?        # 杩欎釜鏍囬鍚庨潰浼氳寰堝鑺傜偣鎷挎潵鐢紝渚嬪锛?        # - 浣滀负榛樿鏂囨。鏍囬
        # - 涓讳綋鍚嶇О璇嗗埆澶辫触鏃朵綔涓哄厹搴曞悕绉?        state['file_title'] = path.stem
        return state


if __name__ == '__main__':
    setup_logging()
    node = EntryNode()
    demo_state: ImportGraphState = {
        'file_dir': '.',
        'import_file_path': 'demo.pdf',
    }
    print(json.dumps(node.process(demo_state), ensure_ascii=False, indent=2))

