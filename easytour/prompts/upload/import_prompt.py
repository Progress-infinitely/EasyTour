"""导入链使用的 prompt 常量。"""

# ===== 文档级抽取（doc_level_extract_node 使用） =====

DOC_LEVEL_EXTRACT_SYSTEM = 'Return valid JSON only.'

DOC_LEVEL_EXTRACT_USER_TEMPLATE = (
    '你是旅游文档解析助手，请从以下信息中提取元数据，只返回 JSON。\n\n'
    '必须包含字段：\n'
    '- content_type: 从 {content_types} 中选一个\n'
    '- province: 省份（无法确定则为空字符串）\n'
    '- city: 城市（无法确定则为空字符串）\n'
    '- region_path: 地区路径，如"海南/三亚"（无法确定则为空字符串）\n'
    '- document_title: 简洁中文标题\n'
    '- main_entities: 主要实体列表，每项含 item_name（名称）和 item_type（类型）\n\n'
    '文件名：{file_title}\n\n'
    '文档内容（前4000字）：\n{content}'
)


# ===== 新：chunk 级抽取（chunk_level_extract_node 使用） =====

CHUNK_LEVEL_EXTRACT_SYSTEM = 'Return valid JSON only, format: {"items": [...]}'

CHUNK_LEVEL_EXTRACT_COMMON_FIELDS = (
    '"tips": 实用提示（字符串，无则为空）, '
    '"notes": 备注（字符串，无则为空）, '
    '"primary_item_name": 本段描述的核心景点/酒店/地名（字符串，无则为空）'
)

CHUNK_LEVEL_EXTRA_FIELDS: dict[str, str] = {
    'attraction': (
        '"opening_hours": 开放时间（字符串）, "ticket_price": 门票价格（字符串）, '
        '"best_season": 最佳季节（字符串）, "suitable_for": 适合人群（字符串）, '
        '"attraction_features": 景点特色（字符串）'
    ),
    'route': '"route_days": 行程天数（整数，无则为0）, "route_budget": 预算范围（字符串）, "suitable_for": 适合人群（字符串）',
    'hotel': '"price_range": 价格区间（字符串）, "hotel_tags": 酒店标签（字符串）',
    'food': '"price_range": 价格区间（字符串）, "food_tags": 美食标签（字符串）',
    'transport': '',
    'culture': '',
}

CHUNK_LEVEL_EXTRACT_USER_TEMPLATE = (
    '请从以下旅游文档片段中提取结构化字段，返回 JSON，格式为 {{"items": [...]}}，'
    '数组长度与输入片段数量相同。\n\n'
    '文档类型：{content_type}\n'
    '每项必须包含：{common_fields}{sep}{extra_fields}\n\n'
    '内容片段（共 {count} 条）：\n{chunks_text}'
)


__all__ = [
    'DOC_LEVEL_EXTRACT_SYSTEM',
    'DOC_LEVEL_EXTRACT_USER_TEMPLATE',
    'CHUNK_LEVEL_EXTRACT_SYSTEM',
    'CHUNK_LEVEL_EXTRACT_COMMON_FIELDS',
    'CHUNK_LEVEL_EXTRA_FIELDS',
    'CHUNK_LEVEL_EXTRACT_USER_TEMPLATE',
]
