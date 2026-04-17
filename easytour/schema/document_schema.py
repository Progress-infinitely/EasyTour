from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentMetadataResponse(BaseModel):
    document_id: str = Field(..., description='稳定文档 ID。')
    file_title: str = Field(default='', description='原始文件名。')
    document_title: str = Field(default='', description='文档标题。')
    content_type: str = Field(default='', description='文档内容类型。')
    province: str = Field(default='', description='省份。')
    city: str = Field(default='', description='城市。')
    region_path: str = Field(default='', description='归一化地区路径。')
    main_entities: list[dict[str, Any]] = Field(default_factory=list, description='文档主实体列表。')
    chunk_count: int = Field(default=0, description='chunk 数量。')
    last_ingest_batch_id: str = Field(default='', description='最近一次导入批次 ID。')
    last_ingest_at: int = Field(default=0, description='最近一次导入时间戳。')
