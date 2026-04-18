from __future__ import annotations

import base64
import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, List, Set, Tuple

from openai import OpenAI

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.config import get_config
from easytour.processor.import_process.exceptions import (
    FileProcessingError,
    ImageProcessingError,
    StateFieldError,
)
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.client.ai_clients import AIClients
from easytour.utils.client.storage_clients import StorageClients


@dataclass
class ImageContext:
    """图片在 Markdown 中的上下文信息。"""

    heading: str
    pre_text: str
    post_text: str


@dataclass
class ImageInfo:
    """单张图片的完整信息。"""

    name: str
    path: str
    context: ImageContext


class MdFileHandler:
    """负责读取 Markdown 文件和备份处理结果。"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def read_md(self, state: ImportGraphState) -> Tuple[str, Path, Path]:
        """读取 Markdown 正文，并推导图片目录。"""
        self.logger.info('[step_1] read markdown and resolve image directory')

        md_path = state.get('md_path', '')
        if not md_path:
            raise StateFieldError(
                node_name='md_img_node',
                field_name='md_path',
                expected_type=str,
            )

        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            raise FileProcessingError(f'invalid markdown path: {md_path}', node_name='md_img_node')

        with open(md_path_obj, 'r', encoding='utf-8') as file_obj:
            md_content = file_obj.read()

        image_dir = md_path_obj.parent / 'images'
        return md_content, md_path_obj, image_dir

    def backup(self, md_path_obj: Path, new_md_content: str) -> str:
        """把处理后的 Markdown 另存为 `_new` 版本。"""
        self.logger.info('[step_5] backup processed markdown')

        new_file_path = md_path_obj.with_name(f'{md_path_obj.stem}_new{md_path_obj.suffix}')
        try:
            with open(new_file_path, 'w', encoding='utf-8') as file_obj:
                file_obj.write(new_md_content)
            self.logger.info('saved processed markdown to: %s', new_file_path)
        except IOError as exc:
            self.logger.error('failed to write markdown backup %s: %s', new_file_path, exc)
            raise ImageProcessingError(f'文件写入失败: {exc}', node_name='md_img_node') from exc
        return str(new_file_path)


class ImageScanner:
    """扫描图片目录，并提取每张图片在 Markdown 中的上下文。"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def scan_img_dir(
        self,
        image_dir: Path,
        md_content: str,
        image_extensions: Set[str],
        context_length: int,
    ) -> List[ImageInfo]:
        """找出真正被 Markdown 引用到的图片。"""
        self.logger.info('[step_2] scan image directory: %s', image_dir)

        image_list: List[ImageInfo] = []
        normalized_extensions = {suffix.lower() for suffix in image_extensions}

        for img_path in Path(image_dir).iterdir():
            if not img_path.is_file():
                continue
            if img_path.suffix.lower() not in normalized_extensions:
                continue

            context = self._find_context(md_content, img_path.name, context_length)
            if context is None:
                self.logger.warning('image is not referenced in markdown: %s', img_path.name)
                continue

            image_list.append(
                ImageInfo(
                    name=img_path.name,
                    path=str(img_path),
                    context=context,
                )
            )

        self.logger.info('found %s referenced images', len(image_list))
        return image_list

    def _find_context(self, md_content: str, img_name: str, max_chars: int = 200) -> ImageContext | None:
        """返回图片第一次出现位置附近的上下文。"""
        pattern = re.compile(r'!\[.*?\]\(.*?' + re.escape(img_name) + r'.*?\)')
        md_lines = md_content.split('\n')

        for line_idx, line in enumerate(md_lines):
            if not pattern.search(line):
                continue

            prev_title, prev_boundary = self._find_heading_above(md_lines, line_idx)
            pre_content = md_lines[prev_boundary + 1 : line_idx]
            img_pre = self._extract_limited_context(pre_content, max_chars, direction='front')

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
        """向上找到最近的 Markdown 标题。"""
        for index in range(from_idx - 1, -1, -1):
            if re.match(r'^#{1,6}\s+', md_lines[index]):
                return md_lines[index], index
        return '', -1

    @staticmethod
    def _find_heading_below(md_lines: List[str], from_idx: int) -> int:
        """向下找到下一个 Markdown 标题。"""
        for index in range(from_idx + 1, len(md_lines)):
            if re.match(r'^#{1,6}\s+', md_lines[index]):
                return index
        return len(md_lines)

    @staticmethod
    def _extract_limited_context(lines: List[str], max_chars: int, direction: str) -> str:
        """按段落抽取限定长度的上下文。"""
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
        for paragraph in paragraphs:
            if total + len(paragraph) > max_chars and selected:
                break
            selected.append(paragraph)
            total += len(paragraph)

        if direction == 'front':
            selected.reverse()

        return '\n\n'.join(selected)


