from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, TypeVar

from easytour.processor.import_process.config import ImportConfig, get_config
from easytour.processor.import_process.exceptions import ImportProcessError
from easytour.utils.task_util import (
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    add_done_task,
    add_running_task,
    update_task_status,
)

T = TypeVar('T')


class BaseNode(ABC):
    """导入节点基类。所有导入节点都继承它。"""

    name: str = 'base_node'

    def __init__(self, config: Optional[ImportConfig] = None):
        self.config = config or get_config()
        self.logger = logging.getLogger(f'import.{self.name}')

    def __call__(self, state: T) -> T:
        """让节点对象本身可以像函数一样被调用。"""
        task_id = self._get_task_id(state)
        try:
            if task_id:
                update_task_status(task_id, TASK_STATUS_PROCESSING)
                add_running_task(task_id, self.name)
            self.logger.info('--- %s start ---', self.name)
            result = self.process(state)
            if task_id:
                add_done_task(task_id, self.name)
            self.logger.info('--- %s done ---', self.name)
            return result
        except Exception as exc:
            if task_id:
                update_task_status(task_id, TASK_STATUS_FAILED)
            self.logger.error('%s failed: %s', self.name, exc)
            raise ImportProcessError(message=str(exc), node_name=self.name, cause=exc)

    @abstractmethod
    def process(self, state: T) -> T:
        """子类必须实现的核心处理逻辑。"""
        ...

    def log_step(self, step_name: str, message: str = '') -> None:
        """输出更细粒度的步骤日志。"""
        log_msg = f'[{step_name}]'
        if message:
            log_msg += f' {message}'
        self.logger.info(log_msg)

    @staticmethod
    def _get_task_id(state: T) -> str:
        """从 state 里安全取出 task_id。"""
        if isinstance(state, dict):
            return str(state.get('task_id') or '')
        return ''


def setup_logging(level: int = logging.INFO) -> None:
    """统一初始化日志格式。"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
