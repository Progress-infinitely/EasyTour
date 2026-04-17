from __future__ import annotations

import copy
from typing import Any, TypedDict


class QueryGraphState(TypedDict, total=False):
    session_id: str
    task_id: str
    message_id: str

    original_query: str
    rewritten_query: str
    retrieval_type: str
    answer_intent: str
    region_filter: dict[str, str]
    resolved_aliases: list[dict[str, str]]

    item_names: list[str]
    confirmed_item_name: str
    candidate_item_names: list[str]
    item_name_candidates: list[dict[str, Any]]

    embedding_chunks: list[dict[str, Any]]
    hyde_embedding_chunks: list[dict[str, Any]]
    web_search_docs: list[dict[str, Any]]
    hyde_document: str

    rrf_chunks: list[dict[str, Any]]
    reranked_docs: list[dict[str, Any]]

    history: list[dict[str, Any]]
    prompt: str
    answer: str
    structured_answer: dict[str, Any]
    citations: list[dict[str, Any]]

    retrieval_filters: str
    topk_chunk_ids: list[Any]
    topk_scores: list[float]
    reranked_chunk_ids: list[Any]
    latency_ms: dict[str, int]

    is_stream: bool


DEFAULT_STATE: QueryGraphState = {
    'session_id': '',
    'task_id': '',
    'message_id': '',
    'original_query': '',
    'rewritten_query': '',
    'retrieval_type': '',
    'answer_intent': '',
    'region_filter': {'province': '', 'city': '', 'region_path': ''},
    'resolved_aliases': [],
    'item_names': [],
    'confirmed_item_name': '',
    'candidate_item_names': [],
    'item_name_candidates': [],
    'embedding_chunks': [],
    'hyde_embedding_chunks': [],
    'web_search_docs': [],
    'hyde_document': '',
    'rrf_chunks': [],
    'reranked_docs': [],
    'history': [],
    'prompt': '',
    'answer': '',
    'structured_answer': {},
    'citations': [],
    'retrieval_filters': '',
    'topk_chunk_ids': [],
    'topk_scores': [],
    'reranked_chunk_ids': [],
    'latency_ms': {},
    'is_stream': False,
}


def create_default_state(**overrides: Any) -> QueryGraphState:
    state = copy.deepcopy(DEFAULT_STATE)
    state.update(overrides)
    return state


def get_default_state() -> QueryGraphState:
    return copy.deepcopy(DEFAULT_STATE)
