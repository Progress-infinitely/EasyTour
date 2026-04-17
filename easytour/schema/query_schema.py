from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easytour.schema.meta_schema import CitationModel


class RegionFilterModel(BaseModel):
    province: str = Field(default='', description='Normalized province')
    city: str = Field(default='', description='Normalized city')
    region_path: str = Field(default='', description='Normalized region path')


class QueryRequest(BaseModel):
    query: str = Field(..., description='User query')
    session_id: str | None = Field(default=None, description='Session ID')
    message_id: str | None = Field(default=None, description='Message ID')
    history: list[dict[str, Any]] = Field(default_factory=list, description='Conversation history')
    is_stream: bool = Field(default=False, description='Whether to stream the answer')
    retrieval_type: str | None = Field(default=None, description='Optional retrieval type override')
    region: str | None = Field(default=None, description='Optional region override')


class QueryResponse(BaseModel):
    message: str = Field(..., description='Execution status')
    session_id: str = Field(..., description='Session ID')
    answer: str = Field(default='', description='Final answer')
    task_id: str = Field(default='', description='Task ID')
    rewritten_query: str = Field(default='', description='Rewritten query')
    retrieval_type: str = Field(default='', description='Detected retrieval type')
    answer_intent: str = Field(default='', description='Detected answer intent')
    region: RegionFilterModel = Field(default_factory=RegionFilterModel, description='Detected region filter')
    item_names: list[str] = Field(default_factory=list, description='Detected item names')
    structured: dict[str, Any] = Field(default_factory=dict, description='Structured answer payload')
    citations: list[CitationModel] = Field(default_factory=list, description='Citation list')
    done_list: list[str] = Field(default_factory=list, description='Completed node list')
    error: str = Field(default='', description='Error message')
    image_urls: list[str] = Field(default_factory=list, description='Attached image URLs')


class StreamSubmitResponse(BaseModel):
    message: str = Field(..., description='Stream task submitted')
    session_id: str = Field(..., description='Session ID')
    task_id: str = Field(..., description='Task ID')


class HistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default='', alias='_id')
    session_id: str = Field(default='', description='Session ID')
    role: str = Field(default='', description='Message role')
    text: str = Field(default='', description='Message text')
    rewritten_query: str = Field(default='', description='Rewritten query')
    item_names: list[str] = Field(default_factory=list, description='Detected item names')
    image_urls: list[str] = Field(default_factory=list, description='Attached image URLs')
    citations: list[CitationModel] = Field(default_factory=list, description='Citation list')
    ts: float | None = Field(default=None, description='Unix timestamp')


class HistoryResponse(BaseModel):
    session_id: str = Field(..., description='Session ID')
    items: list[HistoryItem] = Field(..., description='History items')
