from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, TypeVar

from easytour.processor.query_process.config import QueryConfig, get_config
from easytour.processor.query_process.exceptions import QueryProcessError
from easytour.utils.sse_util import SSEEvent, push_sse_event
from easytour.utils.task_util import (
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    add_done_task,
    add_running_task,
    get_done_task_list,
    get_running_task_list,
    get_task_status,
    update_task_status,
)

T = TypeVar('T')


class BaseNode(ABC):
    name: str = 'base_node'

    def __init__(self, config: Optional[QueryConfig] = None):
        self.config = config or get_config()
        self.logger = logging.getLogger(f'query.{self.name}')

    def __call__(self, state: T) -> T:
        task_id = self._get_task_id(state)
        is_stream = self._is_stream(state)
        try:
            if task_id:
                update_task_status(task_id, TASK_STATUS_PROCESSING)
                add_running_task(task_id, self.name)
                self._emit_progress(task_id, is_stream)
            self.logger.info('--- %s start ---', self.name)
            result = self.process(state)
            if task_id:
                add_done_task(task_id, self.name)
                self._emit_progress(task_id, is_stream)
            self.logger.info('--- %s done ---', self.name)
            return result
        except Exception as exc:
            if task_id:
                update_task_status(task_id, TASK_STATUS_FAILED)
                self._emit_progress(task_id, is_stream, error=str(exc))
            self.logger.error('%s failed: %s', self.name, exc)
            raise QueryProcessError(str(exc), node_name=self.name, cause=exc)

    @abstractmethod
    def process(self, state: T) -> T:
        ...

    def log_step(self, step_name: str, message: str = '') -> None:
        log_message = f'[{step_name}]'
        if message:
            log_message += f' {message}'
        self.logger.info(log_message)

    @staticmethod
    def _get_task_id(state: T) -> str:
        if isinstance(state, dict):
            return str(state.get('task_id') or '')
        return ''

    @staticmethod
    def _is_stream(state: T) -> bool:
        if isinstance(state, dict):
            return bool(state.get('is_stream'))
        return False

    @staticmethod
    def _emit_progress(task_id: str, is_stream: bool, *, error: str = '') -> None:
        if not is_stream:
            return
        payload = {
            'status': get_task_status(task_id),
            'done_list': get_done_task_list(task_id),
            'running_list': get_running_task_list(task_id),
        }
        if error:
            payload['error'] = error
        push_sse_event(task_id, SSEEvent.PROGRESS, payload)


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
