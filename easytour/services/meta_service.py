from __future__ import annotations

from easytour.schema.meta_schema import ContentType, MetaOption
from easytour.services.document_service import DocumentService


class MetaService:
    def __init__(self, document_service: DocumentService):
        self._document_service = document_service

    def get_content_types(self) -> list[MetaOption]:
        return [MetaOption(label=item.value, value=item.value) for item in ContentType]

    def get_regions(self) -> list[MetaOption]:
        return [MetaOption(**item) for item in self._document_service.list_regions()]

    def get_items(self) -> list[MetaOption]:
        return [MetaOption(**item) for item in self._document_service.list_items()]
