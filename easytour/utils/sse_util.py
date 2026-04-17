from __future__ import annotations

import asyncio
import json
import queue
from typing import Any, AsyncGenerator

from fastapi import Request


"""SSE 工具。

SSE = Server-Sent Events。

可以把它理解成：
后端持续往前端“推消息”，而不是前端一直主动轮询。
当前项目里，流式回答和实时进度，就是靠它实现的。

这套工具主要解决三件事：
1. 给每个任务准备一条消息队列。
2. 让后端节点往这个队列里塞事件。
3. 让 FastAPI 把队列内容持续输出成浏览器能识别的 SSE 文本格式。
"""


class SSEEvent:
    """统一维护事件名，避免手写字符串拼错。"""

    READY = 'ready'
    PROGRESS = 'progress'
    DELTA = 'delta'
    FINAL = 'final'
    FINAL_ANSWER = 'final_answer'
    ERROR = 'error'


_task_stream: dict[str, queue.Queue] = {}


def get_sse_queue(task_id: str) -> queue.Queue | None:
    """根据任务 ID 读取对应的消息队列。"""
    return _task_stream.get(task_id)


def create_sse_queue(task_id: str) -> queue.Queue:
    """为一个新任务创建 SSE 队列。"""
    stream_queue = queue.Queue()
    _task_stream[task_id] = stream_queue
    return stream_queue


def remove_sse_queue(task_id: str) -> None:
    """移除任务队列，避免内存泄漏。"""
    _task_stream.pop(task_id, None)


def _sse_pack(event: str, data: dict[str, Any]) -> str:
    """把事件数据打包成浏览器能识别的 SSE 文本格式。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f'event: {event}\ndata: {payload}\n\n'


def push_sse_event(task_id: str, event: str, data: dict[str, Any]) -> None:
    """向任务对应的 SSE 队列推送一条消息。"""
    stream_queue = get_sse_queue(task_id)
    if stream_queue is not None:
        stream_queue.put({'event': event, 'data': data})


async def sse_generator(task_id: str, request: Request) -> AsyncGenerator[str, None]:
    """SSE 输出生成器。

    FastAPI 返回 `StreamingResponse` 时，会不断消费这里 `yield` 出去的文本。
    浏览器收到这些文本后，就能实时更新页面。

    输出流程大致是：
    - 先告诉前端“连接已经就绪”
    - 再不断从队列里取消息并输出
    - 浏览器断开后，清理对应任务的队列
    """
    stream_queue = get_sse_queue(task_id)
    if stream_queue is None:
        return

    loop = asyncio.get_running_loop()
    try:
        yield _sse_pack(SSEEvent.READY, {})
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await loop.run_in_executor(None, stream_queue.get, True, 1.0)
            except queue.Empty:
                # 队列短时间没消息是正常情况，继续等待即可。
                continue
            yield _sse_pack(str(message.get('event') or SSEEvent.PROGRESS), dict(message.get('data') or {}))
    except (ConnectionResetError, BrokenPipeError):
        return
    except asyncio.CancelledError:
        raise
    finally:
        remove_sse_queue(task_id)
