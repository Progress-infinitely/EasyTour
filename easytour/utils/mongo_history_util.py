from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from bson import ObjectId
    from pymongo import ASCENDING, MongoClient
except Exception:  # pragma: no cover
    ObjectId = None
    ASCENDING = 1
    MongoClient = None


"""聊天历史存储工具。

这个文件的目标很明确：
给聊天历史提供一层“统一存取接口”。

默认优先使用 Mongo。
如果 Mongo 没配置好或临时不可用，就自动退回到进程内内存。

这不是“生产级完美方案”，但对学习项目非常友好：
- 有 Mongo 时，可以学真实的持久化流程
- 没 Mongo 时，项目也不至于整个问答功能直接瘫掉

所以你可以把这层理解成：
“聊天历史的存储适配层 + 降级兜底层”。
"""


class HistoryMongoTool:
    """Mongo 聊天历史封装。"""

    def __init__(self):
        if MongoClient is None:
            raise RuntimeError('pymongo is not installed')

        self.mongo_url = os.getenv('MONGO_URL', '').strip()
        self.db_name = os.getenv('MONGO_DB_NAME', '').strip()
        if not self.mongo_url or not self.db_name:
            raise ValueError('MONGO_URL or MONGO_DB_NAME is empty')

        self.client = MongoClient(
            self.mongo_url,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
        )
        self.client.admin.command('ping')
        self.db = self.client[self.db_name]
        self.chat_message = self.db['chat_message']
        self.chat_message.create_index([('session_id', 1), ('ts', ASCENDING)])


_history_mongo_tool: HistoryMongoTool | None = None
_memory_history: dict[str, list[dict[str, Any]]] = defaultdict(list)


def _use_mongo() -> bool:
    """判断当前环境是否应该启用 Mongo。"""
    return bool(os.getenv('MONGO_URL', '').strip() and os.getenv('MONGO_DB_NAME', '').strip() and MongoClient is not None)


def get_history_mongo_tool() -> HistoryMongoTool | None:
    """懒加载 Mongo 工具实例。

    这里的思路和很多客户端管理器类似：
    - 第一次真正需要时再创建
    - 如果创建失败，记录 warning 并降级为内存模式
    """
    global _history_mongo_tool
    if not _use_mongo():
        return None
    if _history_mongo_tool is None:
        try:
            _history_mongo_tool = HistoryMongoTool()
        except Exception as exc:
            logger.warning('Mongo history disabled, fallback to memory: %s', exc)
            _history_mongo_tool = None
    return _history_mongo_tool


def clear_history(session_id: str) -> int:
    """清空某个会话的历史消息。"""
    mongo_tool = get_history_mongo_tool()
    if mongo_tool is not None:
        try:
            result = mongo_tool.chat_message.delete_many({'session_id': session_id})
            return int(result.deleted_count)
        except Exception as exc:
            logger.warning('Mongo clear_history failed, fallback to memory: %s', exc)

    deleted_count = len(_memory_history.get(session_id, []))
    _memory_history.pop(session_id, None)
    return deleted_count


def save_chat_message(
    session_id: str,
    role: str,
    text: str,
    rewritten_query: str = '',
    item_names: list[str] | None = None,
    message_id: str | None = None,
    image_urls: list[str] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> str:
    """保存一条聊天消息。

    这个函数既支持：
    - 插入一条新消息
    - 也支持用已有 `message_id` 去更新一条旧消息

    为什么要支持更新？
    因为有些信息可能在流程后半段才补齐，
    例如：主体名称识别结果。
    """
    document = {
        'session_id': session_id,
        'role': role,
        'text': text,
        'rewritten_query': rewritten_query,
        'item_names': item_names or [],
        'image_urls': image_urls or [],
        'citations': citations or [],
        'ts': datetime.now().timestamp(),
    }

    mongo_tool = get_history_mongo_tool()
    if mongo_tool is not None:
        try:
            if message_id and ObjectId is not None:
                mongo_tool.chat_message.update_one({'_id': ObjectId(message_id)}, {'$set': document})
                return message_id
            result = mongo_tool.chat_message.insert_one(document)
            return str(result.inserted_id)
        except Exception as exc:
            logger.warning('Mongo save_chat_message failed, fallback to memory: %s', exc)

    # 如果 Mongo 不可用，就退回到内存字典里保存。
    # 这样至少在当前进程活着期间，多轮对话仍然能工作。
    record_id = message_id or str(uuid.uuid4())
    stored = dict(document)
    stored['_id'] = record_id
    history = _memory_history[session_id]
    if message_id:
        for index, item in enumerate(history):
            if str(item.get('_id')) == message_id:
                history[index] = stored
                return record_id
    history.append(stored)
    return record_id


def update_message_item_names(ids: list[str], item_names: list[str]) -> int:
    """批量更新消息上的主体名称。"""
    if not ids:
        return 0

    mongo_tool = get_history_mongo_tool()
    if mongo_tool is not None and ObjectId is not None:
        try:
            object_ids = [ObjectId(item_id) for item_id in ids]
            result = mongo_tool.chat_message.update_many(
                {'_id': {'$in': object_ids}},
                {'$set': {'item_names': item_names}},
            )
            return int(result.modified_count)
        except Exception as exc:
            logger.warning('Mongo update_message_item_names failed, fallback to memory: %s', exc)

    modified = 0
    target_ids = {str(item_id) for item_id in ids}
    for session_items in _memory_history.values():
        for record in session_items:
            if str(record.get('_id')) in target_ids:
                record['item_names'] = list(item_names)
                modified += 1
    return modified


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """读取最近几条消息，供多轮对话使用。"""
    mongo_tool = get_history_mongo_tool()
    if mongo_tool is not None:
        try:
            cursor = (
                mongo_tool.chat_message.find({'session_id': session_id})
                .sort('ts', ASCENDING)
                .limit(limit)
            )
            return list(cursor)
        except Exception as exc:
            logger.warning('Mongo get_recent_messages failed, fallback to memory: %s', exc)

    records = list(_memory_history.get(session_id, []))
    records.sort(key=lambda item: float(item.get('ts') or 0))
    if limit > 0:
        records = records[-limit:]
    return [dict(record) for record in records]
