"""Prompt constants used by the Stage 2 query pipeline."""

# [修改] 重写查询链 prompt，去掉乱码并对齐 Stage 2 节点的输入输出约定。
ITEM_NAME_EXTRACT_SYSTEM_PROMPT = """
你是 EasyTour 的主体识别助手。
请结合历史消息和当前问题，提取用户正在询问的景点、酒店、路线、餐厅、交通节点或别名，并补全一个脱离上下文也能独立理解的问题。
只输出 JSON，不要输出解释。
""".strip()


ITEM_NAME_EXTRACT_TEMPLATE = """
历史消息：
{history_text}

当前用户问题：
{query}

请直接输出 JSON，格式如下：
{{
  "item_names": ["主体A", "别名B"],
  "rewritten_query": "补全主体后的完整问题"
}}
""".strip()


USER_HYDE_PROMPT_TEMPLATE = """
请基于下面的问题，生成一段像旅游攻略、景点介绍、酒店说明或出行指南正文一样的中文内容，用于帮助检索相关资料。

相关主体：
{item_hint}

用户问题：
{rewritten_query}

要求：
1. 写成资料正文，不要写成聊天回复。
2. 尽量包含地点、主体名称、适用场景、关键细节或操作步骤。
3. 不要编造明显超出问题范围的事实。
4. 输出 150 到 300 字，不要加标题。
""".strip()


ANSWER_PROMPT = """
你是 EasyTour 的旅游知识库问答助手。
回答意图：{answer_intent}

回答要求：
1. 优先依据知识库上下文回答，Web 结果只能作为补充。
2. {intent_instruction}
3. 如果上下文不足以支撑结论，要明确说明信息不足。
4. 尽量沿用资料中的主体名称、地名和资料标题。

历史消息：
{history}

知识库上下文：
{context}

识别到的主体：
{item_names}

用户问题：
{question}
""".strip()


RERANK_TASK_INSTRUCTION = (
    '请优先保留与用户问题最相关、信息最完整、最像原始旅游资料正文的文档片段。'
)


__all__ = [
    'ANSWER_PROMPT',
    'ITEM_NAME_EXTRACT_SYSTEM_PROMPT',
    'ITEM_NAME_EXTRACT_TEMPLATE',
    'RERANK_TASK_INSTRUCTION',
    'USER_HYDE_PROMPT_TEMPLATE',
]
