from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UploadForceMode(str, Enum):
    METADATA_ONLY = 'metadata_only'
    REINDEX = 'reindex'


class UploadStatus(str, Enum):
    PROCESSING = 'processing'
    ALREADY_IMPORTED = 'already_imported'
    ERROR = 'error'
    REQUIRES_REINDEX = 'requires_reindex'


class UploadOverride(BaseModel):
    model_config = ConfigDict(extra='ignore', use_enum_values=True)

    content_type: str | None = Field(default=None, description='覆盖内容类型。')
    region: str | None = Field(default=None, description='覆盖地区，自由文本输入。')
    source_path: str | None = Field(default=None, description='覆盖来源路径或网页 URL。')
    document_title: str | None = Field(default=None, description='覆盖文档标题。')
    source_label_display: str | None = Field(default=None, description='覆盖前端展示来源标签。')


class UploadResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    message: str = Field(..., description='上传接口响应消息。')
    status: UploadStatus = Field(..., description='上传处理状态。')
    document_id: str = Field(default='', description='稳定文档 ID。')
    task_id: str | None = Field(default=None, description='本次服务活期内的任务 ID。')
    error: str | None = Field(default=None, description='错误详情。')
