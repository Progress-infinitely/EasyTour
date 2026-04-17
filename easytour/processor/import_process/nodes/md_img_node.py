from __future__ import annotations

"""Markdown 鍥剧墖澶勭悊鑺傜偣銆?

杩欎釜鏂囦欢鐪嬭捣鏉ュ緢闀匡紝浣嗕綘鍙互鍏堟妸瀹冪悊瑙ｆ垚涓€鍙ヨ瘽锛?

> 鎶?Markdown 閲岀殑鍥剧墖锛屼粠鈥滈毦妫€绱㈢殑鍥剧墖寮曠敤鈥濓紝鍙樻垚鈥滄洿閫傚悎妫€绱㈠拰灞曠ず鐨勫甫鎽樿鍥剧墖寮曠敤鈥濄€?

涓轰粈涔堝鍏ラ摼閲岃涓撻棬鍋氳繖涓€姝ワ紵
鍥犱负濡傛灉鍙繚鐣欏師濮?`![](xxx.jpg)` 杩欑鍐欐硶锛?
- 鍚戦噺妫€绱㈢湅涓嶅埌鍥剧墖鍐呭
- 妯″瀷涔熶笉鐭ラ亾杩欏紶鍥惧ぇ姒傚湪璁蹭粈涔?
- 鍓嶇灞曠ず鏃朵篃涓嶄竴瀹氳兘鐩存帴璁块棶鏈湴鍥剧墖璺緞

鎵€浠ヨ繖閲岀殑鎬濊矾鏄細
1. 鍏堟壘鍒?Markdown 閲屽紩鐢ㄤ簡鍝簺鍥剧墖
2. 缁欐瘡寮犲浘鐗囪ˉ涓婁笅鏂囦俊鎭?
3. 璋冭瑙夋ā鍨嬬粰鍥剧墖鐢熸垚涓€鍙ユ憳瑕?
4. 鎶婂浘鐗囦紶鍒?MinIO锛堝鏋滃彲鐢級
5. 鍐嶆妸 Markdown 閲岀殑鍥剧墖寮曠敤鏀规垚鈥滄憳瑕?+ 鏂板湴鍧€鈥?

浣犱笉闇€瑕佷竴娆＄湅鎳傝繖涓枃浠剁殑鎵€鏈夌粏鑺傘€?
鏈€閫傚悎鐨勯槄璇绘柟寮忔槸锛?
- 鍏堢湅鏈€鍚庨潰鐨?`MarkDownImageNode.process()`
- 鏄庣櫧瀹冩妸宸ヤ綔鍒嗙粰浜嗗摢鍑犱釜 helper
- 鍐嶆寜 helper 涓€鍧楀潡寰€鍓嶈
"""

import base64
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, List, Set, Tuple

from openai import OpenAI

from easytour.processor.import_process.base import BaseNode, setup_logging
from easytour.processor.import_process.config import get_config
from easytour.processor.import_process.exceptions import (
    FileProcessingError,
    ImageProcessingError,
    StateFieldError,
)
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.client.ai_clients import AIClients
from easytour.utils.client.storage_clients import StorageClients


# 鈹€鈹€ 1. 鏁版嵁妯″瀷 鈹€鈹€

@dataclass
class ImageContext:
    """鍥剧墖鍦?Markdown 涓殑涓婁笅鏂囦俊鎭€?

    涓€寮犲浘鐗囨湰韬湁鏃朵笉澶熷ソ鐞嗚В锛?
    杩橀渶瑕佺粨鍚堝畠鍓嶅悗鐨勬枃瀛椼€佹墍鍦ㄧ珷鑺傛爣棰橈紝鎵嶈兘鏇村噯纭湴鐢熸垚鎽樿銆?
    """

    heading: str
    pre_text: str
    post_text: str


