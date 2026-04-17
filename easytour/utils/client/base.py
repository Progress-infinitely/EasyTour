from __future__ import annotations

import logging
import os
import threading
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseClientManager:
    """客户端管理器基类。

    这一层的目标不是做业务，而是把“客户端管理”这种重复劳动抽出来。

    你可以把它理解成一个公共工具箱，专门给子类提供两类通用能力：
    - `_require_env()`：环境变量校验
    - `_get_or_create()`：带锁的懒加载单例创建模板

    子类只需要关心：
    “具体客户端怎么创建？”
    不需要重复写锁逻辑、缓存逻辑、环境变量读取逻辑。
    """

    @staticmethod
    def _require_env(key: str) -> str:
        """读取必需的环境变量，缺失时立即抛异常。"""
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(f'缺少必需的环境变量: {key}')
        return value

    @classmethod
    def _get_or_create(cls, attr_name: str, lock: threading.Lock, factory):
        """带双重检查锁的通用创建模板。

        参数说明：
        - `attr_name`：类属性名，例如 `_minio_client`
        - `lock`：对应实例创建过程的线程锁
        - `factory`：无参工厂函数，负责真正创建客户端

        为什么要做“双重检查锁”？
        - 第一次无锁检查：如果实例已经存在，直接返回，速度快。
        - 第二次持锁检查：防止并发场景下多个线程重复创建同一个客户端。

        对初学者来说，可以先把它理解成：
        “一种保证客户端只创建一次、而且线程安全的模板写法”。
        """
        instance = getattr(cls, attr_name, None)
        if instance is not None:
            return instance

        with lock:
            instance = getattr(cls, attr_name, None)
            if instance is not None:
                return instance

            instance = factory()
            setattr(cls, attr_name, instance)
            return instance
