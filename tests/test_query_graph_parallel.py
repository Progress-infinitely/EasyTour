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
from easytour.utils.task_util import clear_task


class QueryGraphParallelTopologyTest(unittest.TestCase):
    def test_parallel_fanout_and_fanin_edges_exist(self):
        graph = create_query_graph().get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        # [修改] 二阶段图入口已经切到 intent_route -> alias_resolver -> item_name_confirm。
        self.assertIn(('intent_route', 'alias_resolver'), edges)
        self.assertIn(('alias_resolver', 'item_name_confirm'), edges)
        self.assertIn(('item_name_confirm', 'vector_search'), edges)
        self.assertIn(('item_name_confirm', 'hyde_search'), edges)
        self.assertIn(('item_name_confirm', 'mcp_search'), edges)
        self.assertIn(('vector_search', 'rrf'), edges)
        self.assertIn(('hyde_search', 'rrf'), edges)
        self.assertIn(('rrf', 'rerank'), edges)
        self.assertIn(('mcp_search', 'rerank'), edges)
        self.assertIn(('rerank', 'structured_answer'), edges)

        self.assertNotIn(('vector_search', 'hyde_search'), edges)
        self.assertNotIn(('hyde_search', 'mcp_search'), edges)
        self.assertNotIn(('mcp_search', 'rrf'), edges)


class QueryGraphParallelMergeTest(unittest.TestCase):
    task_id = 'test-query-graph-parallel-merge'

    def tearDown(self):
        clear_task(self.task_id, keep_result=False)

    def test_parallel_branch_updates_are_merged_before_rrf(self):
        def fake_intent(_self, state):
            return {
                'retrieval_type': 'attraction',
                'answer_intent': 'lookup',
                'region_filter': {'province': '海南', 'city': '三亚', 'region_path': '海南/三亚'},
                'rewritten_query': f"rewritten::{state['original_query']}",
            }

        def fake_alias(_self, state):
            self.assertEqual(state['rewritten_query'], 'rewritten::question')
            return {
                'resolved_aliases': [{'alias': '别名', 'canonical_name': 'Device-X'}],
                'rewritten_query': 'rewritten::question',
            }

        def fake_item_name_confirm(_self, state):
            self.assertEqual(state['resolved_aliases'][0]['canonical_name'], 'Device-X')
            return {
                'rewritten_query': 'rewritten::question',
                'item_names': ['Device-X'],
                'confirmed_item_name': 'Device-X',
                'candidate_item_names': ['Device-Y'],
                'item_name_candidates': [],
            }

        def fake_vector(_self, _state):
            return {
                'embedding_chunks': [{'chunk_id': 'v1', 'content': 'vector content'}],
                'retrieval_filters': 'expr',
                'topk_chunk_ids': ['v1'],
                'topk_scores': [0.9],
            }

        def fake_hyde(_self, _state):
            return {
                'hyde_document': 'hyde doc',
                'hyde_embedding_chunks': [{'chunk_id': 'h1', 'content': 'hyde content'}],
            }

        def fake_mcp(_self, _state):
            return {'web_search_docs': [{'title': 'web', 'snippet': 'web snippet', 'url': 'https://example.com'}]}

        def fake_rrf(_self, state):
            self.assertEqual(state['embedding_chunks'], [{'chunk_id': 'v1', 'content': 'vector content'}])
            self.assertEqual(state['hyde_document'], 'hyde doc')
            self.assertEqual(state['hyde_embedding_chunks'], [{'chunk_id': 'h1', 'content': 'hyde content'}])
            self.assertEqual(
                state['web_search_docs'],
                [{'title': 'web', 'snippet': 'web snippet', 'url': 'https://example.com'}],
            )
            return {'rrf_chunks': [{'chunk_id': 'r1', 'content': 'rrf content'}]}

        def fake_rerank(_self, state):
            self.assertEqual(state['rrf_chunks'], [{'chunk_id': 'r1', 'content': 'rrf content'}])
            self.assertEqual(len(state['web_search_docs']), 1)
            return {'reranked_docs': [{'chunk_id': 'r1', 'content': 'reranked content'}], 'reranked_chunk_ids': ['r1']}

        def fake_answer(_self, state):
            self.assertEqual(state['reranked_docs'], [{'chunk_id': 'r1', 'content': 'reranked content'}])
            return {
                'prompt': 'prompt text',
                'answer': 'final answer',
                'structured_answer': {'answer': 'final answer'},
                'citations': [],
            }

        with patch.object(IntentRouteNode, 'process', autospec=True, side_effect=fake_intent), \
             patch.object(AliasResolverNode, 'process', autospec=True, side_effect=fake_alias), \
             patch.object(ItemNameConfirmNode, 'process', autospec=True, side_effect=fake_item_name_confirm), \
             patch.object(VectorSearchNode, 'process', autospec=True, side_effect=fake_vector), \
             patch.object(HyDeSearchNode, 'process', autospec=True, side_effect=fake_hyde), \
             patch.object(McpSearchNode, 'process', autospec=True, side_effect=fake_mcp), \
             patch.object(RrfNode, 'process', autospec=True, side_effect=fake_rrf), \
             patch.object(RerankNode, 'process', autospec=True, side_effect=fake_rerank), \
             patch.object(StructuredAnswerNode, 'process', autospec=True, side_effect=fake_answer):
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

        self.assertEqual(result['rewritten_query'], 'rewritten::question')
        self.assertEqual(result['item_names'], ['Device-X'])
        self.assertEqual(result['embedding_chunks'], [{'chunk_id': 'v1', 'content': 'vector content'}])
        self.assertEqual(result['hyde_embedding_chunks'], [{'chunk_id': 'h1', 'content': 'hyde content'}])
        self.assertEqual(result['web_search_docs'][0]['title'], 'web')
        self.assertEqual(result['rrf_chunks'], [{'chunk_id': 'r1', 'content': 'rrf content'}])
        self.assertEqual(result['reranked_docs'], [{'chunk_id': 'r1', 'content': 'reranked content'}])
        self.assertEqual(result['structured_answer'], {'answer': 'final answer'})
        self.assertEqual(result['answer'], 'final answer')


if __name__ == '__main__':
    unittest.main()
