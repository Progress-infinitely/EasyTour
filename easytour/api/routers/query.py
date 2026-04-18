from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse

from easytour.core.deps import get_query_service
from easytour.schema.query_schema import QueryRequest, QueryResponse, StreamSubmitResponse
from easytour.schema.task_schema import TaskStatusResponse
from easytour.services.query_service import QueryService
from easytour.services.task_status_service import build_task_status_payload
from easytour.utils.sse_util import sse_generator

router = APIRouter()


@router.post('/query')
async def query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    service: QueryService = Depends(get_query_service),
) -> dict[str, object]:
    session_id = request.session_id or service.generate_session_id()
    task_id = service.generate_task_id()

    if request.is_stream:
        service.submit_query(task_id, True)
        background_tasks.add_task(
            service.run_query,
            query=request.query,
            session_id=session_id,
            task_id=task_id,
            message_id=request.message_id,
            history=request.history,
            is_stream=True,
            retrieval_type=request.retrieval_type,
            region=request.region,
        )
        return StreamSubmitResponse(
            message='Query submitted',
            session_id=session_id,
            task_id=task_id,
        ).model_dump()

    final_state = service.run_query(
        query=request.query,
        session_id=session_id,
        task_id=task_id,
        message_id=request.message_id,
        history=request.history,
        is_stream=False,
        retrieval_type=request.retrieval_type,
        region=request.region,
    )
    status = build_task_status_payload(task_id)
    return QueryResponse(
        message='Query completed',
        session_id=session_id,
        task_id=task_id,
        rewritten_query=str(final_state.get('rewritten_query') or request.query),
        retrieval_type=str(final_state.get('retrieval_type') or request.retrieval_type or ''),
        answer_intent=str(final_state.get('answer_intent') or ''),
        region=dict(final_state.get('region_filter') or {}),
        item_names=list(final_state.get('item_names') or []),
        answer=str(final_state.get('answer') or ''),
        structured=dict(final_state.get('structured_answer') or {}),
        citations=list(final_state.get('citations') or []),
        done_list=list(status.get('done_list') or []),
        error=str(status.get('error') or ''),
        image_urls=list(status.get('image_urls') or []),
    ).model_dump()


@router.get('/stream/{task_id}')
async def stream(task_id: str, request: Request):
    return StreamingResponse(sse_generator(task_id, request), media_type='text/event-stream')


@router.get('/status/{task_id}')
async def get_status(task_id: str) -> dict[str, object]:
    return TaskStatusResponse(**build_task_status_payload(task_id)).model_dump()