@dataclass
class ImageInfo:
    """涓€寮犲浘鐗囩殑瀹屾暣淇℃伅銆?""

    name: str
    path: str
    context: ImageContext


# 鈹€鈹€ 2. 鏂囦欢璇诲啓 & 澶囦唤 鈹€鈹€

class MdFileHandler:
    """璐熻矗 Markdown 鏂囦欢鐨勮鍙栥€佽矾寰勬牎楠屽拰澶勭悊鍚庡浠姐€?""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def read_md(self, state: ImportGraphState) -> Tuple[str, Path, Path]:
        """璇诲彇 Markdown 鍐呭锛屽苟鎺ㄥ鍥剧墖鐩綍銆?""
        self.logger.info('銆恠tep_1銆戣鍙?Markdown 鍐呭鍙婃瀯寤哄浘鐗囩洰褰?)

        md_path = state.get('md_path', '')
        if not md_path:
            raise StateFieldError(
                node_name='md_img_node',
                field_name='md_path',
                expected_type=str,
            )

        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            raise FileProcessingError(
                f'md 鏂囦欢璺緞鏃犳晥: {md_path}', node_name='md_img_node'
            )

        with open(md_path_obj, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 褰撳墠椤圭洰榛樿绾﹀畾锛歁arkdown 鍚岀洰褰曚笅鐨?`images/` 鏀惧浘鐗囪祫婧愩€?
        image_dir = md_path_obj.parent / 'images'
        return md_content, md_path_obj, image_dir

    def backup(self, md_path_obj: Path, new_md_content: str) -> str:
        """鎶婂鐞嗗悗鐨?Markdown 鍙﹀瓨涓€浠藉浠芥枃浠躲€?""
        self.logger.info('銆恠tep_5銆戝浠藉鐞嗗悗鐨?Markdown')

        new_file_path = md_path_obj.with_name(f'{md_path_obj.stem}_new{md_path_obj.suffix}')
        try:
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(new_md_content)
            self.logger.info('澶勭悊鍚庣殑鏂囦欢宸插浠借嚦: %s', new_file_path)
        except IOError as e:
            self.logger.error('鍐欏叆鏂版枃浠跺け璐?%s: %s', new_file_path, e)
            raise ImageProcessingError(f'鏂囦欢鍐欏叆澶辫触: {e}', node_name='md_img_node')
        return str(new_file_path)


# 鈹€鈹€ 3. 鍥剧墖鎵弿 & 涓婁笅鏂囨彁鍙?鈹€鈹€

