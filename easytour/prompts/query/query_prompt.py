"""查询链 Prompt 常量：主体识别 / HyDE / 分意图回答模板。"""

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
当前检索主题：{retrieval_focus}
回答意图：{answer_intent}

回答要求：
1. 优先依据知识库上下文回答，Web 结果只能作为补充。
2. {intent_instruction}
3. 如果当前检索主题已经明确，回答必须围绕这个主题展开，不要扩展到其他类型内容。
4. 如果上下文不足以支撑结论，要明确说明信息不足。
5. 尽量沿用资料中的主体名称、地名和资料标题。

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

# ---------------------------------------------------------------------------
# 按 answer_intent 分类的回答指令（注入 ANSWER_PROMPT 的 intent_instruction 字段）
# ---------------------------------------------------------------------------

_INTENT_INSTRUCTIONS: dict[str, str] = {
    'lookup': (
        '用户在查询具体事实信息。请优先给出准确事实（开放时间、门票价格、地址等），'
        '并注明信息来源于哪条上下文。若上下文没有明确数据，请如实说明信息不足，不得编造。'
    ),
    'recommendation': (
        '用户在寻求推荐。请按以下格式逐条列出推荐项：\n'
        '- 名称：XXX\n'
        '- 推荐理由：（结合景色/特色/口碑等，50 字以内）\n'
        '- 适合人群：（如亲子/情侣/老人/独行等，若上下文提及）\n'
        '- 最佳季节：（若上下文提及）\n'
        '推荐数量 3–5 条，优先选有完整信息的主体。'
    ),
    'planning': (
        '用户在请求行程规划。请按天数逐日输出行程安排，每日格式：\n'
        '第 N 天：上午 → 下午 → 晚上（每段 30 字以内）\n'
        '若天数信息来自用户问题，务必与用户要求一致。最后附一行预算提示（若上下文有）。'
    ),
    'comparison': (
        '用户在对比多个选项。请按维度逐行给出对比，格式：\n'
        '| 维度 | 选项A | 选项B |\n'
        '维度建议包含：价格、交通便利性、适合人群、特色亮点、注意事项。'
        '最后给出简短结论（不超过 50 字）。'
    ),
    'howto': (
        '用户在询问操作方法或流程。请按步骤逐条给出，格式：\n'
        '步骤 1：...\n步骤 2：...\n'
        '若有注意事项，在步骤后单独列出"注意事项"小节。'
    ),
    'generic': (
        '请优先给出简洁直接的回答。如上下文不足，可适当补充常识，但须注明哪些是补充判断。'
    ),
}


def get_intent_instruction(answer_intent: str) -> str:
    """返回指定 answer_intent 对应的回答指令字符串。"""
    return _INTENT_INSTRUCTIONS.get(answer_intent, _INTENT_INSTRUCTIONS['generic'])


__all__ = [
    'ANSWER_PROMPT',
    'ITEM_NAME_EXTRACT_SYSTEM_PROMPT',
    'ITEM_NAME_EXTRACT_TEMPLATE',
    'RERANK_TASK_INSTRUCTION',
    'USER_HYDE_PROMPT_TEMPLATE',
    'get_intent_instruction',
]
