from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    'DocumentService',
    'ImportFileService',
    'MetaService',
    'QueryService',
    'TaskService',
]


def __getattr__(name: str) -> Any:
    # [修改] 改成懒加载，避免 document_service/query_service/query graph 在包导入阶段互相绕成环。
    module_map = {
        'DocumentService': ('easytour.services.document_service', 'DocumentService'),
        'ImportFileService': ('easytour.services.import_file_service', 'ImportFileService'),
        'MetaService': ('easytour.services.meta_service', 'MetaService'),
        'QueryService': ('easytour.services.query_service', 'QueryService'),
        'TaskService': ('easytour.services.task_service', 'TaskService'),
    }
    if name not in module_map:
        raise AttributeError(name)
    module_name, attr_name = module_map[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
