from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from easytour.core.deps import get_document_service
from easytour.schema.document_schema import DocumentMetadataResponse
from easytour.services.document_preview_service import (
    build_preview_html,
    build_preview_not_found_html,
    prepare_preview_document,
)
from easytour.services.document_service import DocumentService
from easytour.services.source_open_service import open_source_target

router = APIRouter()


@router.get('/documents/{document_id}/preview')
async def preview_document_chunks(
    document_id: str,
    chunk_id: str | None = None,
    service: DocumentService = Depends(get_document_service),
) -> HTMLResponse:
    document = service.get_document(document_id)
    if document is None:
        return HTMLResponse(build_preview_not_found_html(document_id), status_code=404)
    preview_document = prepare_preview_document(
        document,
        chunk_id=chunk_id,
        chunks_collection=str(service._chunks_collection),
    )
    return HTMLResponse(build_preview_html(preview_document, chunk_id=chunk_id))


@router.get('/documents/{document_id}')
async def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict[str, object]:
    document = service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail='document not found')
    return DocumentMetadataResponse(**document).model_dump()


@router.post('/documents/{document_id}/open')
async def open_document_source(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict[str, str]:
    document = service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail='document not found')

    source_target = str(document.get('source_uri_internal') or '').strip()
    if not source_target:
        raise HTTPException(status_code=404, detail='document source not found')

    try:
        result = open_source_target(source_target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'failed to open source: {exc}') from exc

    return {'message': 'source opened', **result}
