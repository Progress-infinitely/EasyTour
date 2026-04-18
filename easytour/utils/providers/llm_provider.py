from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from easytour.core.config import get_shared_config
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
        config = get_shared_config()
        api_key = config.provider_api_key
        if not api_key:
            raise ProviderConfigError('OPENAI_API_KEY or DASHSCOPE_API_KEY is required')

        resolved_model_name = (
            model_name
            or config.item_model
            or config.llm_default_model
            or config.model
            or 'qwen-flash'
        )
        base_url = (
            config.openai_api_base
            or config.dashscope_compatible_api_base
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
