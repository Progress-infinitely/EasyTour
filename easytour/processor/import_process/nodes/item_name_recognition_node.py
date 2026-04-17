from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pymilvus import DataType

from easytour.processor.import_process.base import BaseNode
from easytour.processor.import_process.exceptions import EmbeddingError, StateFieldError, ValidationError
from easytour.processor.import_process.state import ImportGraphState
from easytour.prompts.upload.import_prompt import ITEM_NAME_SYSTEM_PROMPT, ITEM_NAME_USER_PROMPT_TEMPLATE
from easytour.utils.client.ai_clients import AIClients
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.providers.base import TEXT_TYPE_DOCUMENT
from easytour.utils.providers.provider_factory import get_embedding_provider


class ItemNameRecognitionNode(BaseNode):
    """涓讳綋鍚嶇О璇嗗埆鑺傜偣銆?
    杩欎釜鑺傜偣鍦ㄥ鍏ラ摼閲岄潪甯稿叧閿紝
    鍥犱负瀹冨洖绛旂殑鏄竴涓牳蹇冮棶棰橈細

    > 褰撳墠瀵煎叆鐨勮繖浠芥枃妗ｏ紝涓昏鍦ㄨ鍝釜璁惧 / 鍟嗗搧 / 涓讳綋锛?
    璇嗗埆鍑虹殑 `item_name` 鏈変袱涓富瑕佺敤閫旓細
    1. 鍐欏洖姣忎釜 chunk锛屾柟渚挎煡璇㈡椂鎸変富浣撹繃婊?    2. 鍗曠嫭瀛樿繘 `item_name_collection`锛屾柟渚挎煡璇㈤摼鍏堝仛涓讳綋鍚嶇О纭

    杩欎篃鏄负浠€涔堝畠涓嶄粎鈥滆瘑鍒悕绉扳€濓紝杩樹細棰濆鈥滅粰鍚嶇О鍋?embedding 骞跺崟鐙叆搴撯€濄€?    """

    name = 'item_name_recognition_node'

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """璇嗗埆鏂囨。涓讳綋鍚嶇О锛屽苟鎶婄粨鏋滃啓鍥?chunk 涓庡崟鐙泦鍚堛€?""
        file_title, chunks, item_name_chunks_k, item_name_chunk_size = self._validate_state(state)
        item_name_recognition_context = self._prepare_item_name_recognition_context(
            chunks, item_name_chunks_k, item_name_chunk_size
        )
        item_name = self._recognition_name(file_title, item_name_recognition_context)
        dense_vector, sparse_vector = self._embedding_item_name(item_name)
        self._insert_milvus(
            file_title,
            item_name,
            dense_vector,
            sparse_vector,
            self.config.item_name_collection,
        )
        self._fill_item_name(item_name, state, chunks)
        return state

    def _validate_state(self, state: ImportGraphState):
        """鏍￠獙璇嗗埆涓讳綋鍚嶇О鎵€闇€鐨勮緭鍏ャ€?""
        file_title = state.get('file_title')
        chunks = state.get('chunks')

        if not file_title:
            raise StateFieldError(node_name=self.name, field_name='file_title', expected_type=str)
        if not chunks or not isinstance(chunks, list):
            raise StateFieldError(node_name=self.name, field_name='chunks', expected_type=list)

        item_name_chunks_k = self.config.item_name_chunk_k
        if not item_name_chunks_k or item_name_chunks_k <= 0:
            raise ValidationError(message='item_name_chunk_k 涓虹┖鎴栬€呮棤鏁?, node_name=self.name)

        item_name_chunk_size = self.config.item_name_chunk_size
        if not item_name_chunk_size or item_name_chunk_size <= 0:
            raise ValidationError(message='item_name_chunk_size 涓虹┖鎴栬€呮棤鏁?, node_name=self.name)

        return file_title, chunks, item_name_chunks_k, item_name_chunk_size

    def _prepare_item_name_recognition_context(self, chunks, item_name_chunks_k, item_name_chunk_size):
        """浠庡墠鍑犱釜 chunk 涓鍑轰竴娈典笂涓嬫枃锛屼氦缁?LLM 璇嗗埆涓讳綋鍚嶇О銆?
        涓轰粈涔堜笉鏄妸鏁翠唤鏂囨。閮藉缁欐ā鍨嬶紵
        - 鎴愭湰鏇撮珮
        - 閫熷害鏇存參
        - 鍓嶅嚑涓?chunk 寰€寰€宸茬粡瓒冲鏆撮湶鏂囨。涓婚

        杩欎竴姝ョ殑鐩爣涓嶆槸鈥滆妯″瀷瀹屾暣璇诲畬鏁存湰鎵嬪唽鈥濓紝
        鑰屾槸缁欏畠瓒冲澶氱殑绾跨储鍘荤寽鍑衡€滆繖鏈墜鍐屼富瑕佽璋佲€濄€?        """
        total = 0
        final_context = []
        for index, chunk in enumerate(chunks[:item_name_chunks_k]):
            if not isinstance(chunk, dict):
                continue
            chunk_content = chunk.get('content')
            context = f'銆愬垏鐗囥€?{index}-{chunk_content}'

            if total + len(context) > item_name_chunk_size:
                break

            total += len(context)
            final_context.append(context)

        return '\n'.join(final_context)

    def _recognition_name(self, file_title, item_name_recognition_context):
        """鐢?LLM 璇嗗埆鏂囨。涓讳綋鍚嶇О銆?
        濡傛灉妯″瀷娌¤瘑鍒嚭鏉ワ紝鎴栬皟鐢ㄥけ璐ワ紝浼氶檷绾т娇鐢ㄦ枃浠舵爣棰樸€?        杩欐牱鍋氱殑鐩殑鏄細
        鍗充娇璇嗗埆鏁堟灉涓嶅畬缇庯紝瀵煎叆閾句篃灏介噺涓嶈涓柇銆?        """
        try:
            llm_client = AIClients.get_llm_client(response_format=False)
            user_prompt = ITEM_NAME_USER_PROMPT_TEMPLATE.format(
                file_title=file_title,
                context=item_name_recognition_context,
            )

            llm_response = llm_client.invoke([
                SystemMessage(content=ITEM_NAME_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ])

            llm_result = llm_response.content.strip()
            if not llm_result or llm_result == 'UNKNOWN':
                self.logger.info('LLM 鏈瘑鍒嚭鍟嗗搧鍚嶏紝闄嶇骇浣跨敤鏍囬: %s', file_title)
                return file_title

            self.logger.info('LLM 鎻愬彇鍒板晢鍝佸悕: %s', llm_result)
            return llm_result
        except Exception as e:
            self.logger.error('LLM 璋冪敤澶辫触锛岄檷绾т娇鐢ㄦ爣棰? %s锛屽紓甯? %s', file_title, e)
            return file_title

    def _embedding_item_name(self, item_name) -> tuple[Optional[list[float]], Optional[dict[int, float]]]:
        """鎶婅瘑鍒嚭鐨?item_name 涔熻浆鎴愬悜閲忋€?
        杩欎竴鐐瑰鏂版墜寰堝鏄撳拷鐣ワ細
        涓轰粈涔堚€滀竴涓晢鍝佸悕鈥濅篃瑕佸崟鐙仛 embedding锛?
        鍘熷洜鏄細
        鏌ヨ閾惧悗闈㈤渶瑕佺敤鐢ㄦ埛闂閲岀殑璁惧鍚嶃€佸瀷鍙峰悕銆佸埆鍚嶏紝
        鍘诲拰鐭ヨ瘑搴撻噷宸茬粡瀛樺湪鐨勬爣鍑嗗悕绉板仛鐩镐技鍖归厤銆?
        鎵€浠?item_name 涓嶆槸鍙瓨涓€浠界函鏂囨湰锛?        鑰屾槸浼氬悓鏃跺瓨锛?        - 鏂囨湰鍚嶇О
        - dense 鍚戦噺
        - sparse 鍚戦噺
        """
        try:
            embedding_provider = get_embedding_provider()
            records = embedding_provider.embed_texts(
                [item_name],
                text_type=TEXT_TYPE_DOCUMENT,
                dimension=self.config.embedding_dim,
            )
            if not records:
                return None, None
            return records[0].dense_vector, records[0].sparse_vector
        except Exception as e:
            self.logger.error('鍟嗗搧鍚嶈繙绋?embedding 澶辫触: %s', e)
            return None, None

    def _insert_milvus(self, file_title, item_name, dense_vector, sparse_vector, item_name_collection):
        """鎶婁富浣撳悕绉板啓鍏?`item_name_collection`銆?""
        if not dense_vector or sparse_vector is None:
            self.logger.error('鏂囨。 %s 瀵瑰簲鐨勫晢鍝佸悕 %s 鍚戦噺鐢熸垚涓嶅畬鏁?, file_title, item_name)
            return

        try:
            milvus_client = StorageClients.get_milvus_client()
        except Exception as e:
            self.logger.error('Milvus 瀹㈡埛绔垱寤哄け璐? %s', e)
            return

        try:
            if not milvus_client.has_collection(item_name_collection):
                self._create_item_name_collection(item_name_collection, milvus_client)

            data = {
                'file_title': file_title,
                'item_name': item_name,
                'dense_vector': dense_vector,
                'sparse_vector': sparse_vector,
            }
            result = milvus_client.insert(collection_name=item_name_collection, data=[data])
            self.logger.info('宸叉垚鍔熶繚瀛樺埌 Milvus锛孖D: %s', result['ids'][0])
        except Exception as e:
            self.logger.error('Milvus 鏁版嵁鎿嶄綔澶辫触: %s', e)

    def _create_item_name_collection(self, collection_name, milvus_client):
        """濡傛灉涓讳綋鍚嶇О闆嗗悎涓嶅瓨鍦紝灏辫嚜鍔ㄥ垱寤恒€?
        杩欐槸涓€涓€滆緟鍔╅泦鍚堚€濓紝瀹冨拰 chunks 闆嗗悎鐨勮亴璐ｄ笉涓€鏍凤細
        - chunks 闆嗗悎锛氬瓨姝ｆ枃鐗囨锛岀粰闂瓟妫€绱㈢敤
        - item_name 闆嗗悎锛氬瓨鏍囧噯涓讳綋鍚嶇О锛岀粰鍚嶇О纭鐢?        """
        schema = milvus_client.create_schema()

        # 涓婚敭浣跨敤 INT64 + auto_id锛岄伩鍏嶆墜鍔ㄦ嫾涓婚敭鎴栧鐞嗗瓧绗︿覆涓婚敭鍏煎闂銆?        schema.add_field(field_name='pk', datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name='file_title', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='item_name', datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=self.config.embedding_dim)
        schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)

        index_param = milvus_client.prepare_index_params()
        index_param.add_index(
            field_name='dense_vector',
            index_name='dense_vector_index',
            index_type='AUTOINDEX',
            metric_type='COSINE',
        )
        index_param.add_index(
            field_name='sparse_vector',
            index_name='sparse_vector_index',
            index_type='SPARSE_INVERTED_INDEX',
            metric_type='IP',
        )

        milvus_client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_param,
        )
        self.logger.info('闆嗗悎 %s 鍒涘缓鎴愬姛骞舵瀯寤轰簡绱㈠紩', collection_name)

    def _fill_item_name(self, item_name, state, chunks):
        """鎶婅瘑鍒嚭鐨?item_name 鍐欏洖姣忎釜 chunk 鍜?state銆?""
        for chunk in chunks:
            chunk['item_name'] = item_name

        state['item_name'] = item_name

