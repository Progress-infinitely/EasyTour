from __future__ import annotations

import logging
import time
from typing import Any

from dotenv import load_dotenv

from easytour.core.config import get_shared_config

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover
    MongoClient = None  # type: ignore[assignment]

_memory_traces: list[dict[str, Any]] = []
_mongo_col = None


def _get_mongo_col():
    global _mongo_col
    if MongoClient is None:
        return None
    if _mongo_col is not None:
        return _mongo_col

    config = get_shared_config()
    mongo_url = config.mongo_url
    db_name = config.mongo_db_name
    if not mongo_url or not db_name:
        return None

    try:
        client = MongoClient(
            mongo_url,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
        )
        client.admin.command('ping')
        _mongo_col = client[db_name]['retrieval_trace']
        return _mongo_col
    except Exception as exc:
        logger.warning('retrieval_trace Mongo disabled: %s', exc)
        return None


class TraceService:
    def record(self, trace: dict[str, Any]) -> None:
        if not trace:
            return
        record = {k: v for k, v in trace.items() if k != '_id'}
        record.setdefault('created_at', int(time.time() * 1000))

        col = _get_mongo_col()
        if col is not None:
            try:
                col.insert_one(record)
                return
            except Exception as exc:
                logger.warning('trace insert failed: %s', exc)

        _memory_traces.append(record)
