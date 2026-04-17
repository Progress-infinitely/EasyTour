from __future__ import annotations

from typing import Any, Dict, List

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import EmbeddingError, StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.utils.providers.base import TEXT_TYPE_DOCUMENT
from easytour.utils.providers.provider_factory import get_embedding_provider


class BgeEmbeddingChunksNode(BaseNode):
    """chunk 鍚戦噺鍖栬妭鐐广€?
    杩欎釜鑺傜偣鏄鍏ラ摼鍚庡崐娈电殑鍏抽敭妗ユ銆?    浣犲彲浠ユ妸瀹冪悊瑙ｆ垚锛?
    > 鎶娾€滀汉鑳借鐨勬枃鏈潡鈥濓紝鍙樻垚鈥淢ilvus 鑳芥绱㈢殑鍚戦噺鍧椻€濄€?
    鍓嶉潰 `document_split_node` 鍋氱殑鏄細
    - 鎶婇暱鏂囧垏鎴愬涓?chunk

    杩欓噷鍋氱殑鏄細
    - 缁欐瘡涓?chunk 鐢熸垚 dense / sparse 涓ょ被鍚戦噺

    鍙湁缁忚繃杩欎竴姝ワ紝鍚庨潰鐨?`import_milvus_node` 鎵嶈兘鎶婃暟鎹湡姝ｅ啓杩涘悜閲忓簱锛?    鏌ヨ閾句箣鍚庢墠鏈変笢瑗垮彲鎼溿€?
    鍚嶅瓧閲岃櫧鐒惰繕淇濈暀 `Bge` 杩欎釜鍘嗗彶鍛藉悕锛?    浣嗗綋鍓嶅疄鐜板凡缁忎笉鏄湰鍦?BGE 妯″瀷浜嗭紝
    鑰屾槸缁熶竴璧拌繙绋?embedding provider銆?    """

    name = 'beg_embedding_chunks_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """鎵归噺鎶?chunk 杞垚鍚戦噺锛屽苟鎶婂悜閲忓啓鍥?`state['chunks']`銆?""
        self.log_step('step1', '鏍￠獙 chunks 鏁版嵁缁撴瀯')
        validated_chunks = self._validate_state(state)

        self.log_step('step2', '鑾峰彇杩滅▼ embedding provider')
        try:
            embedding_provider = get_embedding_provider()
        except Exception as e:
            self.logger.error('杩滅▼ embedding provider 鍒涘缓澶辫触, 鍘熷洜: %s', e)
            raise EmbeddingError(
                message=f'杩滅▼ embedding provider 鍒涘缓澶辫触, 鍘熷洜: {e}',
                node_name=self.name,
            )

        batch_size = self.config.embedding_batch_size
        total = len(validated_chunks)
        final_chunks = []
        for index in range(0, total, batch_size):
            batch_chunks = validated_chunks[index:index + batch_size]
            batch_end = index + len(batch_chunks)
            self.logger.info('宓屽叆鎵规 [%s-%s] / %s', index + 1, batch_end, total)
            current_chunks = self._embed_chunks(batch_chunks, embedding_provider)
            final_chunks.extend(current_chunks)

        state['chunks'] = final_chunks
        return state

    def _validate_state(self, state: ImportGraphState) -> List[Dict[str, Any]]:
        """纭 state 閲岀殑 `chunks` 鏄竴涓悎娉曠殑瀛楀吀鍒楄〃銆?""
        chunks = state.get('chunks')
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name='chunks', expected_type=list)

        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise ValidationError(
                    message=f'[chunk_{index + 1}] 绫诲瀷鍜屾湡鏈涗笉鍖归厤锛屽疄闄呯被鍨?{type(chunk).__name__}',
                    node_name=self.name,
                )
        return chunks

    def _embed_chunks(self, batch_chunks: List[Dict[str, Any]], embedding_provider) -> List[Dict[str, Any]]:
        """鎶婁竴鎵?chunk 閫佸幓杩滅▼ embedding銆?
        涓€涓緢鍊煎緱娉ㄦ剰鐨勮璁℃槸锛?        褰撳墠涓嶆槸鍙嬁 `content` 鍘诲仛鍚戦噺鍖栵紝
        鑰屾槸鎶?`item_name + content` 涓€璧烽€佸幓缂栫爜銆?
        涓轰粈涔堬紵
        鍥犱负鍚屼竴鍙ヨ鏄庢枃鏈紝鏀惧湪涓嶅悓璁惧鏂囨。閲岋紝璇箟鑳屾櫙鍙兘骞朵笉涓€鏍枫€?        鎶?`item_name` 涓€璧峰甫涓婏紝鍙互璁╁悜閲忛噷淇濈暀鏇村鈥滆繖娈靛唴瀹瑰睘浜庤皝鈥濈殑淇″彿銆?        """
        embedding_documents = [f"{chunk.get('item_name', '')}\n{chunk.get('content', '')}" for chunk in batch_chunks]

        try:
            embedding_records = embedding_provider.embed_texts(
                embedding_documents,
                text_type=TEXT_TYPE_DOCUMENT,
                dimension=self.config.embedding_dim,
            )
        except Exception as e:
            raise EmbeddingError(message=f'宓屽叆澶辫触, 鍘熷洜: {e}', node_name=self.name)

        if not embedding_records:
            raise EmbeddingError(message='宓屽叆缁撴灉涓嶅瓨鍦?, node_name=self.name)

        # 杩滅▼ API 宸茬粡鐩存帴杩斿洖鏍囧噯鍖栧悗鐨?dense/sparse 缁撴瀯锛?        # 杩欓噷涓嶉渶瑕佸啀鎵嬪姩鎷?CSR 鎴栧仛棰濆鏍煎紡杞崲銆?        for chunk, record in zip(batch_chunks, embedding_records):
            chunk['dense_vector'] = record.dense_vector
            chunk['sparse_vector'] = record.sparse_vector

        return batch_chunks


__all__ = ['BgeEmbeddingChunksNode']

