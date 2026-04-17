from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Tuple
from urllib import error, request

import requests

from easytour.processor.import_process.base import BaseNode, setup_logging, T
from easytour.processor.import_process.exceptions import (
    FileProcessingError,
    PdfConversionError,
    ValidationError,
)
from easytour.processor.import_process.state import ImportGraphState


class PdfToMdNode(BaseNode):
    """PDF 杞?Markdown 鑺傜偣銆?
    杩欐槸瀵煎叆閾鹃噷瀵瑰垵瀛﹁€呮渶鍏抽敭鐨勮妭鐐逛箣涓€銆?    浣犲彲浠ュ厛璁颁綇涓€鍙ヨ瘽锛?
    > 鍚庨潰鐨勫鍏ユ祦绋嬩富瑕侀兘鍥寸粫 Markdown 鏂囨湰鏉ュ鐞嗭紝鎵€浠?PDF 蹇呴』鍏堝彉鎴?Markdown銆?
    杩欎釜鑺傜偣鏈韩涓嶈礋璐ｂ€滄湰鍦拌В鏋?PDF 鍐呭鈥濓紝
    鑰屾槸鎶婇珮绠楀姏閮ㄥ垎浜ょ粰杩滅▼ MinerU API銆?
    鏈湴杩欓噷涓昏鍋?4 浠朵簨锛?    1. 鏍￠獙杈撳叆璺緞
    2. 鍙戣捣杩滅▼瑙ｆ瀽浠诲姟
    3. 杞杩滅▼浠诲姟鐘舵€?    4. 涓嬭浇骞舵暣鐞嗚В鏋愮粨鏋滃埌鏈湴鐩綍

    浣犲彲浠ユ妸瀹冪悊瑙ｆ垚锛?    鈥滄湰鍦板鍏ラ摼瀵硅繙绋?PDF 瑙ｆ瀽鏈嶅姟鐨勪竴灞傝皟搴﹀寘瑁呪€濄€?    """

    name = 'pdf_to_md_node'

    # 杩欎簺闆嗗悎鏄负浜嗗吋瀹硅繙绋嬫湇鍔″彲鑳借繑鍥炵殑涓嶅悓鐘舵€佸瓧绗︿覆銆?    # 杩欐牱鐘舵€佸垽鏂氨涓嶄細鍜屾煇涓€涓浐瀹氬瓧娈靛悕銆佸浐瀹氭枃妗堢粦姝汇€?    _REMOTE_PENDING_STATUSES = {
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
        """鑺傜偣鍏ュ彛锛氭牎楠岃緭鍏ャ€佽皟鐢ㄨ繙绋?MinerU銆佹妸 `md_path` 鍐欏洖 state銆?""
        import_file_path, file_dir_path = self._validate_state_inputs_path(state)
        self._execute_conversion(import_file_path, file_dir_path)
        md_path = self._get_md_paths(import_file_path, file_dir_path)
        if not Path(md_path).exists():
            raise PdfConversionError(f'鏈壘鍒伴鏈熺殑 markdown 鏂囦欢: {md_path}', self.name)
        state['md_path'] = md_path
        return state

    def _validate_state_inputs_path(self, state: ImportGraphState) -> Tuple[Path, Path]:
        """鏍￠獙杈撳叆璺緞锛屽苟纭繚宸ヤ綔鐩綍瀛樺湪銆?
        杩欓噷鏈€閲嶈鐨勮緭鍑轰笉鏄€滄姤涓嶆姤閿欌€濓紝
        鑰屾槸鎶婂悗缁祦绋嬬湡姝ｈ鐢ㄧ殑涓や釜 Path 瀵硅薄鍑嗗濂斤細
        - 鍘熷 PDF 璺緞
        - 褰撳墠浠诲姟鐨勫伐浣滅洰褰?        """
        self.log_step('step1', '鏍￠獙杈撳叆璺緞')
        import_file_path = state.get('import_file_path', '')
        file_dir = state.get('file_dir', '')
        if not import_file_path:
            raise ValidationError('import_file_path 缂哄け', self.name)

        import_file_path_obj = Path(import_file_path)
        if not import_file_path_obj.exists():
            raise FileProcessingError(f'Input file not found: {import_file_path_obj}', self.name)
        if not file_dir:
            file_dir = str(import_file_path_obj.parent)
        file_dir_path_obj = Path(file_dir)
        file_dir_path_obj.mkdir(parents=True, exist_ok=True)
        self.logger.info('input file path: %s', import_file_path_obj)
        self.logger.info('working directory: %s', file_dir_path_obj)
        return import_file_path_obj, file_dir_path_obj

    def _execute_conversion(self, import_file_path: Path, file_dir_path: Path) -> None:
        """鎵ц PDF 杞?Markdown銆?
        褰撳墠瀹炵幇鍙蛋杩滅▼ MinerU銆?        涔熷氨鏄锛?        鏈湴涓嶅仛澶嶆潅 PDF 瑙ｆ瀽锛屾湰鍦板彧璐熻矗鎶婁换鍔′氦缁欒繙绔苟鎶婄粨鏋滄嬁鍥炴潵銆?        """
        if not self.config.mineru_api_key:
            raise PdfConversionError('MINERU_API_KEY 缂哄け', self.name)
        self.log_step('step2', '浣跨敤 MinerU 瀹樻柟 API')
        self._execute_remote_mineru(import_file_path, file_dir_path)

    def _execute_remote_mineru(self, import_file_path: Path, file_dir_path: Path) -> None:
        """瀹屾暣鎵ц涓€娆?MinerU 杩滅▼浠诲姟銆?
        鏁翠釜杩滅▼娴佺▼鍙互鎷嗘垚 4 灏忔锛?        1. 鍏堝悜 MinerU 鐢宠涓€涓笂浼犲湴鍧€
        2. 鍐嶆妸 PDF 鐪熸涓婁紶杩囧幓
        3. 鐒跺悗杞浠诲姟鏄惁澶勭悊瀹屾垚
        4. 鏈€鍚庝笅杞借В鏋愪骇鐗╁帇缂╁寘骞舵暣鐞嗗埌鏈湴
        """
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
        """鍙戦€佷竴娆?JSON HTTP 璇锋眰鍒?MinerU API銆?""
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
        """浠?MinerU 鏍囧噯鍝嶅簲閲屽彇鍑?`data` 瀛楁銆?""
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
        """鎶?PDF 鏂囦欢涓婁紶鍒?MinerU 鎻愪緵鐨勯绛惧悕鍦板潃銆?
        杩欓噷棰濆鍋氫簡閲嶈瘯锛?        鍥犱负涓婁紶闃舵缁忓父浼氬彈鍒扮綉缁滄姈鍔ㄣ€佷复鏃?5xx銆侀檺娴佺瓑褰卞搷銆?        """
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

        raise PdfConversionError(
            f'MinerU upload failed: {last_error}',
            self.name,
        ) from last_error

    def _poll_remote_result(self, *, batch_id: str, file_name: str) -> dict[str, Any]:
        """杞 MinerU 浠诲姟鐘舵€侊紝鐩村埌鎴愬姛銆佸け璐ユ垨瓒呮椂銆?""
        poll_url = f"{self.config.mineru_api_base.rstrip('/')}/extract-results/batch/{batch_id}"
        deadline = time.time() + self.config.mineru_timeout_seconds

        while time.time() < deadline:
            payload = self._request_json(method='GET', url=poll_url)
            data = self._unwrap_api_data(payload, 'query batch result')

            result_item = self._select_result_item(data, file_name)
            status = self._extract_status(result_item, data)
            self.logger.info('MinerU remote status=%s batch_id=%s', status or 'unknown', batch_id)

            # 涓€鏃︽嬁鍒板帇缂╁寘鍦板潃锛岃鏄庣粨鏋滃凡缁忓熀鏈噯澶囧ソ浜嗐€?            if self._extract_full_zip_url(result_item):
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
        """浠庤繑鍥炵粨鏋勯噷鎸戝嚭褰撳墠鏂囦欢瀵瑰簲鐨勭粨鏋滃璞°€?""
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
        """鍏煎涓嶅悓杩斿洖瀛楁鍚嶏紝鎻愬彇浠诲姟鐘舵€併€?""
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
        """鎷垮埌瑙ｆ瀽缁撴灉鍘嬬缉鍖呬笅杞藉湴鍧€銆?""
        return str(
            result_item.get('full_zip_url')
            or result_item.get('zip_url')
            or ''
        ).strip()

    def _download_and_prepare_output(
        self,
        *,
        zip_url: str,
        import_file_path: Path,
        file_dir_path: Path,
    ) -> None:
        """涓嬭浇 MinerU 缁撴灉鍘嬬缉鍖咃紝骞舵暣鐞嗘垚椤圭洰闇€瑕佺殑鐩綍缁撴瀯銆?
        杩欎竴姝ュ仛瀹屽悗锛屽綋鍓嶉」鐩細寰楀埌涓€涓粺涓€绾﹀畾鐨?Markdown 璺緞锛?        `浠诲姟鐩綍/鏂囦欢鍚?hybrid_auto/鏂囦欢鍚?md`

        鍚庣画瀵煎叆鑺傜偣灏卞彧闇€瑕佽杩欎釜璺緞锛屼笉闇€瑕佸啀鍏冲績杩滅▼鏈嶅姟鍘熷鍘嬬缉鍖呴暱浠€涔堟牱銆?        """
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
        """涓嬭浇杩滅▼鍘嬬缉鍖呭埌鏈湴銆?""
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
        """鍦ㄨВ鍘嬬洰褰曢噷瀹氫綅 markdown 杈撳嚭鏍圭洰褰曘€?""
        md_candidates = list(extract_root.rglob('full.md'))
        if not md_candidates:
            md_candidates = list(extract_root.rglob('*.md'))
        if not md_candidates:
            raise PdfConversionError('MinerU zip does not contain markdown output', self.name)

        source_md = md_candidates[0]
        return source_md.parent, source_md

    def _copy_result_tree(self, source_root: Path, target_root: Path) -> None:
        """鎶婅В鍘嬪嚭鐨勭粨鏋滄爲澶嶅埗鍒版渶缁堢洰褰曘€?""
        for child in source_root.iterdir():
            destination = target_root / child.name
            if child.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    def _get_md_paths(self, import_file_path: Path, file_dir_path: Path) -> str:
        """鏍规嵁椤圭洰绾﹀畾鎺ㄥ鏈€缁?markdown 璺緞銆?""
        file_name = import_file_path.stem
        md_path = file_dir_path / file_name / 'hybrid_auto' / f'{file_name}.md'
        return str(md_path)

