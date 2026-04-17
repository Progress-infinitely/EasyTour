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
    """瀵煎叆鑺傜偣鍩虹被銆?
    鎵€鏈夊鍏ヨ妭鐐归兘缁ф壙瀹冦€?
    杩欎釜鍩虹被甯綘缁熶竴鍋氫簡涓夌被鈥滄瘡涓妭鐐归兘瑕侀噸澶嶅仛鈥濈殑宸ヤ綔锛?    1. 鑷姩鎷块厤缃€?    2. 鑷姩璁板綍鏃ュ織銆?    3. 鑷姩鏇存柊浠诲姟杩涘害锛屽苟鎶婂紓甯稿寘瑁呮垚缁熶竴鏍煎紡銆?
    鎵€浠ュ叿浣撹妭鐐归€氬父鍙渶瑕佷笓蹇冨疄鐜?`process()`锛?    鈥滄嬁鍒?state -> 鍋氳嚜宸辩殑涓氬姟 -> 杩斿洖鏇存柊鍚庣殑 state鈥濄€?    """

    name: str = 'base_node'

    def __init__(self, config: Optional[ImportConfig] = None):
        self.config = config or get_config()
        self.logger = logging.getLogger(f'import.{self.name}')

    def __call__(self, state: T) -> T:
        """璁╄妭鐐瑰璞℃湰韬彲浠ュ儚鍑芥暟涓€鏍疯鍥捐皟鐢ㄣ€?
        鍦?LangGraph 鐪嬫潵锛屼竴涓妭鐐规湰璐ㄤ笂灏辨槸鈥滃彲璋冪敤瀵硅薄鈥濄€?        杩欓噷鎶婅妭鐐圭敓鍛藉懆鏈熺粺涓€鍖呰捣鏉ュ悗锛屽瓙绫诲氨涓嶅繀姣忔閮芥墜鍐欙細
        - 寮€濮嬫棩蹇?        - 浠诲姟鐘舵€佹洿鏂?        - 寮傚父鍖呰
        """
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
        """瀛愮被蹇呴』瀹炵幇鐨勬牳蹇冨鐞嗛€昏緫銆?""
        ...

    def log_step(self, step_name: str, message: str = '') -> None:
        """杈撳嚭鏇寸粏绮掑害鐨勬楠ゆ棩蹇椼€?""
        log_msg = f'[{step_name}]'
        if message:
            log_msg += f' {message}'
        self.logger.info(log_msg)

    @staticmethod
    def _get_task_id(state: T) -> str:
        """浠?state 閲屽畨鍏ㄥ彇鍑?task_id銆?""
        if isinstance(state, dict):
            return str(state.get('task_id') or '')
        return ''


def setup_logging(level: int = logging.INFO) -> None:
    """缁熶竴鍒濆鍖栨棩蹇楁牸寮忋€?""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

