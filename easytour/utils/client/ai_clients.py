from __future__ import annotations

import threading
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI

from easytour.utils.client.base import BaseClientManager, logger

load_dotenv()


class AIClients(BaseClientManager):
    """统一管理 OpenAI 原生客户端和 LangChain 客户端。"""

    _openai_client: Optional[OpenAI] = None
    _openai_lock = threading.Lock()

    # [修改] JSON 模式和普通文本模式分开缓存，避免 model_kwargs 相互污染。
    _openai_llm_json_client: Optional[ChatOpenAI] = None
    _openai_llm_json_lock = threading.Lock()

    _openai_llm_plain_client: Optional[ChatOpenAI] = None
    _openai_llm_plain_lock = threading.Lock()

    @classmethod
    def get_vlm_client(cls) -> OpenAI:
        """返回原生 OpenAI 客户端，供图片/VLM 场景使用。"""
        return cls._get_or_create('_openai_client', cls._openai_lock, cls._create_vlm_client)

    @classmethod
    def _create_vlm_client(cls) -> OpenAI:
        """创建原生 OpenAI 客户端。"""
        try:
            api_key = cls._require_env('OPENAI_API_KEY')
            base_url = cls._require_env('OPENAI_API_BASE')

            client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info('OpenAI client initialized (base_url=%s)', base_url)
            return client
        except EnvironmentError:
            raise
        except Exception as exc:
            logger.error('failed to initialize OpenAI client: %s', exc)
            raise ConnectionError(f'OpenAI 连接失败: {exc}') from exc

    @classmethod
    def get_llm_client(cls, response_format: bool = True) -> ChatOpenAI:
        """返回 LangChain ChatOpenAI 客户端。"""
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
        """创建 LangChain ChatOpenAI 客户端。"""
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
            logger.info('OpenAI LLM client initialized response_format=%s', response_format)
            return llm_client
        except EnvironmentError:
            raise
        except Exception as exc:
            raise ConnectionError(f'OpenAI 连接失败: {exc}') from exc
