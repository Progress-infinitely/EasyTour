from __future__ import annotations

import threading
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI

from easytour.utils.client.base import BaseClientManager, logger

load_dotenv()


class AIClients(BaseClientManager):
    """AI 瀹㈡埛绔鐞嗗櫒銆?
    杩欎釜绫荤粺涓€绠＄悊涓ょ被瀹㈡埛绔細
    1. `OpenAI` 鍘熺敓瀹㈡埛绔細涓昏缁?VLM 鎴栫洿鎺ヨ蛋鍏煎鎺ュ彛鐨勫満鏅娇鐢ㄣ€?    2. `ChatOpenAI` LangChain 瀹㈡埛绔細涓昏缁欓」鐩噷鐨?LLM 鑺傜偣璋冪敤銆?
    杩欏眰鍜?provider 灞傜殑鍖哄埆锛屽彲浠ュ厛杩欐牱鐞嗚В锛?    - provider 灞傦細鏇村叧蹇冣€滀笟鍔¤兘鍔涘皝瑁呪€濓紝渚嬪 embedding銆乺erank銆乴lm 鎺ュ彛鎬庝箞瀵瑰鏆撮湶
    - client 灞傦細鏇村叧蹇冣€滃簳灞?SDK 瀹㈡埛绔€庝箞鍒涘缓鍜屽鐢ㄢ€?
    鎵€浠?client 鏇村儚鈥滃簳灞傚伐鍏风鐞嗗憳鈥濓紝provider 鏇村儚鈥滀笟鍔¤兘鍔涘寘瑁呭眰鈥濄€?    """

    _openai_client: Optional[OpenAI] = None
    _openai_lock = threading.Lock()

    # JSON 妯″紡鍜屾櫘閫氭枃鏈ā寮忓垎鍒紦瀛橈紝
    # 鍥犱负瀹冧滑鐨?`model_kwargs` 涓嶄竴鏍凤紝涓嶈兘绠€鍗曞叡鐢ㄥ悓涓€涓疄渚嬨€?    _openai_llm_json_client: Optional[ChatOpenAI] = None
    _openai_llm_json_lock = threading.Lock()

    _openai_llm_plain_client: Optional[ChatOpenAI] = None
    _openai_llm_plain_lock = threading.Lock()

    @classmethod
    def get_vlm_client(cls) -> OpenAI:
        """杩斿洖 VLM / OpenAI 鍏煎瀹㈡埛绔崟渚嬨€?
        杩欎釜瀹㈡埛绔洿鍋忓簳灞傚師鐢熻皟鐢ㄩ鏍硷紝
        涓昏閫傚悎鍥惧儚鐩稿叧鎴栭渶瑕佽嚜宸辨帶鍒惰姹傜粨鏋勭殑鍦烘櫙銆?        """
        return cls._get_or_create('_openai_client', cls._openai_lock, cls._create_vlm_client)

    @classmethod
    def _create_vlm_client(cls) -> OpenAI:
        """鐪熸鍒涘缓搴曞眰 OpenAI 瀹㈡埛绔€?""
        try:
            api_key = cls._require_env('OPENAI_API_KEY')
            base_url = cls._require_env('OPENAI_API_BASE')

            client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info('OpenAI 瀹㈡埛绔垵濮嬪寲瀹屾垚 (base_url=%s)', base_url)
            return client
        except EnvironmentError:
            raise
        except Exception as e:
            logger.error('OpenAI 瀹㈡埛绔垵濮嬪寲澶辫触: %s', e)
            raise ConnectionError(f'OpenAI 杩炴帴澶辫触: {e}') from e

    @classmethod
    def get_llm_client(cls, response_format: bool = True) -> ChatOpenAI:
        """杩斿洖 LangChain LLM 瀹㈡埛绔€?
        鍙傛暟璇存槑锛?        - `response_format=True`锛氳姹傛ā鍨嬭緭鍑?JSON 瀵硅薄
          閫傚悎鈥滀富浣撳悕绉拌瘑鍒€佺粨鏋勫寲鎻愬彇鈥濊繖绫婚渶瑕佺ǔ瀹氬瓧娈电殑鍦烘櫙
        - `response_format=False`锛氭櫘閫氭枃鏈ā寮?          閫傚悎鑷敱鐢熸垚锛屾瘮濡傛渶缁堝洖绛斻€丠yDE 鏂囨湰鐢熸垚

        涓轰粈涔堣繖閲岃鍒嗕袱绉嶇紦瀛橈紵
        鍥犱负 JSON 妯″紡鍜屾櫘閫氭ā寮忓簳灞傞厤缃笉鍚岋紝
        娣风敤鍚屼竴涓鎴风瀹炰緥浼氳琛屼负涓嶇ǔ瀹氥€?        """
        if response_format:
            return cls._get_or_create(
                '_openai_llm_json_client',
                cls._openai_llm_json_lock,
                lambda: cls._create_llm_client(response_format=True),
            )
        return cls._get_or_create(
            '_openai_llm_plain_client',
            cls._openai_llm_plain_lock,
            lambda: cls._create_llm_client(response_format=False),
        )

    @classmethod
    def _create_llm_client(cls, response_format: bool) -> ChatOpenAI:
        """鐪熸鍒涘缓 LangChain 鐨?ChatOpenAI 瀹㈡埛绔€?""
        try:
            api_key = cls._require_env('OPENAI_API_KEY')
            base_url = cls._require_env('OPENAI_API_BASE')
            model_name = cls._require_env('LLM_DEFAULT_MODEL')

            model_kwargs = {}
            if response_format:
                model_kwargs['response_format'] = {'type': 'json_object'}

            llm_client = ChatOpenAI(
                model_name=model_name,
                temperature=0,
                openai_api_key=api_key,
                openai_api_base=base_url,
                model_kwargs=model_kwargs,
            )
            logger.info('OpenAI LLM 瀹㈡埛绔垵濮嬪寲瀹屾垚 response_format=%s', response_format)
            return llm_client
        except EnvironmentError:
            raise
        except Exception as e:
            raise ConnectionError(f'OpenAI 杩炴帴澶辫触: {e}') from e

