from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easytour.schema.meta_schema import CitationModel


class RegionFilterModel(BaseModel):
    province: str = Field(default='', description='省份')
    city: str = Field(default='', description='城市')
    region_path: str = Field(default='', description='归一化地区路径')


class QueryRequest(BaseModel):
    query: str = Field(..., description='用户问题')
    session_id: str | None = Field(default=None, description='会话 ID')
    message_id: str | None = Field(default=None, description='消息 ID')
    history: list[dict[str, Any]] = Field(default_factory=list, description='历史消息')
    is_stream: bool = Field(default=False, description='是否流式返回')
    retrieval_type: str | None = Field(default=None, description='可选的检索类型覆盖')
    region: str | None = Field(default=None, description='可选的地区覆盖')


class QueryResponse(BaseModel):
    message: str = Field(..., description='执行结果')
    session_id: str = Field(..., description='会话 ID')
    answer: str = Field(default='', description='最终答案')
    task_id: str = Field(default='', description='任务 ID')
    rewritten_query: str = Field(default='', description='改写后的查询')
    retrieval_type: str = Field(default='', description='识别出的检索类型')
    answer_intent: str = Field(default='', description='识别出的回答意图')
    region: RegionFilterModel = Field(default_factory=RegionFilterModel, description='识别出的地区过滤')
    item_names: list[str] = Field(default_factory=list, description='识别出的主体列表')
    structured: dict[str, Any] = Field(default_factory=dict, description='结构化回答')
    citations: list[CitationModel] = Field(default_factory=list, description='引用信息')
    done_list: list[str] = Field(default_factory=list, description='已完成节点')
    error: str = Field(default='', description='错误信息')
    image_urls: list[str] = Field(default_factory=list, description='附带图片')


class StreamSubmitResponse(BaseModel):
    message: str = Field(..., description='流式任务提交成功')
    session_id: str = Field(..., description='会话 ID')
    task_id: str = Field(..., description='任务 ID')


class HistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default='', alias='_id')
    session_id: str = Field(default='', description='会话 ID')
    role: str = Field(default='', description='消息角色')
    text: str = Field(default='', description='消息内容')
    rewritten_query: str = Field(default='', description='改写后的查询')
    item_names: list[str] = Field(default_factory=list, description='主体列表')
    image_urls: list[str] = Field(default_factory=list, description='图片列表')
    ts: float | None = Field(default=None, description='时间戳')


class HistoryResponse(BaseModel):
    session_id: str = Field(..., description='会话 ID')
    items: list[HistoryItem] = Field(..., description='历史消息列表')
