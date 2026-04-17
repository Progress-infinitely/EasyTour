from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from easytour.processor.query_process.main_graph import create_query_graph
from easytour.processor.query_process.nodes.alias_resolver_node import AliasResolverNode
from easytour.processor.query_process.nodes.hyde_search_node import HyDeSearchNode
from easytour.processor.query_process.nodes.intent_route_node import IntentRouteNode
from easytour.processor.query_process.nodes.item_name_confirm_node import ItemNameConfirmNode
from easytour.processor.query_process.nodes.mcp_search_node import McpSearchNode
from easytour.processor.query_process.nodes.rerank_node import RerankNode
from easytour.processor.query_process.nodes.rrf_node import RrfNode
from easytour.processor.query_process.nodes.structured_answer_node import StructuredAnswerNode
from easytour.processor.query_process.nodes.vector_search_node import VectorSearchNode


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


class _FakeAnswerLLMProvider:
    def get_client(self, response_format=False):
        return _FakeAnswerLLMClient()


class _FakeRerankProvider:
    def rerank(self, query, documents, top_n, task_instruction):
        return [SimpleNamespace(index=i, score=float(top_n - i)) for i, _ in enumerate(documents)]


class QuerySemanticParityTest(unittest.TestCase):
    def test_parallel_schedule_matches_stage2_semantic_pipeline(self):
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
        web_docs = [{'title': 'Web Title', 'snippet': 'web snippet', 'url': 'https://example.com'}]

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
                 return_value=web_docs,
             ), \
             patch('easytour.processor.query_process.nodes.rerank_node.get_rerank_provider', return_value=_FakeRerankProvider()), \
             patch(
                 'easytour.processor.query_process.nodes.structured_answer_node.get_llm_provider',
                 return_value=_FakeAnswerLLMProvider(),
             ):
            hyde_node = HyDeSearchNode()
            hyde_node.config.enable_hyde = True
            mcp_node = McpSearchNode()
            mcp_node.config.enable_web_search = True
            base_state = {
                'original_query': 'question',
                'history': [],
                'is_stream': False,
                'task_id': '',
                'session_id': 'session-1',
            }

            route_output = IntentRouteNode().process(deepcopy(base_state))
            alias_input = dict(base_state)
            alias_input.update(route_output)
            alias_output = AliasResolverNode().process(alias_input)

            confirm_input = dict(alias_input)
            confirm_input.update(alias_output)
            confirm_output = ItemNameConfirmNode().process(confirm_input)

            retrieval_input = dict(confirm_input)
            retrieval_input.update(confirm_output)

            vector_output = VectorSearchNode().process(retrieval_input)
            hyde_output = hyde_node.process(retrieval_input)
            mcp_output = mcp_node.process(retrieval_input)

            expected_rrf_input = dict(retrieval_input)
            expected_rrf_input.update(vector_output)
            expected_rrf_input.update(hyde_output)
            expected_rrf_output = RrfNode().process(expected_rrf_input)

            expected_rerank_input = dict(expected_rrf_input)
            expected_rerank_input.update(expected_rrf_output)
            expected_rerank_input.update(mcp_output)
            expected_rerank_output = RerankNode().process(expected_rerank_input)

            expected_answer_input = dict(expected_rerank_input)
            expected_answer_input.update(expected_rerank_output)
            expected_answer_output = StructuredAnswerNode().process(expected_answer_input)

            graph = create_query_graph()
            graph_output = graph.invoke(deepcopy(base_state))

        self.assertEqual(graph_output['rewritten_query'], expected_answer_input['rewritten_query'])
        self.assertEqual(graph_output['item_names'], confirm_output['item_names'])
        self.assertEqual(graph_output['embedding_chunks'], vector_output['embedding_chunks'])
        self.assertEqual(graph_output['hyde_embedding_chunks'], hyde_output['hyde_embedding_chunks'])
        self.assertEqual(graph_output['web_search_docs'], mcp_output['web_search_docs'])
        self.assertEqual(graph_output['rrf_chunks'], expected_rrf_output['rrf_chunks'])
        self.assertEqual(graph_output['reranked_chunk_ids'], expected_rerank_output['reranked_chunk_ids'])
        self.assertEqual(graph_output['answer'], expected_answer_output['answer'])
        self.assertEqual(graph_output['citations'], expected_answer_output['citations'])
        self.assertEqual(graph_output['structured_answer'], expected_answer_output['structured_answer'])


if __name__ == '__main__':
    unittest.main()
