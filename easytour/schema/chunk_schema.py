from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkScalarFieldSpec:
    field_name: str
    max_length: int


# [修改] 收敛当前主链真正依赖的 chunks collection 显式字段，避免 schema 定义散落在多处。
CHUNK_SCALAR_FIELDS: tuple[ChunkScalarFieldSpec, ...] = (
    ChunkScalarFieldSpec('content', 65535),
    ChunkScalarFieldSpec('title', 1024),
    ChunkScalarFieldSpec('parent_title', 1024),
    ChunkScalarFieldSpec('file_title', 1024),
    ChunkScalarFieldSpec('item_name', 1024),
    ChunkScalarFieldSpec('primary_item_name', 1024),
    ChunkScalarFieldSpec('document_id', 64),
    ChunkScalarFieldSpec('document_title', 1024),
    ChunkScalarFieldSpec('content_type', 64),
    ChunkScalarFieldSpec('province', 128),
    ChunkScalarFieldSpec('city', 128),
    ChunkScalarFieldSpec('region_path', 256),
    ChunkScalarFieldSpec('source_label_display', 1024),
)


# [修改] 向量检索主链统一读取这些字段，避免 vector / hyde 两处各写一份。
CHUNK_SEARCH_OUTPUT_FIELDS: tuple[str, ...] = (
    'chunk_id',
    'content',
    'title',
    'parent_title',
    'file_title',
    'document_title',
    'item_name',
    'primary_item_name',
    'entity_names',
    'document_id',
    'source_label_display',
    'city',
)


# [修改] 预览页 fallback 只需要这一小组字段，单独收敛出来避免硬编码散落。
CHUNK_PREVIEW_OUTPUT_FIELDS: tuple[str, ...] = (
    'chunk_id',
    'document_id',
    'content',
    'title',
    'parent_title',
)


__all__ = [
    'CHUNK_PREVIEW_OUTPUT_FIELDS',
    'CHUNK_SCALAR_FIELDS',
    'CHUNK_SEARCH_OUTPUT_FIELDS',
    'ChunkScalarFieldSpec',
]
