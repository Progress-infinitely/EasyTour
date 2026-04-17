from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from easytour.core.deps import (
    get_document_service,
    get_import_file_service,
    get_meta_service,
    get_query_service,
)
from easytour.core.paths import get_front_page_dir
from easytour.schema.document_schema import DocumentMetadataResponse
from easytour.schema.query_schema import QueryRequest, QueryResponse, StreamSubmitResponse
from easytour.schema.task_schema import TaskStatusResponse
from easytour.schema.upload_schema import UploadForceMode, UploadOverride, UploadResponse, UploadStatus
from easytour.services.document_service import DocumentService
from easytour.services.import_file_service import ImportFileService
from easytour.services.meta_service import MetaService
from easytour.services.query_service import QueryService
from easytour.utils.client.storage_clients import StorageClients
from easytour.utils.sse_util import sse_generator
from easytour.utils.task_util import (
    get_done_task_list,
    get_running_task_list,
    get_task_result,
    get_task_status,
)


def build_task_status_payload(task_id: str) -> dict[str, object]:
    return {
        'task_id': task_id,
        'status': get_task_status(task_id),
        'done_list': get_done_task_list(task_id),
        'running_list': get_running_task_list(task_id),
        'answer': str(get_task_result(task_id, 'answer', '') or ''),
        'error': str(get_task_result(task_id, 'error', '') or ''),
        'image_urls': list(get_task_result(task_id, 'image_urls', []) or []),
        'citations': list(get_task_result(task_id, 'citations', []) or []),
        'file_title': str(get_task_result(task_id, 'file_title', '') or ''),
        'item_name': str(get_task_result(task_id, 'item_name', '') or ''),
        'chunk_count': int(get_task_result(task_id, 'chunk_count', 0) or 0),
        'document_id': str(get_task_result(task_id, 'document_id', '') or ''),
        'region_path': str(get_task_result(task_id, 'region_path', '') or ''),
        'doc_main_entities': list(get_task_result(task_id, 'doc_main_entities', []) or []),
    }


def _launch_local_path(target_path: Path) -> None:
    normalized_path = str(target_path)
    if os.name == 'nt':
        os.startfile(normalized_path)  # type: ignore[attr-defined]
        return
    if sys.platform == 'darwin':
        subprocess.Popen(['open', normalized_path])
        return
    subprocess.Popen(['xdg-open', normalized_path])


def open_source_target(source_target: str) -> dict[str, str]:
    normalized_target = str(source_target or '').strip()
    if not normalized_target:
        raise FileNotFoundError('source target is empty')

    parsed = urlparse(normalized_target)
    if parsed.scheme in {'http', 'https'}:
        webbrowser.open(normalized_target, new=2)
        return {'target_type': 'url'}

    if parsed.scheme == 'file':
        normalized_target = unquote(parsed.path or '')
        if parsed.netloc:
            normalized_target = f'//{parsed.netloc}{normalized_target}'

    local_path = Path(normalized_target).expanduser()
    if not local_path.exists():
        raise FileNotFoundError(f'source file not found: {local_path}')

    _launch_local_path(local_path)
    return {'target_type': 'file'}


