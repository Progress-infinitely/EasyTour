from __future__ import annotations

import asyncio
import json
from typing import Any

from easytour.processor.query_process.base import BaseNode
from easytour.processor.query_process.exceptions import ConfigurationError, StateFieldError
from easytour.processor.query_process.state import QueryGraphState

try:
    from agents.mcp import MCPServerStreamableHttp
except Exception:  # pragma: no cover
    MCPServerStreamableHttp = None


class McpSearchNode(BaseNode):
    name = 'mcp_search_node'

    def process(self, state: QueryGraphState) -> QueryGraphState:
        if not self.config.enable_web_search:
            return {'web_search_docs': []}

        rewritten_query = str(state.get('rewritten_query') or state.get('original_query') or '').strip()
        item_names = list(state.get('item_names') or [])
        if not rewritten_query:
            raise StateFieldError(node_name=self.name, field_name='rewritten_query', expected_type=str)

        # [修改] 没有主体约束时先跳过联网检索，避免把噪音网页带进二阶段主链。
        if not item_names:
            self.logger.info('No confirmed item names, skip MCP web search')
            return {'web_search_docs': []}

        try:
            web_search_docs = asyncio.run(self._search_web(query=rewritten_query))
        except Exception as exc:
            self.logger.warning('MCP web search unavailable, fallback to empty result: %s', exc)
            web_search_docs = []
        return {'web_search_docs': web_search_docs}

    async def _search_web(self, *, query: str) -> list[dict[str, str]]:
        if MCPServerStreamableHttp is None:
            raise ConfigurationError('openai-agents is required for MCP web search', node_name=self.name)

        url = self._normalize_mcp_url(self.config.mcp_dashscope_base_url)
        if not url:
            raise ConfigurationError('MCP_DASHSCOPE_BASE_URL is required when ENABLE_WEB_SEARCH=true', node_name=self.name)
        if not self.config.openai_api_key:
            raise ConfigurationError('OPENAI_API_KEY is required for MCP web search', node_name=self.name)

        mcp_client = MCPServerStreamableHttp(
            name='web_search',
            params={
                'url': url,
                'headers': {'Authorization': f'Bearer {self.config.openai_api_key}'},
            },
            cache_tools_list=True,
        )

        try:
            await mcp_client.connect()
            result = await mcp_client.call_tool(
                tool_name='bailian_web_search',
                arguments={'query': query, 'count': 3},
            )
            return self._parse_mcp_result(result)
        finally:
            await mcp_client.cleanup()

    def _normalize_mcp_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url:
            return ''
        if url.endswith('/sse'):
            return url[:-4] + '/mcp'
        if url.endswith('/mcp'):
            return url
        if '/api/v1/mcps/' in url:
            return url.rstrip('/') + '/mcp'
        return url

    def _parse_mcp_result(self, result: Any) -> list[dict[str, str]]:
        if not result or not getattr(result, 'content', None):
            return []

        first_item = result.content[0]
        raw_text = getattr(first_item, 'text', '')
        if not raw_text:
            return []

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            self.logger.warning('Invalid MCP web search payload')
            return []

        pages = payload.get('pages')
        if not isinstance(pages, list):
            return []

        docs: list[dict[str, str]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            docs.append(
                {
                    'title': str(page.get('title') or '').strip(),
                    'snippet': str(page.get('snippet') or '').strip(),
                    'url': str(page.get('url') or '').strip(),
                }
            )
        return docs


__all__ = ['McpSearchNode']
