from types import SimpleNamespace
import unittest
from unittest.mock import patch

from easytour.processor.query_process.config import get_config
from easytour.processor.query_process.main_graph import create_query_graph
from easytour.processor.query_process.nodes.alias_resolver_node import AliasResolverNode
from easytour.processor.query_process.nodes.intent_route_node import IntentRouteNode
from easytour.utils.task_util import clear_task


class _FakeEmbeddingRecord:
    dense_vector = [0.1, 0.2]
    sparse_vector = {1: 1.0}


class _FakeEmbeddingProvider:
    def embed_texts(self, texts, **_kwargs):
        return [_FakeEmbeddingRecord() for _ in texts]


class _FakeHydeLLMClient:
    def invoke(self, _messages):
        return SimpleNamespace(content='generated hyde document')


class _FakeHydeLLMProvider:
    def get_client(self, response_format=False):
        return _FakeHydeLLMClient()


class _FakeAnswerLLMClient:
    def invoke(self, _prompt):
        return SimpleNamespace(content='final answer from llm')

    def stream(self, _prompt):
        yield SimpleNamespace(content='final answer from llm')


class _FakeAnswerLLMProvider:
    def get_client(self, response_format=False):
        return _FakeAnswerLLMClient()


class _FakeRerankProvider:
    def rerank(self, query, documents, top_n, task_instruction):
        return [SimpleNamespace(index=i, score=float(top_n - i)) for i, _ in enumerate(documents)]


class QueryGraphBehaviorTest(unittest.TestCase):
    task_id = 'test-query-graph-behavior'

    def tearDown(self):
        clear_task(self.task_id, keep_result=False)

    def test_graph_invocation_preserves_behavior_with_parallel_retrieval(self):
        config = get_config()
        previous_enable_hyde = config.enable_hyde
        previous_enable_web_search = config.enable_web_search
        config.enable_hyde = True
        config.enable_web_search = True

        vector_hits = [
            {
                'entity': {
                    'chunk_id': 'v1',
                    'content': 'vector content',
                    'title': 'Vector Title',
                    'parent_title': 'Parent',
                    'file_title': 'Manual',
                    'item_name': 'Device-X',
                    'primary_item_name': 'Device-X',
                    'entity_names': ['Device-X'],
                    'document_id': 'doc-v1',
                    'city': 'Sanya',
                },
                'distance': 0.95,
            }
        ]
        hyde_hits = [
            {
                'entity': {
                    'chunk_id': 'h1',
                    'content': 'hyde content',
                    'title': 'HyDE Title',
                    'parent_title': 'Parent',
                    'file_title': 'Manual',
                    'item_name': 'Device-X',
                    'primary_item_name': 'Device-X',
                    'entity_names': ['Device-X'],
                    'document_id': 'doc-h1',
                    'city': 'Sanya',
                },
                'distance': 0.85,
            }
        ]
        item_name_hits = [
            {
                'entity': {
                    'item_name': 'Device-X',
                    'file_title': 'Manual',
                },
                'distance': 0.92,
            }
        ]

        try:
            with patch.object(
                IntentRouteNode,
                'process',
                autospec=True,
                return_value={
                    'retrieval_type': 'attraction',
                    'answer_intent': 'lookup',
                    'region_filter': {'province': '海南', 'city': '三亚', 'region_path': '海南/三亚'},
                    'rewritten_query': 'rewritten question',
                },
            ), \
                 patch.object(
                     AliasResolverNode,
                     'process',
                     autospec=True,
                     return_value={'resolved_aliases': [], 'rewritten_query': 'rewritten question'},
                 ), \
                 patch(
                     'easytour.processor.query_process.nodes.item_name_confirm_node.get_llm_provider',
                     return_value=SimpleNamespace(
                         get_client=lambda response_format=True: SimpleNamespace(
                             invoke=lambda _messages: SimpleNamespace(
                                 content={'item_names': ['Device-X'], 'rewritten_query': 'rewritten question'}
                             )
                         )
                     ),
                 ), \
                 patch('easytour.processor.query_process.nodes.item_name_confirm_node.get_embedding_provider', return_value=_FakeEmbeddingProvider()), \
                 patch('easytour.processor.query_process.nodes.item_name_confirm_node.hybrid_search', return_value=item_name_hits), \
                 patch('easytour.processor.query_process.nodes.vector_search_node.get_embedding_provider', return_value=_FakeEmbeddingProvider()), \
                 patch('easytour.processor.query_process.nodes.vector_search_node.build_milvus_expr', return_value='expr'), \
                 patch('easytour.processor.query_process.nodes.vector_search_node.hybrid_search', return_value=vector_hits), \
                 patch('easytour.processor.query_process.nodes.hyde_search_node.get_embedding_provider', return_value=_FakeEmbeddingProvider()), \
                 patch('easytour.processor.query_process.nodes.hyde_search_node.get_llm_provider', return_value=_FakeHydeLLMProvider()), \
                 patch('easytour.processor.query_process.nodes.hyde_search_node.build_milvus_expr', return_value='expr'), \
                 patch('easytour.processor.query_process.nodes.hyde_search_node.hybrid_search', return_value=hyde_hits), \
                 patch(
                     'easytour.processor.query_process.nodes.mcp_search_node.McpSearchNode._search_web',
                     autospec=True,
                     return_value=[{'title': 'Web Title', 'snippet': 'web snippet', 'url': 'https://example.com'}],
                 ), \
                 patch('easytour.processor.query_process.nodes.rerank_node.get_rerank_provider', return_value=_FakeRerankProvider()), \
                 patch(
                     'easytour.processor.query_process.nodes.structured_answer_node.get_llm_provider',
                     return_value=_FakeAnswerLLMProvider(),
                 ):
                graph = create_query_graph()
                result = graph.invoke(
                    {
                        'original_query': 'question',
                        'session_id': 'session-1',
                        'task_id': self.task_id,
                        'history': [],
                        'is_stream': False,
                    }
                )
        finally:
            config.enable_hyde = previous_enable_hyde
            config.enable_web_search = previous_enable_web_search

        self.assertEqual(result['retrieval_type'], 'attraction')
        self.assertEqual(result['answer_intent'], 'lookup')
        self.assertEqual(result['rewritten_query'], 'rewritten question')
        self.assertEqual(result['item_names'], ['Device-X'])
        self.assertEqual(result['embedding_chunks'][0]['chunk_id'], 'v1')
        self.assertEqual(result['hyde_embedding_chunks'][0]['chunk_id'], 'h1')
        self.assertEqual(result['web_search_docs'][0]['title'], 'Web Title')
        self.assertEqual(len(result['rrf_chunks']), 2)
        self.assertEqual(len(result['reranked_docs']), 3)
        self.assertEqual(result['answer'], 'final answer from llm')
        self.assertIn('doc-v1', {item['document_id'] for item in result['citations']})
        self.assertIn('vector content', result['prompt'])
        self.assertIn('hyde content', result['prompt'])


if __name__ == '__main__':
    unittest.main()
