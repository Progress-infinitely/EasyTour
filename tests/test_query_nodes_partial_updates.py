from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
    def embed_texts(self, *_args, **_kwargs):
        return [_FakeEmbeddingRecord()]


class _FakeLLMClient:
    def invoke(self, _prompt):
        return SimpleNamespace(content='final answer')

    def stream(self, _prompt):
        yield SimpleNamespace(content='final ')
        yield SimpleNamespace(content='answer')


class _FakeLLMProvider:
    def get_client(self, response_format=False):
        return _FakeLLMClient()


class _FakeRerankProvider:
    def rerank(self, query, documents, top_n, task_instruction):
        return [SimpleNamespace(index=i, score=float(top_n - i)) for i, _ in enumerate(documents)]


class QueryNodePartialUpdateTest(unittest.TestCase):
    def test_intent_route_returns_stage2_route_fields(self):
        node = IntentRouteNode()
        with patch.object(
            node,
            '_route_with_llm',
            return_value={
                'retrieval_type': 'food',
                'answer_intent': 'recommendation',
                'region_filter': {'province': '海南', 'city': '三亚', 'region_path': '海南/三亚'},
                'rewritten_query': '三亚有什么值得推荐的美食',
            },
        ):
            result = node.process({'original_query': '三亚美食推荐', 'history': []})

        self.assertEqual(
            result,
            {
                'retrieval_type': 'food',
                'answer_intent': 'recommendation',
                'region_filter': {'province': '海南', 'city': '三亚', 'region_path': '海南/三亚'},
                'rewritten_query': '三亚有什么值得推荐的美食',
            },
        )

    def test_alias_resolver_returns_resolved_aliases_and_rewritten_query(self):
        node = AliasResolverNode()
        with patch.object(AliasResolverNode, '_load_alias_map', return_value={'天涯海角': '天涯海角游览区'}):
            result = node.process({'rewritten_query': '天涯海角门票多少钱'})

        self.assertEqual(result['resolved_aliases'], [{'alias': '天涯海角', 'canonical_name': '天涯海角游览区'}])
        self.assertIn('天涯海角游览区', result['rewritten_query'])

    def test_item_name_confirm_returns_only_owned_fields(self):
        node = ItemNameConfirmNode()
        with patch.object(node, '_extract_item_names', return_value=(['alias'], 'rewritten question')), \
             patch.object(node, '_align_item_names', return_value=('Device-X', ['Device-Y'], [{'matches': []}])):
            result = node.process({'original_query': 'question', 'history': []})

        self.assertEqual(
            result,
            {
                'rewritten_query': 'rewritten question',
                'item_names': ['Device-X', 'Device-Y'],
                'confirmed_item_name': 'Device-X',
                'candidate_item_names': ['Device-Y'],
                'item_name_candidates': [{'matches': []}],
            },
        )

    def test_vector_search_returns_stage2_retrieval_fields(self):
        node = VectorSearchNode()
        with patch('easytour.processor.query_process.nodes.vector_search_node.get_embedding_provider', return_value=_FakeEmbeddingProvider()), \
             patch('easytour.processor.query_process.nodes.vector_search_node.build_milvus_expr', return_value='expr'), \
             patch('easytour.processor.query_process.nodes.vector_search_node.hybrid_search', return_value=[
                 {
                     'entity': {
                         'chunk_id': 'c1',
                         'content': 'vector content',
                         'title': 'Title',
                         'parent_title': 'Parent',
                         'file_title': 'Manual',
                         'item_name': 'Device-X',
                         'primary_item_name': 'Device-X',
                         'entity_names': ['Device-X'],
                         'document_id': 'doc-1',
                         'source_label_display': 'Manual',
                         'city': 'Sanya',
                     },
                     'distance': 0.9,
                 }
             ]):
            result = node.process(
                {
                    'rewritten_query': 'question',
                    'retrieval_type': 'attraction',
                    'region_filter': {'province': '', 'city': 'Sanya', 'region_path': 'Sanya'},
                    'confirmed_item_name': 'Device-X',
                }
            )

        self.assertEqual(list(result.keys()), ['embedding_chunks', 'retrieval_filters', 'topk_chunk_ids', 'topk_scores'])
        self.assertEqual(result['retrieval_filters'], 'expr')
        self.assertEqual(result['embedding_chunks'][0]['content'], 'vector content')
        self.assertEqual(result['embedding_chunks'][0]['retrieval_source'], 'vector_search')
        self.assertEqual(result['topk_chunk_ids'], ['c1'])
        self.assertEqual(result['topk_scores'], [0.9])

    def test_hyde_search_disabled_returns_empty_partial_update(self):
        node = HyDeSearchNode()
        node.config.enable_hyde = False
        result = node.process({'rewritten_query': 'question', 'item_names': ['Device-X']})

        self.assertEqual(result, {'hyde_document': '', 'hyde_embedding_chunks': []})

    def test_mcp_search_disabled_returns_empty_partial_update(self):
        node = McpSearchNode()
        node.config.enable_web_search = False
        result = node.process({'rewritten_query': 'question', 'item_names': ['Device-X']})

        self.assertEqual(result, {'web_search_docs': []})

    def test_rrf_returns_rrf_chunks_only(self):
        node = RrfNode()
        result = node.process(
            {
                'embedding_chunks': [{'chunk_id': 'v1', 'content': 'vector', 'retrieval_source': 'vector_search'}],
                'hyde_embedding_chunks': [{'chunk_id': 'h1', 'content': 'hyde', 'retrieval_source': 'hyde_search'}],
            }
        )

        self.assertEqual(list(result.keys()), ['rrf_chunks'])
        self.assertEqual(len(result['rrf_chunks']), 2)

    def test_rerank_returns_reranked_docs_and_chunk_ids(self):
        node = RerankNode()
        with patch('easytour.processor.query_process.nodes.rerank_node.get_rerank_provider', return_value=_FakeRerankProvider()):
            result = node.process(
                {
                    'rewritten_query': 'question',
                    'candidate_item_names': [],
                    'confirmed_item_name': '',
                    'rrf_chunks': [{'chunk_id': 'r1', 'content': 'local content', 'title': 'Local'}],
                    'web_search_docs': [{'title': 'Web', 'snippet': 'web content', 'url': 'https://example.com'}],
                }
            )

        self.assertEqual(set(result.keys()), {'reranked_docs', 'reranked_chunk_ids'})
        self.assertEqual(len(result['reranked_docs']), 2)
        self.assertEqual(result['reranked_chunk_ids'], ['r1'])
        self.assertIn('score', result['reranked_docs'][0])

    def test_structured_answer_returns_prompt_answer_structured_and_citations(self):
        node = StructuredAnswerNode()
        with patch('easytour.processor.query_process.nodes.structured_answer_node.get_llm_provider', return_value=_FakeLLMProvider()):
            result = node.process(
                {
                    'original_query': 'question',
                    'answer_intent': 'lookup',
                    'reranked_docs': [
                        {
                            'content': 'context content',
                            'title': 'Doc 1',
                            'item_name': 'Device-X',
                            'source_label_display': 'Doc 1',
                            'document_id': 'doc-1',
                            'city': 'Sanya',
                        }
                    ],
                    'history': [{'role': 'user', 'text': 'earlier question'}],
                    'item_names': ['Device-X'],
                    'is_stream': False,
                }
            )

        self.assertEqual(set(result.keys()), {'prompt', 'answer', 'structured_answer', 'citations'})
        self.assertEqual(result['answer'], 'final answer')
        self.assertEqual(result['structured_answer']['facts']['matched_items'], ['Device-X'])
        self.assertEqual(result['citations'][0]['document_id'], 'doc-1')
        self.assertIn('context content', result['prompt'])


if __name__ == '__main__':
    unittest.main()
