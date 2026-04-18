from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    ATTRACTION = 'attraction'
    ROUTE = 'route'
    HOTEL = 'hotel'
    FOOD = 'food'
    TRANSPORT = 'transport'
    CULTURE = 'culture'


class AnswerIntent(str, Enum):
    LOOKUP = 'lookup'
    RECOMMENDATION = 'recommendation'
    PLANNING = 'planning'
    COMPARISON = 'comparison'
    HOWTO = 'howto'
    GENERIC = 'generic'


class CitationModel(BaseModel):
    source_label_display: str = Field(default='', description='前端展示用的来源标题')
    item_name: str = Field(default='', description='命中的主体名称')
    city: str = Field(default='', description='命中的城市')
    document_id: str = Field(default='', description='来源文档 ID')
    source_type: str = Field(default='document', description='来源类型：document / web_search')
    source_url: str = Field(default='', description='在线来源链接，仅 web_search 使用')
    chunk_id: str = Field(default='', description='命中的 chunk ID，仅本地文档引用使用')


class MetaOption(BaseModel):
    label: str = Field(..., description='前端展示的选项名称')
    value: str = Field(..., description='实际提交的选项值')
