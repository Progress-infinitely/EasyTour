from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from easytour.schema.meta_schema import CitationModel


class TaskStatusResponse(BaseModel):
    status: str = Field(..., description='Task status')
    done_list: list[str] = Field(default_factory=list, description='Completed nodes')
    running_list: list[str] = Field(default_factory=list, description='Running nodes')
    answer: str = Field(default='', description='Answer text')
    error: str = Field(default='', description='Error text')
    image_urls: list[str] = Field(default_factory=list, description='Attached image URLs')
    citations: list[CitationModel] = Field(default_factory=list, description='Citation list')
    file_title: str = Field(default='', description='Imported file title')
    document_title: str = Field(default='', description='Document display title')
    item_name: str = Field(default='', description='Document-level item name')
    chunk_count: int = Field(default=0, description='Chunk count')
    document_id: str = Field(default='', description='Document ID')
    region_path: str = Field(default='', description='Region path')
    retrieval_type: str = Field(default='', description='Effective retrieval type')
    answer_intent: str = Field(default='', description='Effective answer intent')
    region: dict[str, str] = Field(default_factory=dict, description='Effective region filter')
    doc_main_entities: list[dict[str, Any]] = Field(default_factory=list, description='Main entities')
