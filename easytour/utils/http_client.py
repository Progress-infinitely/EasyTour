from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, request

from easytour.core.config import get_shared_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpClientConfig:
    """HTTP 客户端配置。

    这些参数控制的是“和远程 API 打交道时的工程行为”，例如：
    - 等多久算超时
    - 最多重试几次
    - 失败后多久再重试
    - 同时允许多少请求并发发出去

    对新手来说，可以先把这组参数理解成：
    “网络调用时的保险丝和缓冲垫”。
    它们不是业务逻辑本身，但会直接影响系统稳定性。
    """

    timeout_seconds: float = 30.0
    max_retries: int = 3
    base_backoff_seconds: float = 0.6
    max_backoff_seconds: float = 8.0
    max_concurrency: int = 4

    @classmethod
    def from_shared_config(cls) -> 'HttpClientConfig':
        config = get_shared_config()
        return cls(
            timeout_seconds=float(config.http_timeout_seconds),
            max_retries=int(config.http_max_retries),
            base_backoff_seconds=float(config.http_retry_base_seconds),
            max_backoff_seconds=float(config.http_retry_max_seconds),
            max_concurrency=int(config.http_max_concurrency),
        )


class HttpClientError(RuntimeError):
    """统一的 HTTP 调用异常。

    这个异常类型的价值在于：
    上层不用分别处理 `HTTPError / URLError / JSONDecodeError`，
    而是统一处理成一个更清晰的“远程调用失败”概念。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        response_body: str = '',
    ):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.response_body = response_body


class JsonHttpClient:
    """通用 JSON HTTP 客户端。

    这个类是 provider 层的基础设施。
    embedding / rerank 这类远程 API 调用，最终都会落到这里。

    为什么要单独抽一层 `JsonHttpClient`，而不是每个 provider 自己写请求代码？
    因为这些东西几乎每次远程调用都要重复做：
    - 发 POST 请求
    - 传 JSON body
    - 解析 JSON 响应
    - 失败时重试
    - 控制并发

    所以把这些共性抽出来后：
    - provider 文件更短
    - 职责更清晰
    - 出问题时也更容易集中修
    """

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, config: HttpClientConfig | None = None):
        self.config = config or HttpClientConfig.from_shared_config()
        self._semaphore = threading.BoundedSemaphore(self.config.max_concurrency)

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """发送 JSON POST 请求，并返回解析后的 JSON 结果。

        参数说明：
        - `url`：远程 API 地址
        - `payload`：要发送的 JSON 数据
        - `headers`：额外请求头，例如认证信息

        返回值：
        - 解析后的 JSON 字典
        """
        request_id = str(uuid.uuid4())
        final_headers = {
            'Content-Type': 'application/json',
            'X-Request-Id': request_id,
        }
        if headers:
            final_headers.update(dict(headers))

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        attempt = 0
        last_error: HttpClientError | None = None

        while attempt <= self.config.max_retries:
            attempt += 1
            try:
                # 用信号量限制并发，避免同一时间把太多请求压到远端服务上。
                with self._semaphore:
                    req = request.Request(url=url, data=body, headers=final_headers, method='POST')
                    with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                        text = response.read().decode('utf-8')
                        response_request_id = response.headers.get('X-Request-Id') or request_id
                        logger.info(
                            'HTTP POST success url=%s request_id=%s attempt=%s',
                            url,
                            response_request_id,
                            attempt,
                        )
                        return self._load_json(text, request_id=response_request_id)
            except error.HTTPError as exc:
                response_text = exc.read().decode('utf-8', errors='replace')
                request_id_from_error = exc.headers.get('X-Request-Id') or request_id
                last_error = HttpClientError(
                    f'HTTP request failed with status {exc.code}',
                    status_code=exc.code,
                    request_id=request_id_from_error,
                    response_body=response_text,
                )

                # 不是所有错误都值得重试。
                # 例如 400 这种请求本身有问题，重试通常没有意义；
                # 但 429 / 5xx 常常是临时问题，可以再试一次。
                if exc.code not in self._RETRYABLE_STATUS_CODES or attempt > self.config.max_retries:
                    raise last_error
                self._sleep_before_retry(attempt, url, request_id_from_error, exc.code)
            except error.URLError as exc:
                last_error = HttpClientError(
                    f'HTTP request failed: {exc.reason}',
                    request_id=request_id,
                )
                if attempt > self.config.max_retries:
                    raise last_error
                self._sleep_before_retry(attempt, url, request_id, None)

        if last_error is not None:
            raise last_error
        raise HttpClientError('HTTP request failed without a captured exception', request_id=request_id)

    def _load_json(self, text: str, *, request_id: str) -> dict[str, Any]:
        """把响应文本解析成 JSON。"""
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HttpClientError(
                f'HTTP response is not valid JSON: {exc}',
                request_id=request_id,
                response_body=text,
            ) from exc

    def _sleep_before_retry(
        self,
        attempt: int,
        url: str,
        request_id: str,
        status_code: int | None,
    ) -> None:
        """按指数退避策略等待后重试。

        “指数退避”可以先这样理解：
        每失败一次，就比上一次多等一会儿，
        这样能减少“服务刚出问题时，我们反而更疯狂地打它”的情况。

        这里还加了一点随机抖动（jitter），
        避免多个请求在同一时刻整齐地一起重试。
        """
        backoff = min(
            self.config.max_backoff_seconds,
            self.config.base_backoff_seconds * (2 ** (attempt - 1)),
        )
        jitter = random.uniform(0.0, backoff * 0.2)
        sleep_seconds = backoff + jitter
        logger.warning(
            'HTTP POST retry url=%s request_id=%s attempt=%s status=%s sleep=%.2fs',
            url,
            request_id,
            attempt,
            status_code,
            sleep_seconds,
        )
        time.sleep(sleep_seconds)
