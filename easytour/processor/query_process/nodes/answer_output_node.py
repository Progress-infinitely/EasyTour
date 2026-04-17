from __future__ import annotations

from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.state import QueryGraphState
from easytour.prompts.query.query_prompt import ANSWER_PROMPT
from easytour.utils.sse_util import SSEEvent, push_sse_event
from easytour.utils.providers.provider_factory import get_llm_provider


class AnswerOutputNode(BaseNode):
    """鏈€缁堢瓟妗堢敓鎴愯妭鐐广€?
    杩欐槸鏌ヨ閾剧殑鏈€鍚庝竴绔欙紝涔熸槸鈥滅敤鎴风湡姝ｇ湅鍒扮粨鏋溾€濈殑鍦版柟銆?
    鍓嶉潰鍋氱殑浜嬫儏锛?    - 纭涓讳綋鍚嶇О
    - 澶氳矾妫€绱?    - 铻嶅悎
    - 绮炬帓

    鏈川涓婇兘鏄湪缁欒繖閲屽噯澶団€滃弬鑰冩潗鏂欌€濄€?
    杩欎釜鑺傜偣鐪熸璐熻矗鐨勬槸锛?    1. 鎶婃渶缁堟枃妗ｆ暣鐞嗘垚 prompt 閲岀殑涓婁笅鏂?    2. 鎶婂巻鍙插璇濄€佷富浣撳悕绉般€佺敤鎴烽棶棰樹竴璧锋嫾杩涘幓
    3. 璋冨ぇ妯″瀷鐢熸垚鏈€缁堢瓟妗?    4. 濡傛灉鏄祦寮忔ā寮忥紝灏辫竟鐢熸垚杈规帹缁欏墠绔?    """

    name = 'answer_output_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """鏍规嵁鏈€缁堜笂涓嬫枃鏋勯€?prompt锛屽苟鐢熸垚鍥炵瓟銆?""
        query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        context = self._format_context(state.get('reranked_docs') or [])
        prompt = ANSWER_PROMPT.format(
            context=context or 'No matched context was found.',
            history=self._format_history(state.get('history') or []),
            item_names=', '.join(state.get('item_names') or []) or 'No confirmed item names.',
            question=query,
        )

        llm_client = get_llm_provider().get_client(response_format=False)
        task_id = str(state.get('task_id') or '')
        is_stream = bool(state.get('is_stream'))

        if is_stream and task_id:
            # 娴佸紡妯″紡涓嬶紝涓嶇瓑妯″瀷涓€娆℃€у悙鍑哄叏鏂囥€?            # 鑰屾槸姣忔嬁鍒颁竴灏忔锛屽氨绔嬪埢閫氳繃 SSE 鎺ㄧ粰鍓嶇銆?            chunks: list[str] = []
            for chunk in llm_client.stream(prompt):
                delta = self._extract_chunk_text(chunk)
                if not delta:
                    continue
                chunks.append(delta)
                push_sse_event(task_id, SSEEvent.DELTA, {'delta': delta})
            return {
                'prompt': prompt,
                'answer': ''.join(chunks).strip(),
            }

        response = llm_client.invoke(prompt)
        return {
            'prompt': prompt,
            'answer': str(getattr(response, 'content', '') or '').strip(),
        }

    def _format_context(self, docs: list[dict[str, Any]]) -> str:
        """鎶婄簿鎺掑悗鐨勬枃妗ｆ暣鐞嗘垚 prompt 閲岀殑涓婁笅鏂囨枃鏈€?
        杩欓噷涓嶆槸绠€鍗曟妸鎵€鏈夊唴瀹规棤鑴戞嫾鎺ワ紝
        鑰屾槸浼氬仛涓や欢浜嬶細
        - 缁欐瘡鏉℃潗鏂欏姞涓婄紪鍙?/ 鏍囬 / 涓讳綋鍚嶆彁绀?        - 鎺у埗鎬婚暱搴︼紝閬垮厤 prompt 杩囬暱
        """
        lines: list[str] = []
        used_chars = 0
        for index, doc in enumerate(docs, start=1):
            content = str(doc.get('content', '')).strip()
            if not content:
                continue
            title = str(doc.get('title') or doc.get('file_title') or '').strip()
            item_name = str(doc.get('item_name', '')).strip()
            header_parts = [f'[{index}]']
            if item_name:
                header_parts.append(f'item={item_name}')
            if title:
                header_parts.append(f'title={title}')
            entry = ' '.join(header_parts) + '\n' + content
            if used_chars + len(entry) > self.config.max_context_chars:
                break
            lines.append(entry)
            used_chars += len(entry) + 2
        return '\n\n'.join(lines)

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        """鎶婃渶杩戝嚑杞巻鍙插璇濇暣鐞嗘垚 prompt 鏂囨湰銆?""
        lines: list[str] = []
        for message in history[-6:]:
            role = str(message.get('role', '')).strip()
            text = str(message.get('text', '')).strip()
            if role and text:
                lines.append(f'{role}: {text}')
        return '\n'.join(lines) or 'No history.'

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        """浠庢祦寮忚繑鍥炵墖娈甸噷鎻愬彇鐪熸鏂囨湰銆?
        涓嶅悓瀹㈡埛绔?/ SDK 杩斿洖鐨?chunk 缁撴瀯鍙兘涓嶅畬鍏ㄤ竴鏍凤紝
        鎵€浠ヨ繖閲屽仛涓€灞傚吋瀹硅В鏋愶紝灏介噺缁熶竴鎻愬彇鍑烘枃鏈唴瀹广€?        """
        content = getattr(chunk, 'content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get('text')
                    if text:
                        parts.append(str(text))
            return ''.join(parts)
        return str(content or '')