class VLMSummarizer:
    """调用视觉模型生成图片标题摘要。"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def summarize_all(
        self,
        document_title: str,
        image_list: List[ImageInfo],
        vl_model: str,
        requests_per_minute: int,
        concurrency: int = 1,
    ) -> Dict[str, str]:
        """为所有图片批量生成摘要。"""
        self.logger.info('[step_3] generate image summaries')

        summaries: Dict[str, str] = {}
        request_timestamps: Deque[float] = deque()
        # [修改] RPM 限速在多线程下共享，用锁保护时间戳读写，sleep 在锁外进行避免串行化。
        rate_lock = threading.Lock()

        try:
            client = AIClients.get_vlm_client()
        except Exception as exc:
            self.logger.warning('VLM is unavailable, use fallback summaries: %s', exc)
            for img in image_list:
                summaries[img.name] = '图片描述'
            return summaries

        worker_count = max(1, min(concurrency, len(image_list)))

        def task(img: ImageInfo) -> Tuple[str, str]:
            self._acquire_rpm_slot(request_timestamps, rate_lock, requests_per_minute)
            return img.name, self._summarize_one(client, vl_model, document_title, img)

        if worker_count == 1:
            for img in image_list:
                name, summary = task(img)
                summaries[name] = summary
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                for name, summary in pool.map(task, image_list):
                    summaries[name] = summary

        self.logger.info('generated %s image summaries', len(summaries))
        return summaries

    def _summarize_one(self, client: OpenAI, vl_model: str, document_title: str, img: ImageInfo) -> str:
        """为单张图片生成摘要。"""
        parts = [part for part in (img.context.heading, img.context.pre_text, img.context.post_text) if part]
        final_context = '\n'.join(parts) if parts else '暂无可用上下文'

        try:
            with open(img.path, 'rb') as file_obj:
                b64 = base64.b64encode(file_obj.read()).decode('utf-8')
        except Exception:
            return '暂无图片'

        try:
            response = client.chat.completions.create(
                model=vl_model,
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    '任务：为 Markdown 文档中的图片生成一个简短准确的中文标题。\n'
                                    f'文档标题：{document_title}\n'
                                    f'图片上下文：{final_context}\n'
                                    '请结合图片内容和上下文，只输出标题本身，不要解释。'
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
            content = response.choices[0].message.content
            if isinstance(content, str):
                return content.strip() or '图片描述'
            return str(content or '').strip() or '图片描述'
        except Exception as exc:
            self.logger.warning('failed to summarize image %s: %s', img.path, exc)
            return '图片描述'

    def _acquire_rpm_slot(
        self,
        timestamps: Deque[float],
        lock: threading.Lock,
        max_requests: int,
        window: int = 60,
    ) -> None:
        """线程安全地申请一个 RPM 限速令牌。"""
        while True:
            sleep_duration = 0.0
            with lock:
                now = time.time()
                while timestamps and now - timestamps[0] >= window:
                    timestamps.popleft()
                if len(timestamps) < max_requests:
                    timestamps.append(now)
                    return
                sleep_duration = window - (now - timestamps[0])

            if sleep_duration > 0:
                self.logger.info('rate limited, sleep %.2f seconds', sleep_duration)
                time.sleep(sleep_duration)


class ImageUploader:
    """上传图片到 MinIO，并替换 Markdown 中的图片链接。"""

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
        """上传图片并用远端地址替换原始 Markdown 引用。"""
        self.logger.info('[step_4] upload images and rewrite markdown links')

        remote_urls = self._upload_all(document_name, image_list, minio_bucket, minio_base_url)
        return self._replace_in_md(md_content, images_summaries, remote_urls)

    def _upload_all(
        self,
        document_name: str,
        image_list: List[ImageInfo],
        minio_bucket: str,
        minio_base_url: str,
    ) -> Dict[str, str]:
        """批量上传图片。"""
        remote_urls: Dict[str, str] = {}

        try:
            minio_client = StorageClients.get_minio_client()
        except Exception as exc:
            self.logger.warning('MinIO is unavailable, keep local image paths: %s', exc)
            for img in image_list:
                remote_urls[img.name] = img.path
            return remote_urls

        for img in image_list:
            object_name = f'{document_name}/{img.name}'
            try:
                minio_client.fput_object(minio_bucket, object_name, img.path)
                remote_url = f'{minio_base_url}/{minio_bucket}/{object_name}'
                self.logger.info('uploaded image: %s', img.name)
                remote_urls[img.name] = remote_url
            except Exception:
                self.logger.warning('failed to upload %s, keep local path', img.name)
                remote_urls[img.name] = img.path

        self.logger.info('prepared %s image urls', len(remote_urls))
        return remote_urls

    @staticmethod
    def _replace_in_md(md_content: str, summaries: Dict[str, str], remote_urls: Dict[str, str]) -> str:
        """把 Markdown 图片引用替换成带摘要的新链接。"""
        pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')

        def replacer(match: re.Match) -> str:
            original_path = match.group(2).strip()
            file_name_in_md = Path(original_path).name
            for img_name, summary in summaries.items():
                if img_name == file_name_in_md:
                    return f'![{summary}]({remote_urls[img_name]})'
            return match.group(0)

        return pattern.sub(replacer, md_content)


class MarkDownImageNode(BaseNode):
    """Markdown 图片处理总节点。"""

    name = 'md_img_node'

    def __init__(self):
        super().__init__()
        # [修改] 保留原有 helper 拆分结构，只清理乱码文案和异常信息。
        self.file_handler = MdFileHandler(self.logger)
        self.scanner = ImageScanner(self.logger)
        self.summarizer = VLMSummarizer(self.logger)
        self.uploader = ImageUploader(self.logger)

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """执行完整的 Markdown 图片处理流程。"""
        config = get_config()

        md_content, md_path_obj, image_dir = self.file_handler.read_md(state)
        if not image_dir.exists():
            self.logger.warning('no image directory found for markdown: %s', md_path_obj.name)
            state['md_content'] = md_content
            return state

        image_list = self.scanner.scan_img_dir(
            image_dir,
            md_content,
            image_extensions=config.image_extensions,
            context_length=config.img_content_length,
        )
        if not image_list:
            state['md_content'] = md_content
            return state

        summaries = self.summarizer.summarize_all(
            document_title=md_path_obj.stem,
            image_list=image_list,
            vl_model=config.vl_model,
            requests_per_minute=config.requests_per_minute,
            concurrency=config.vlm_concurrency,
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
