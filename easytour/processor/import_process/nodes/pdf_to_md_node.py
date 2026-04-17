from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Tuple
from urllib import error, request

import requests

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import (
    FileProcessingError,
    PdfConversionError,
    ValidationError,
)
from easytour.processor.import_process.state import ImportGraphState


class PdfToMdNode(BaseNode):
    """调用 MinerU 把 PDF 转成 Markdown。"""

    name = 'pdf_to_md_node'

    _REMOTE_PENDING_STATUSES = {
        '',
        'created',
        'queued',
        'waiting',
        'waiting-file',
        'pending',
        'running',
        'processing',
        'parsing',
        'extracting',
        'converting',
        'convert',
        'uploading',
    }
    _REMOTE_SUCCESS_STATUSES = {'done', 'success', 'finished', 'completed'}
    _REMOTE_FAILED_STATUSES = {'failed', 'error', 'cancelled', 'canceled', 'timeout'}
    _REMOTE_UPLOAD_RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """校验输入，执行远程转换，并把 md_path 写回 state。"""
        import_file_path, file_dir_path = self._validate_state_inputs_path(state)
        self._execute_conversion(import_file_path, file_dir_path)
        md_path = self._get_md_paths(import_file_path, file_dir_path)
        if not Path(md_path).exists():
            raise PdfConversionError(f'未找到预期的 Markdown 文件: {md_path}', self.name)
        state['md_path'] = md_path
        return state

    def _validate_state_inputs_path(self, state: ImportGraphState) -> Tuple[Path, Path]:
        """检查输入路径，并确保工作目录存在。"""
        self.log_step('step1', '校验输入路径')
        import_file_path = state.get('import_file_path', '')
        file_dir = state.get('file_dir', '')
        if not import_file_path:
            raise ValidationError('import_file_path 缺失', self.name)

        import_file_path_obj = Path(import_file_path)
        if not import_file_path_obj.exists():
            raise FileProcessingError(f'input file not found: {import_file_path_obj}', self.name)

        if not file_dir:
            file_dir = str(import_file_path_obj.parent)
        file_dir_path_obj = Path(file_dir)
        file_dir_path_obj.mkdir(parents=True, exist_ok=True)

        self.logger.info('input file path: %s', import_file_path_obj)
        self.logger.info('working directory: %s', file_dir_path_obj)
        return import_file_path_obj, file_dir_path_obj

    def _execute_conversion(self, import_file_path: Path, file_dir_path: Path) -> None:
        """执行 PDF 转 Markdown。"""
        if not self.config.mineru_api_key:
            raise PdfConversionError('MINERU_API_KEY 缺失', self.name)
        self.log_step('step2', '调用 MinerU 官方 API')
        self._execute_remote_mineru(import_file_path, file_dir_path)

    def _execute_remote_mineru(self, import_file_path: Path, file_dir_path: Path) -> None:
        """完整执行一次远程 MinerU 任务。"""
        upload_payload = {
            'enable_formula': True,
            'files': [
                {
                    'name': import_file_path.name,
                    'is_ocr': True,
                    'data_id': import_file_path.stem,
                }
            ],
        }
        if self.config.mineru_model_version:
            upload_payload['model_version'] = self.config.mineru_model_version

        upload_response = self._request_json(
            method='POST',
            url=f"{self.config.mineru_api_base.rstrip('/')}/file-urls/batch",
            payload=upload_payload,
        )
        response_data = self._unwrap_api_data(upload_response, 'request upload url')

        batch_id = str(response_data.get('batch_id', '')).strip()
        file_urls = response_data.get('file_urls') or response_data.get('files') or []
        if not batch_id or not file_urls:
            raise PdfConversionError(
                f'MinerU upload init response missing batch_id or file_urls: {response_data}',
                self.name,
            )

        upload_url = str(file_urls[0]).strip()
        self.logger.info('MinerU remote batch_id=%s', batch_id)

        self._upload_file(upload_url, import_file_path)
        result_data = self._poll_remote_result(batch_id=batch_id, file_name=import_file_path.name)

        zip_url = self._extract_full_zip_url(result_data)
        if not zip_url:
            raise PdfConversionError(
                f'MinerU batch completed but full_zip_url is missing: {result_data}',
                self.name,
            )

        self._download_and_prepare_output(
            zip_url=zip_url,
            import_file_path=import_file_path,
            file_dir_path=file_dir_path,
        )

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """向 MinerU API 发送 JSON 请求。"""
        final_headers = {
            'Authorization': f'Bearer {self.config.mineru_api_key}',
            'Content-Type': 'application/json',
        }
        if headers:
            final_headers.update(headers)

        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

        req = request.Request(url=url, data=body, headers=final_headers, method=method)
        try:
            with request.urlopen(req, timeout=self.config.mineru_timeout_seconds) as resp:
                text = resp.read().decode('utf-8')
        except error.HTTPError as exc:
            response_text = exc.read().decode('utf-8', errors='replace')
            raise PdfConversionError(
                f'MinerU API {method} {url} failed with status {exc.code}: {response_text}',
                self.name,
            ) from exc
        except error.URLError as exc:
            raise PdfConversionError(
                f'MinerU API {method} {url} failed: {exc.reason}',
                self.name,
            ) from exc

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise PdfConversionError(
                f'MinerU API returned invalid JSON: {text}',
                self.name,
            ) from exc

    def _unwrap_api_data(self, payload: dict[str, Any], action: str) -> dict[str, Any]:
        """从 MinerU 标准响应中取出 data 字段。"""
        if payload.get('code') != 0:
            raise PdfConversionError(
                f'MinerU API failed to {action}: {payload}',
                self.name,
            )

        data = payload.get('data')
        if not isinstance(data, dict):
            raise PdfConversionError(
                f'MinerU API returned unexpected data for {action}: {payload}',
                self.name,
            )
        return data

    def _upload_file(self, upload_url: str, file_path: Path) -> None:
        """上传 PDF 到预签名地址，必要时自动重试。"""
        max_attempts = 3
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                with open(file_path, 'rb') as file_obj:
                    response = requests.put(
                        upload_url,
                        data=file_obj,
                        timeout=self.config.mineru_timeout_seconds,
                    )

                if response.status_code not in {200, 201, 204}:
                    response_body = response.text[:500]
                    if response.status_code in self._REMOTE_UPLOAD_RETRY_STATUS_CODES and attempt < max_attempts:
                        self.logger.warning(
                            'MinerU upload retryable status=%s attempt=%s/%s file=%s',
                            response.status_code,
                            attempt,
                            max_attempts,
                            file_path.name,
                        )
                        time.sleep(attempt)
                        continue

                    raise PdfConversionError(
                        f'MinerU upload failed with status {response.status_code}: {response_body}',
                        self.name,
                    )

                self.logger.info(
                    'uploaded pdf to MinerU remote storage: %s attempt=%s/%s',
                    file_path.name,
                    attempt,
                    max_attempts,
                )
                return

            except PdfConversionError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                self.logger.warning(
                    'MinerU upload retry after request error attempt=%s/%s file=%s error=%s',
                    attempt,
                    max_attempts,
                    file_path.name,
                    exc,
                )
                time.sleep(attempt)
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                self.logger.warning(
                    'MinerU upload retry after connection error attempt=%s/%s file=%s error=%s',
                    attempt,
                    max_attempts,
                    file_path.name,
                    exc,
                )
                time.sleep(attempt)

        raise PdfConversionError(f'MinerU upload failed: {last_error}', self.name) from last_error

    def _poll_remote_result(self, *, batch_id: str, file_name: str) -> dict[str, Any]:
        """轮询远程任务直到成功、失败或超时。"""
        poll_url = f"{self.config.mineru_api_base.rstrip('/')}/extract-results/batch/{batch_id}"
        deadline = time.time() + self.config.mineru_timeout_seconds

        while time.time() < deadline:
            payload = self._request_json(method='GET', url=poll_url)
            data = self._unwrap_api_data(payload, 'query batch result')

            result_item = self._select_result_item(data, file_name)
            status = self._extract_status(result_item, data)
            self.logger.info('MinerU remote status=%s batch_id=%s', status or 'unknown', batch_id)

            if self._extract_full_zip_url(result_item):
                return result_item

            if status in self._REMOTE_SUCCESS_STATUSES:
                return result_item

            if status in self._REMOTE_FAILED_STATUSES:
                error_message = (
                    result_item.get('err_msg')
                    or result_item.get('message')
                    or data.get('message')
                    or data.get('err_msg')
                    or 'unknown remote error'
                )
                raise PdfConversionError(
                    f'MinerU remote batch failed: {error_message}',
                    self.name,
                )

            time.sleep(max(1, self.config.mineru_poll_seconds))

        raise PdfConversionError(
            f'MinerU remote batch timed out after {self.config.mineru_timeout_seconds}s',
            self.name,
        )

    def _select_result_item(self, data: dict[str, Any], file_name: str) -> dict[str, Any]:
        """从返回结构里取出当前文件对应的结果。"""
        extract_result = data.get('extract_result')

        if isinstance(extract_result, dict):
            return extract_result

        if isinstance(extract_result, list):
            for item in extract_result:
                if not isinstance(item, dict):
                    continue
                current_name = str(item.get('file_name') or item.get('name') or '').strip()
                if current_name == file_name:
                    return item

            for item in extract_result:
                if isinstance(item, dict):
                    return item

        return data

    @staticmethod
    def _extract_status(result_item: dict[str, Any], data: dict[str, Any]) -> str:
        """兼容不同字段名，提取任务状态。"""
        status = (
            result_item.get('state')
            or result_item.get('status')
            or data.get('state')
            or data.get('status')
            or data.get('batch_status')
            or ''
        )
        return str(status).strip().lower()

    @staticmethod
    def _extract_full_zip_url(result_item: dict[str, Any]) -> str:
        """提取结果压缩包下载地址。"""
        return str(result_item.get('full_zip_url') or result_item.get('zip_url') or '').strip()

    def _download_and_prepare_output(
        self,
        *,
        zip_url: str,
        import_file_path: Path,
        file_dir_path: Path,
    ) -> None:
        """下载结果压缩包，并整理成项目约定的输出目录。"""
        file_name = import_file_path.stem

        document_root = file_dir_path / file_name
        target_root = document_root / 'hybrid_auto'
        temp_extract_root = document_root / '_mineru_api_extract'
        zip_path = document_root / f'{file_name}_mineru_api.zip'

        document_root.mkdir(parents=True, exist_ok=True)
        target_root.mkdir(parents=True, exist_ok=True)

        if temp_extract_root.exists():
            shutil.rmtree(temp_extract_root)
        temp_extract_root.mkdir(parents=True, exist_ok=True)

        self._download_file(zip_url, zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            zip_file.extractall(temp_extract_root)

        source_root, source_md = self._locate_result_root(temp_extract_root)
        self._copy_result_tree(source_root, target_root)

        canonical_md_path = target_root / f'{file_name}.md'
        full_md_path = target_root / 'full.md'

        if source_md.name != 'full.md' and not full_md_path.exists():
            shutil.copy2(source_md, full_md_path)
        elif source_md.name == 'full.md' and source_md.resolve() != full_md_path.resolve():
            shutil.copy2(source_md, full_md_path)

        source_for_canonical = full_md_path if full_md_path.exists() else target_root / source_md.name
        shutil.copy2(source_for_canonical, canonical_md_path)

        if zip_path.exists():
            zip_path.unlink()
        if temp_extract_root.exists():
            shutil.rmtree(temp_extract_root)

        self.logger.info('MinerU remote output ready at %s', canonical_md_path)

    def _download_file(self, url: str, target_path: Path) -> None:
        """下载远程压缩包到本地。"""
        req = request.Request(url=url, method='GET')
        try:
            with request.urlopen(req, timeout=self.config.mineru_timeout_seconds) as resp:
                target_path.write_bytes(resp.read())
        except error.HTTPError as exc:
            response_text = exc.read().decode('utf-8', errors='replace')
            raise PdfConversionError(
                f'MinerU result download failed with status {exc.code}: {response_text}',
                self.name,
            ) from exc
        except error.URLError as exc:
            raise PdfConversionError(
                f'MinerU result download failed: {exc.reason}',
                self.name,
            ) from exc

    def _locate_result_root(self, extract_root: Path) -> Tuple[Path, Path]:
        """在解压目录里定位 Markdown 输出根目录。"""
        md_candidates = list(extract_root.rglob('full.md'))
        if not md_candidates:
            md_candidates = list(extract_root.rglob('*.md'))
        if not md_candidates:
            raise PdfConversionError('MinerU zip does not contain markdown output', self.name)

        source_md = md_candidates[0]
        return source_md.parent, source_md

    def _copy_result_tree(self, source_root: Path, target_root: Path) -> None:
        """复制解析产物到最终目录。"""
        for child in source_root.iterdir():
            destination = target_root / child.name
            if child.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    def _get_md_paths(self, import_file_path: Path, file_dir_path: Path) -> str:
        """根据项目约定推导最终 Markdown 路径。"""
        file_name = import_file_path.stem
        md_path = file_dir_path / file_name / 'hybrid_auto' / f'{file_name}.md'
        return str(md_path)