class ImageScanner:
    """鎵弿鍥剧墖鐩綍锛屽苟鎻愬彇姣忓紶鍥剧墖鍦?Markdown 涓殑涓婁笅鏂囦俊鎭€?""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def scan_img_dir(
        self,
        image_dir: Path,
        md_content: str,
        image_extensions: Set[str],
        context_length: int,
    ) -> List[ImageInfo]:
        """鎵弿鐩綍锛屾壘鍑虹湡姝ｈ Markdown 寮曠敤鍒扮殑鏈夋晥鍥剧墖銆?""
        self.logger.info('銆恠tep_2銆戞壂鎻忓浘鐗囩洰褰?%s', image_dir)

        image_list: List[ImageInfo] = []

        for img_path in Path(image_dir).iterdir():
            if not img_path.is_file():
                continue
            if img_path.suffix not in image_extensions:
                continue

            ctx = self._find_context(md_content, img_path.name, context_length)
            if ctx is None:
                # 璇存槑鍥剧墖鐩綍閲岃櫧鐒舵湁杩欎釜鏂囦欢锛屼絾 Markdown 姝ｆ枃骞舵病鏈夌湡姝ｅ紩鐢ㄥ畠銆?
                self.logger.warning('Markdown 鏂囦欢涓湭鎵惧埌鍥剧墖 %s 鐨勫紩鐢?, img_path.name)
                continue

            image_list.append(
                ImageInfo(
                    name=img_path.name,
                    path=str(img_path),
                    context=ctx,
                )
            )

        self.logger.info('鎵惧埌 %s 寮犳湁鏁堝浘鐗?, len(image_list))
        return image_list

    def _find_context(self, md_content: str, img_name: str, max_chars: int = 200) -> ImageContext | None:
        """杩斿洖鍥剧墖鍦?Markdown 涓涓€娆″嚭鐜颁綅缃殑涓婁笅鏂囥€?""
        pattern = re.compile(r'!\[.*?\]\(.*?' + re.escape(img_name) + r'.*?\)')
        md_lines = md_content.split('\n')

        for line_idx, line in enumerate(md_lines):
            if not pattern.search(line):
                continue

            # 鍚戜笂鎵炬渶杩戞爣棰橈紝鍐嶅彇鏍囬鍜屽浘鐗囦箣闂寸殑姝ｆ枃浣滀负涓婃枃銆?
            prev_title, prev_boundary = self._find_heading_above(md_lines, line_idx)
            pre_content = md_lines[prev_boundary + 1 : line_idx]
            img_pre = self._extract_limited_context(pre_content, max_chars, direction='front')

            # 鍚戜笅鎵句笅涓€涓爣棰橈紝鍐嶅彇鍥剧墖鍜屾爣棰樹箣闂寸殑姝ｆ枃浣滀负涓嬫枃銆?
            next_boundary = self._find_heading_below(md_lines, line_idx)
            post_content = md_lines[line_idx + 1 : next_boundary]
            img_post = self._extract_limited_context(post_content, max_chars, direction='end')

            return ImageContext(
                heading=prev_title,
                pre_text=img_pre,
                post_text=img_post,
            )

        return None

    @staticmethod
    def _find_heading_above(md_lines: List[str], from_idx: int) -> Tuple[str, int]:
        """浠庡綋鍓嶄綅缃悜涓婃煡鎵炬渶杩戠殑鏍囬銆?""
        for i in range(from_idx - 1, -1, -1):
            if re.match(r'^#{1,6}\s+', md_lines[i]):
                return md_lines[i], i
        return '', -1

    @staticmethod
    def _find_heading_below(md_lines: List[str], from_idx: int) -> int:
        """浠庡綋鍓嶄綅缃悜涓嬫煡鎵句笅涓€涓爣棰樸€?""
        for i in range(from_idx + 1, len(md_lines)):
            if re.match(r'^#{1,6}\s+', md_lines[i]):
                return i
        return len(md_lines)

    @staticmethod
    def _extract_limited_context(lines: List[str], max_chars: int, direction: str) -> str:
        """鎸夋钀芥彁鍙栨湁闄愪笂涓嬫枃銆?

        杩欓噷涓嶆槸绠€鍗曟寜瀛楃纭埅鏂紝
        鑰屾槸灏介噺鎸夋钀藉彇锛屼繚璇佷笂涓嬫枃璇昏捣鏉ユ洿鑷劧銆?
        """
        current_paragraph: List[str] = []
        paragraphs: List[str] = []

        for line in lines:
            is_blank_line = not line.strip()
            is_other_image = re.match(r'^!\[.*?\]\(.*?\)$', line.strip())

            if is_blank_line or is_other_image:
                if current_paragraph:
                    paragraphs.append('\n'.join(current_paragraph))
                    current_paragraph = []
                continue

            current_paragraph.append(line)

        if current_paragraph:
            paragraphs.append('\n'.join(current_paragraph))

        if direction == 'front':
            paragraphs.reverse()

        total = 0
        selected: List[str] = []
        for para in paragraphs:
            if total + len(para) > max_chars and selected:
                break
            selected.append(para)
            total += len(para)

        if direction == 'front':
            selected.reverse()

        return '\n\n'.join(selected)


# 鈹€鈹€ 4. VLM 鎽樿鐢熸垚 鈹€鈹€

class VLMSummarizer:
    """閫氳繃瑙嗚璇█妯″瀷涓烘瘡寮犲浘鐗囩敓鎴愪腑鏂囨爣棰?鎽樿銆?""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def summarize_all(
        self,
        document_title: str,
        image_list: List[ImageInfo],
        vl_model: str,
        requests_per_minute: int,
    ) -> Dict[str, str]:
        """缁欐墍鏈夊浘鐗囨壒閲忕敓鎴愭憳瑕併€?""
        self.logger.info('銆恠tep_3銆戞彁鍙栧浘鐗囨憳瑕?)

        summaries: Dict[str, str] = {}
        request_timestamps: Deque[float] = deque()

        try:
            client = AIClients.get_vlm_client()
        except Exception as e:
            # 濡傛灉瑙嗚妯″瀷鏆傛椂涓嶅彲鐢紝鏁翠釜瀵煎叆閾句篃涓嶈嚦浜庢姤搴熴€?
            # 杩欓噷鐩存帴闄嶇骇鎴愪竴涓緢绠€鍗曠殑榛樿鎻忚堪銆?
            self.logger.warning('VLM 涓嶅彲鐢紝璺宠繃鍥剧墖鎽樿鐢熸垚: %s', e)
            for img in image_list:
                summaries[img.name] = '鍥剧墖鎻忚堪'
            return summaries

        for img in image_list:
            self._enforce_rate_limit(request_timestamps, requests_per_minute)
            summaries[img.name] = self._summarize_one(client, vl_model, document_title, img)

        self.logger.info('鐢熸垚 %s 寮犲浘鐗囨憳瑕?, len(summaries))
        return summaries

    def _summarize_one(self, client: OpenAI, vl_model: str, document_title: str, img: ImageInfo) -> str:
        """缁欏崟寮犲浘鐗囩敓鎴愭憳瑕併€?""
        parts = [p for p in (img.context.heading, img.context.pre_text, img.context.post_text) if p]
        final_context = '\n'.join(parts) if parts else '鏆傛棤鍙敤涓婁笅鏂?

        try:
            with open(img.path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception:
            return '鏆傛棤鍥剧墖'

        try:
            resp = client.chat.completions.create(
                model=vl_model,
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    f'浠诲姟锛氫负 Markdown 鏂囨。涓殑鍥剧墖鐢熸垚涓€涓畝鐭殑涓枃鏍囬銆俓n'
                                    f'鑳屾櫙淇℃伅锛歕n'
                                    f'  1. 鎵€灞炴枃妗ｆ爣棰橈細"{document_title}"\n'
                                    f'  2. 鍥剧墖涓婁笅鏂囷細{final_context}\n'
                                    f'璇风粨鍚堝浘鐗囧唴瀹瑰拰涓婅堪涓婁笅鏂囦俊鎭紝'
                                    f'鐢ㄤ腑鏂囩畝瑕佹€荤粨杩欏紶鍥剧墖鐨勫唴瀹癸紝'
                                    f'鐢熸垚涓€涓簿鍑嗙殑涓枃鏍囬锛堜笉瑕佸寘鍚浘鐗囦簩瀛楋級銆?
                                ),
                            },
                            {
                                'type': 'image_url',
                                'image_url': {'url': f'data:image/jpeg;base64,{b64}'},
                            },
                        ],
                    }
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            self.logger.warning('鍥剧墖鎽樿鐢熸垚澶辫触 %s: %s', img.path, e)
            return '鍥剧墖鎻忚堪'

    def _enforce_rate_limit(self, timestamps: Deque[float], max_requests: int, window: int = 60):
        """鍋氫竴涓畝鍗曠殑璇锋眰棰戠巼闄愬埗銆?""
        now = time.time()
        while timestamps and now - timestamps[0] >= window:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            sleep_dur = window - (now - timestamps[0])
            if sleep_dur > 0:
                self.logger.info('杈惧埌閫熺巼闄愬埗锛屾殏鍋?%.2f 绉?..', sleep_dur)
                time.sleep(sleep_dur)
            now = time.time()
            while timestamps and now - timestamps[0] >= window:
                timestamps.popleft()

        timestamps.append(now)


# 鈹€鈹€ 5. MinIO 涓婁紶 & Markdown 鍐呭鏇挎崲 鈹€鈹€

class ImageUploader:
    """灏嗘湰鍦板浘鐗囦笂浼犲埌 MinIO锛屽苟鏇存柊 Markdown 涓殑鍥剧墖寮曠敤銆?""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def upload_and_replace(
        self,
        document_name: str,
        md_content: str,
        images_summaries: Dict[str, str],
        image_list: List[ImageInfo],
        minio_bucket: str,
        minio_base_url: str,
    ) -> str:
        """涓婁紶鍥剧墖骞舵妸 Markdown 涓殑鍘熷鍥剧墖璺緞鏇挎崲鎴愭柊鍦板潃銆?""
        self.logger.info('銆恠tep_4銆戜笂浼犲浘鐗囧埌 MinIO 骞舵洿鏂?Markdown')

        remote_urls = self._upload_all(document_name, image_list, minio_bucket, minio_base_url)
        return self._replace_in_md(md_content, images_summaries, remote_urls)

    def _upload_all(
        self,
        document_name: str,
        image_list: List[ImageInfo],
        minio_bucket: str,
        minio_base_url: str,
    ) -> Dict[str, str]:
        """鎵归噺涓婁紶鍥剧墖銆?""
        remote_urls: Dict[str, str] = {}

        try:
            minio_client = StorageClients.get_minio_client()
        except Exception as e:
            # 濡傛灉 MinIO 涓嶅彲鐢紝浠嶇劧淇濈暀鏈湴璺緞锛岃鍚庣画娴佺▼鑳界户缁€?
            self.logger.warning('MinIO 涓嶅彲鐢紝鎵€鏈夊浘鐗囦繚鐣欐湰鍦拌矾寰? %s', e)
            for img in image_list:
                remote_urls[img.name] = img.path
            return remote_urls

        for img in image_list:
            object_name = f'{document_name}/{img.name}'
            try:
                minio_client.fput_object(minio_bucket, object_name, img.path)
                remote_url = f'{minio_base_url}/{minio_bucket}/{object_name}'
                self.logger.info('%s 涓婁紶鎴愬姛', img.name)
                remote_urls[img.name] = remote_url
            except Exception:
                self.logger.warning('%s 涓婁紶澶辫触锛屼繚鐣欐湰鍦拌矾寰?, img.name)
                remote_urls[img.name] = img.path

        self.logger.info('鎴愬姛澶勭悊 %s 寮犲浘鐗囧湴鍧€', len(remote_urls))
        return remote_urls

    @staticmethod
    def _replace_in_md(md_content: str, summaries: Dict[str, str], remote_urls: Dict[str, str]) -> str:
        """鎶?Markdown 涓殑鍥剧墖寮曠敤鏇挎崲鎴愨€滄憳瑕?+ 鏂板湴鍧€鈥濄€?

        鍘熸潵鍙兘鏄細
        `![xxx](images/a.jpg)`

        澶勭悊鍚庝細鍙樻垚绫讳技锛?
        `![浜ゆ崲鏈洪潰鏉跨ず鎰忓浘](http://.../a.jpg)`

        杩欐牱鍚庣画妫€绱㈠拰鍓嶇灞曠ず閮戒細鏇村弸濂姐€?
        """
        pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')

        def replacer(match: re.Match) -> str:
            original_path = match.group(2).strip()
            file_name_in_md = Path(original_path).name
            for img_name, summary in summaries.items():
                if img_name == file_name_in_md:
                    return f'![{summary}]({remote_urls[img_name]})'
            return match.group(0)

        return pattern.sub(replacer, md_content)


# 鈹€鈹€ 6. 涓昏妭鐐?鈹€鈹€

class MarkDownImageNode(BaseNode):
    """Markdown 鍥剧墖澶勭悊鎬昏妭鐐广€?

    杩欎釜绫绘湰韬笉鎵胯浇鎵€鏈変笟鍔＄粏鑺傦紝
    瀹冩洿鍍忎竴涓皬鎬诲婕旓細
    - 鏂囦欢璇诲彇浜ょ粰 `MdFileHandler`
    - 鍥剧墖鎵弿浜ょ粰 `ImageScanner`
    - 鍥剧墖鎽樿浜ょ粰 `VLMSummarizer`
    - 涓婁紶涓庢浛鎹氦缁?`ImageUploader`

    杩欐牱鎷嗗紑鍚庯紝鍗曚釜绫讳笉浼氳繃浜庤噧鑲匡紝
    鍚屾椂姣忎竴鍧楄亴璐ｄ篃鏇存竻鏅般€?
    """

    name = 'md_img_node'

    def __init__(self):
        super().__init__()
        self.file_handler = MdFileHandler(self.logger)
        self.scanner = ImageScanner(self.logger)
        self.summarizer = VLMSummarizer(self.logger)
        self.uploader = ImageUploader(self.logger)

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """鎵ц鏁存潯 Markdown 鍥剧墖澶勭悊娴佺▼銆?""
        config = get_config()

        md_content, md_path_obj, image_dir = self.file_handler.read_md(state)

        if not image_dir.exists():
            # 娌℃湁鍥剧墖鏃讹紝涓嶇畻閿欒锛岀洿鎺ユ妸鍘?Markdown 鍐呭浼犵粰鍚庣画鑺傜偣灏辫銆?
            self.logger.warning('鏂囦欢 %s 鏆傛棤鍥剧墖瑕佸鐞?, md_path_obj.name)
            state['md_content'] = md_content
            return state

        image_list = self.scanner.scan_img_dir(
            image_dir,
            md_content,
            image_extensions=config.image_extensions,
            context_length=config.img_content_length,
        )

        summaries = self.summarizer.summarize_all(
            document_title=md_path_obj.stem,
            image_list=image_list,
            vl_model=config.vl_model,
            requests_per_minute=config.requests_per_minute,
        )

        new_md_content = self.uploader.upload_and_replace(
            document_name=md_path_obj.stem,
            md_content=md_content,
            images_summaries=summaries,
            image_list=image_list,
            minio_bucket=config.minio_bucket,
            minio_base_url=config.get_minio_base_url(),
        )

        self.file_handler.backup(md_path_obj, new_md_content)
        state['md_content'] = new_md_content
        return state

