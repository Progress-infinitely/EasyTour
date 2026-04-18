from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from easytour.core.deps import get_query_service
from easytour.services.query_service import QueryService

router = APIRouter()


@router.get('/history/{session_id}')
async def get_history(
    session_id: str,
    limit: int = 50,
    service: QueryService = Depends(get_query_service),
) -> dict[str, object]:
    return {
        'session_id': session_id,
        'items': service.get_history(session_id, limit),
    }


@router.delete('/history/{session_id}')
async def clear_chat_history(
    session_id: str,
    service: QueryService = Depends(get_query_service),
) -> dict[str, object]:
    try:
        deleted_count = service.clear_history(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'history error: {exc}') from exc
    return {'message': 'History cleared', 'deleted_count': deleted_count}
