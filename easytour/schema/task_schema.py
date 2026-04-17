from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskStatusResponse(BaseModel):
    status: str = Field(..., description='任务状态。')
    done_list: list[str] = Field(default_factory=list, description='已完成节点。')
    running_list: list[str] = Field(default_factory=list, description='正在运行的节点。')
    answer: str = Field(default='', description='查询答案。')
    error: str = Field(default='', description='错误详情。')
    image_urls: list[str] = Field(default_factory=list, description='图片链接。')
    file_title: str = Field(default='', description='文件名。')
    item_name: str = Field(default='', description='主实体名。')
    chunk_count: int = Field(default=0, description='chunk 数量。')
    document_id: str = Field(default='', description='稳定文档 ID。')
    region_path: str = Field(default='', description='归一化地区路径。')
    doc_main_entities: list[dict[str, Any]] = Field(default_factory=list, description='文档级主实体。')
