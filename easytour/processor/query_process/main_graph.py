from __future__ import annotations

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from easytour.processor.query_process.nodes.alias_resolver_node import AliasResolverNode
from easytour.processor.query_process.nodes.hyde_search_node import HyDeSearchNode
from easytour.processor.query_process.nodes.intent_route_node import IntentRouteNode
from easytour.processor.query_process.nodes.item_name_confirm_node import ItemNameConfirmNode
from easytour.processor.query_process.nodes.mcp_search_node import McpSearchNode
from easytour.processor.query_process.nodes.rerank_node import RerankNode
from easytour.processor.query_process.nodes.rrf_node import RrfNode
from easytour.processor.query_process.nodes.structured_answer_node import StructuredAnswerNode
from easytour.processor.query_process.nodes.vector_search_node import VectorSearchNode
from easytour.processor.query_process.state import QueryGraphState

load_dotenv()


def create_query_graph() -> CompiledStateGraph:
    workflow = StateGraph(QueryGraphState)  # type: ignore[arg-type]
    workflow.add_node('intent_route', IntentRouteNode())
    workflow.add_node('alias_resolver', AliasResolverNode())
    workflow.add_node('item_name_confirm', ItemNameConfirmNode())
    workflow.add_node('vector_search', VectorSearchNode())
    workflow.add_node('hyde_search', HyDeSearchNode())
    workflow.add_node('mcp_search', McpSearchNode())
    workflow.add_node('rrf', RrfNode())
    workflow.add_node('rerank', RerankNode())
    workflow.add_node('structured_answer', StructuredAnswerNode())

    workflow.set_entry_point('intent_route')
    workflow.add_edge('intent_route', 'alias_resolver')
    workflow.add_edge('alias_resolver', 'item_name_confirm')
    workflow.add_edge('item_name_confirm', 'vector_search')
    workflow.add_edge('item_name_confirm', 'hyde_search')
    workflow.add_edge('item_name_confirm', 'mcp_search')
    workflow.add_edge(['vector_search', 'hyde_search'], 'rrf')
    workflow.add_edge(['rrf', 'mcp_search'], 'rerank')
    workflow.add_edge('rerank', 'structured_answer')
    workflow.add_edge('structured_answer', END)
    return workflow.compile()


query_app = create_query_graph()
