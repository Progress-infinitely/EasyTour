from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from easytour.utils.providers.base import ProviderConfigError

load_dotenv()


class DashScopeLLMProvider:
    def __init__(self):
        self._cache: dict[tuple[str, float, bool], ChatOpenAI] = {}

    def get_client(
        self,
        *,
        model_name: str | None = None,
        temperature: float = 0.0,
        response_format: bool = False,
    ) -> ChatOpenAI:
        api_key = os.getenv('OPENAI_API_KEY') or os.getenv('DASHSCOPE_API_KEY')
        if not api_key:
            raise ProviderConfigError('OPENAI_API_KEY or DASHSCOPE_API_KEY is required')

        resolved_model_name = (
            model_name
            or os.getenv('ITEM_MODEL')
            or os.getenv('LLM_DEFAULT_MODEL')
            or 'qwen-flash'
        )
        base_url = (
            os.getenv('OPENAI_API_BASE')
            or os.getenv('DASHSCOPE_COMPAT_BASE_URL')
            or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        )

        cache_key = (resolved_model_name, temperature, response_format)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        model_kwargs: dict[str, Any] = {}
        if response_format:
            # [修改] 主体抽取、路由等结构化场景统一走 JSON 输出约束。
            model_kwargs['response_format'] = {'type': 'json_object'}

        client = ChatOpenAI(
            model_name=resolved_model_name,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=temperature,
            extra_body={'enable_thinking': False},
            model_kwargs=model_kwargs,
        )
        self._cache[cache_key] = client
        return client
