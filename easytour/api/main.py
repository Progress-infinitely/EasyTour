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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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
from easytour.utils.milvus_util import fetch_chunks_by_chunk_ids
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
    # [修改] 根目录 logo 需要单独暴露，前端头部才能统一复用同一张品牌图。
    logo_path = Path(front_page_dir).resolve().parent.parent / 'logo.png'
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

    @app.get('/logo.png')
    async def logo_asset() -> FileResponse:
        if not logo_path.exists():
            raise HTTPException(status_code=404, detail='logo not found')
        return FileResponse(logo_path)

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

    @app.get('/documents/{document_id}/preview')
    async def preview_document_chunks(
        document_id: str,
        chunk_id: str | None = None,
        service: DocumentService = Depends(get_document_service),
    ) -> HTMLResponse:
        document = service.get_document(document_id)
        if document is None:
            return HTMLResponse(_build_preview_not_found_html(document_id), status_code=404)
        preview_document = _prepare_preview_document(
            document,
            chunk_id=chunk_id,
            chunks_collection=str(service._chunks_collection),
        )
        return HTMLResponse(_build_preview_html(preview_document, chunk_id=chunk_id))

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


def _build_preview_html(document: dict, chunk_id: str | None = None) -> str:
    import json as _json

    title = document.get('document_title') or document.get('file_title') or '文档预览'
    city = document.get('city') or ''
    region_path = document.get('region_path') or ''
    content_type_map = {
        'attraction': '景点', 'route': '路线', 'hotel': '酒店',
        'food': '美食', 'transport': '交通', 'culture': '文化',
    }
    content_type = content_type_map.get(document.get('content_type') or '', document.get('content_type') or '')
    chunks = document.get('chunks_snapshot') or []
    # [修改] 支持按 chunk_id 过滤，只展示当前引用真正命中的那一段。
    selected_chunk_id = str(chunk_id or '').strip()
    chunks_data = [
        {
            'title': str(c.get('title') or c.get('parent_title') or ''),
            'content': str(c.get('content') or ''),
            'chunk_id': str(c.get('chunk_id') or ''),
        }
        for c in chunks
        if c.get('content') and (not selected_chunk_id or str(c.get('chunk_id') or '') == selected_chunk_id)
    ]
    doc_json = _json.dumps(
        {
            'title': title,
            'city': city,
            'region': region_path,
            'type': content_type,
            'preview_scope': 'chunk' if selected_chunk_id else 'document',
            'empty_message': '没有找到对应的命中片段' if selected_chunk_id else '暂无可预览的内容',
            'chunks': chunks_data,
        },
        ensure_ascii=False,
    )
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · 引用预览</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body {{ font-family: "Inter", "Noto Sans SC", sans-serif; background: #f4f7fc; }}
.prose h1,.prose h2,.prose h3 {{ font-weight:700; margin:1em 0 .4em; color:#00236f; }}
.prose h1 {{ font-size:1.4rem; }}
.prose h2 {{ font-size:1.2rem; border-bottom:1px solid #e2e8f0; padding-bottom:.3em; }}
.prose h3 {{ font-size:1.05rem; }}
.prose p {{ margin:.5em 0; line-height:1.75; }}
.prose ul,.prose ol {{ padding-left:1.4em; margin:.5em 0; }}
.prose li {{ margin:.25em 0; line-height:1.7; }}
.prose strong {{ font-weight:600; }}
.prose code {{ background:#eef2ff; color:#3730a3; padding:.1em .35em; border-radius:.3em; font-size:.88em; }}
.prose pre {{ background:#1e293b; color:#e2e8f0; padding:1em; border-radius:.6em; overflow-x:auto; margin:.75em 0; }}
.prose pre code {{ background:none; color:inherit; padding:0; }}
.prose blockquote {{ border-left:3px solid #b6c4ff; padding:.1em 1em; color:#585f6a; margin:.5em 0; background:#f0f4ff; border-radius:0 .4em .4em 0; }}
.prose table {{ border-collapse:collapse; width:100%; margin:.75em 0; }}
.prose th,.prose td {{ border:1px solid #e2e8f0; padding:.4em .75em; }}
.prose th {{ background:#eef2ff; font-weight:600; }}
</style>
</head>
<body class="min-h-screen px-4 py-8">
<div class="mx-auto max-w-3xl">
  <div class="mb-6 rounded-2xl bg-white p-6 shadow-sm border border-slate-100">
    <div class="flex items-start gap-4">
      <!-- [修改] 预览页头部改成复用项目 logo，不再显示占位 ET 方块。 -->
      <img src="/logo.png" alt="EasyTour Logo" class="h-12 w-12 shrink-0 rounded-xl object-cover" />
      <div class="flex-1 min-w-0">
        <h1 class="text-xl font-bold text-slate-900 break-words" id="doc-title"></h1>
        <div class="mt-2 flex flex-wrap gap-2" id="doc-meta"></div>
      </div>
    </div>
  </div>
  <div id="chunks-container" class="space-y-4"></div>
</div>
<script>
const DATA = {doc_json};
const $ = id => document.getElementById(id);
$("doc-title").textContent = DATA.title;
const meta = $("doc-meta");
[DATA.city, DATA.region, DATA.type].filter(Boolean).forEach(tag => {{
  const span = document.createElement("span");
  span.className = "rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800";
  span.textContent = tag;
  meta.appendChild(span);
}});
const container = $("chunks-container");
if (!DATA.chunks.length) {{
  container.innerHTML = `<p class="text-center text-slate-400 py-8">${{DATA.empty_message}}</p>`;
}} else {{
  DATA.chunks.forEach((chunk, i) => {{
    const card = document.createElement("div");
    card.className = "rounded-2xl bg-white p-6 shadow-sm border border-slate-100";
    let html = "";
    const blockLabel = DATA.preview_scope === "chunk" ? "命中片段" : `段落 ${{i+1}}`;
    if (chunk.title) {{
      html += `<div class="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">${{blockLabel}} · ${{chunk.title}}</div>`;
    }} else {{
      html += `<div class="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">${{blockLabel}}</div>`;
    }}
    html += `<div class="prose text-sm text-slate-700">${{marked.parse(chunk.content)}}</div>`;
    card.innerHTML = html;
    container.appendChild(card);
  }});
}}
</script>
</body>
</html>'''


def _prepare_preview_document(
    document: dict[str, object],
    *,
    chunk_id: str | None,
    chunks_collection: str,
) -> dict[str, object]:
    preview_document = dict(document)
    selected_chunk_id = str(chunk_id or '').strip()
    if not selected_chunk_id:
        return preview_document

    chunks = list(document.get('chunks_snapshot') or [])
    matched_snapshot = [
        chunk
        for chunk in chunks
        if chunk.get('content') and str(chunk.get('chunk_id') or '') == selected_chunk_id
    ]
    if matched_snapshot:
        preview_document['chunks_snapshot'] = matched_snapshot
        return preview_document

    # [修改] 兼容历史文档：老快照里可能没有 chunk_id，兜底去 Milvus 按 chunk_id 直接捞命中片段。
    fallback_chunk = _fetch_preview_chunk_from_milvus(
        chunk_id=selected_chunk_id,
        document_id=str(document.get('document_id') or ''),
        chunks_collection=chunks_collection,
    )
    preview_document['chunks_snapshot'] = [fallback_chunk] if fallback_chunk else []
    return preview_document


def _fetch_preview_chunk_from_milvus(
    *,
    chunk_id: str,
    document_id: str,
    chunks_collection: str,
) -> dict[str, str] | None:
    lookup_id: int | str = int(chunk_id) if chunk_id.isdigit() else chunk_id
    rows = fetch_chunks_by_chunk_ids(
        chunks_collection,
        [lookup_id],
        output_fields=['chunk_id', 'document_id', 'content', 'title', 'parent_title'],
    )
    for row in rows:
        row_document_id = str(row.get('document_id') or '')
        if document_id and row_document_id and row_document_id != document_id:
            continue
        content = str(row.get('content') or '').strip()
        if not content:
            continue
        return {
            'chunk_id': str(row.get('chunk_id') or chunk_id),
            'title': str(row.get('title') or row.get('parent_title') or ''),
            'parent_title': str(row.get('parent_title') or ''),
            'content': content,
        }
    return None


def _build_preview_not_found_html(document_id: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>文档未找到</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="flex min-h-screen items-center justify-center bg-slate-50">
<div class="text-center p-8">
  <div class="text-5xl mb-4">🔍</div>
  <h1 class="text-xl font-bold text-slate-700">文档未找到</h1>
  <p class="mt-2 text-sm text-slate-400">ID: {document_id}</p>
  <p class="mt-1 text-sm text-slate-400">该文档可能已被删除或尚未入库</p>
</div>
</body></html>'''


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
