from __future__ import annotations

from easytour.schema.chunk_schema import CHUNK_PREVIEW_OUTPUT_FIELDS
from easytour.utils.milvus_util import fetch_chunks_by_chunk_ids
from easytour.utils.title_util import resolve_chunk_title, resolve_document_title


def prepare_preview_document(
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

    if snapshot_has_chunk_ids(chunks):
        preview_document['chunks_snapshot'] = []
        return preview_document

    fallback_chunk = fetch_preview_chunk_from_milvus(
        chunk_id=selected_chunk_id,
        document_id=str(document.get('document_id') or ''),
        chunks_collection=chunks_collection,
    )
    preview_document['chunks_snapshot'] = [fallback_chunk] if fallback_chunk else []
    return preview_document


def snapshot_has_chunk_ids(chunks: list[dict[str, object]]) -> bool:
    return any(str(chunk.get('chunk_id') or '').strip() for chunk in chunks)


def fetch_preview_chunk_from_milvus(
    *,
    chunk_id: str,
    document_id: str,
    chunks_collection: str,
) -> dict[str, str] | None:
    lookup_id: int | str = int(chunk_id) if chunk_id.isdigit() else chunk_id
    rows = fetch_chunks_by_chunk_ids(
        chunks_collection,
        [lookup_id],
        output_fields=CHUNK_PREVIEW_OUTPUT_FIELDS,
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


def build_preview_html(document: dict, chunk_id: str | None = None) -> str:
    import json as _json

    title = resolve_document_title(document) or '文档预览'
    city = document.get('city') or ''
    region_path = document.get('region_path') or ''
    content_type_map = {
        'attraction': '景点',
        'route': '路线',
        'hotel': '酒店',
        'food': '美食',
        'transport': '交通',
        'culture': '文化',
    }
    content_type = content_type_map.get(document.get('content_type') or '', document.get('content_type') or '')
    chunks = document.get('chunks_snapshot') or []
    selected_chunk_id = str(chunk_id or '').strip()
    chunks_data = [
        {
            'title': resolve_chunk_title(
                c,
                default_document_title=title,
                fallback_file_title=str(document.get('file_title') or ''),
            ),
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


def build_preview_not_found_html(document_id: str) -> str:
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