def create_app() -> FastAPI:
    app = FastAPI(title='EasyTour Service')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    front_page_dir = get_front_page_dir()
    if os.path.exists(front_page_dir):
        app.mount('/front', StaticFiles(directory=front_page_dir), name='front')

    @app.get('/')
    def read_root() -> dict[str, object]:
        return {
            'message': 'EasyTour service is running',
            'chat_page': '/chat.html',
            'import_page': '/import',
            'docs': '/docs',
        }

    @app.get('/healthz')
    def healthz(
        document_service: DocumentService = Depends(get_document_service),
    ) -> dict[str, object]:
        return {
            'status': 'ok',
            'mongo_connected': document_service.is_mongo_connected(),
            'milvus_connected': _check_milvus_connected(),
            'minio_connected': _check_minio_connected(),
        }

    @app.get('/chat.html')
    async def chat_page() -> FileResponse:
        return FileResponse(os.path.join(front_page_dir, 'chat.html'))

    @app.get('/import')
    @app.get('/import.html')
    async def import_page() -> FileResponse:
        return FileResponse(os.path.join(front_page_dir, 'import.html'))

    @app.get('/meta/content_types')
    async def get_content_types(
        service: MetaService = Depends(get_meta_service),
    ) -> list[dict[str, str]]:
        return [item.model_dump() for item in service.get_content_types()]

    @app.get('/meta/regions')
    async def get_regions(
        service: MetaService = Depends(get_meta_service),
    ) -> list[dict[str, str]]:
        return [item.model_dump() for item in service.get_regions()]

    @app.get('/meta/items')
    async def get_items(
        service: MetaService = Depends(get_meta_service),
    ) -> list[dict[str, str]]:
        return [item.model_dump() for item in service.get_items()]

    @app.get('/documents/{document_id}')
    async def get_document(
        document_id: str,
        service: DocumentService = Depends(get_document_service),
    ) -> dict[str, object]:
        document = service.get_document(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail='document not found')
        return DocumentMetadataResponse(**document).model_dump()

    @app.post('/documents/{document_id}/open')
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

    @app.post('/upload')
    async def upload_file(
        background_tasks: BackgroundTasks,
        file: UploadFile,
        content_type: str | None = Form(default=None),
        region: str | None = Form(default=None),
        source_path: str | None = Form(default=None),
        document_title: str | None = Form(default=None),
        source_label_display: str | None = Form(default=None),
        force: UploadForceMode | None = Form(default=None),
        service: ImportFileService = Depends(get_import_file_service),
    ) -> object:
        override = UploadOverride(
            content_type=content_type,
            region=region,
            source_path=source_path,
            document_title=document_title,
            source_label_display=source_label_display,
        )
        response, run_context = service.prepare_upload(file=file, overrides=override, force=force)
        if response.status == UploadStatus.REQUIRES_REINDEX:
            return JSONResponse(status_code=409, content=response.model_dump(exclude_none=True))
        if run_context is not None:
            background_tasks.add_task(service.run_upload, run_context)
        return response.model_dump(exclude_none=True)

    @app.post('/query')
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
                service.run_query_graph,
                task_id,
                session_id,
                request.query,
                True,
                request.message_id or '',
                request.history,
                request.retrieval_type,
                request.region,
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

    @app.get('/stream/{task_id}')
    async def stream(task_id: str, request: Request):
        return StreamingResponse(sse_generator(task_id, request), media_type='text/event-stream')

    @app.get('/status/{task_id}')
    async def get_status(task_id: str) -> dict[str, object]:
        return TaskStatusResponse(**build_task_status_payload(task_id)).model_dump()

    @app.get('/history/{session_id}')
    async def get_history(
        session_id: str,
        limit: int = 50,
        service: QueryService = Depends(get_query_service),
    ) -> dict[str, object]:
        return {
            'session_id': session_id,
            'items': service.get_history(session_id, limit),
        }

    @app.delete('/history/{session_id}')
    async def clear_chat_history(
        session_id: str,
        service: QueryService = Depends(get_query_service),
    ) -> dict[str, object]:
        try:
            deleted_count = service.clear_history(session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f'history error: {exc}') from exc
        return {'message': 'History cleared', 'deleted_count': deleted_count}

    return app


def _check_milvus_connected() -> bool:
    try:
        StorageClients.get_milvus_client().list_collections()
        return True
    except Exception:
        return False


def _check_minio_connected() -> bool:
    try:
        client = StorageClients.get_minio_client()
        bucket_name = os.getenv('MINIO_BUCKET_NAME', '').strip()
        if bucket_name:
            client.bucket_exists(bucket_name)
        else:
            client.list_buckets()
        return True
    except Exception:
        return False


app = create_app()


if __name__ == '__main__':
    host = os.getenv('EASYTOUR_API_HOST', os.getenv('KNOWLEDGE_API_HOST', '0.0.0.0'))
    port = int(os.getenv('EASYTOUR_API_PORT', os.getenv('KNOWLEDGE_API_PORT', '8000')))
    uvicorn.run(app=app, host=host, port=port)
