from __future__ import annotations

from functools import lru_cache

from easytour.services.document_service import DocumentService
from easytour.services.import_file_service import ImportFileService
from easytour.services.meta_service import MetaService
from easytour.services.query_service import QueryService
from easytour.services.task_service import TaskService


@lru_cache
def get_task_service() -> TaskService:
    return TaskService()


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService()


@lru_cache
def get_import_file_service() -> ImportFileService:
    return ImportFileService(get_task_service(), get_document_service())


@lru_cache
def get_query_service() -> QueryService:
    return QueryService()


@lru_cache
def get_meta_service() -> MetaService:
    return MetaService(get_document_service())
