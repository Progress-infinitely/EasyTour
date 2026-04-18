from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from easytour.core.paths import get_front_page_dir

router = APIRouter()

front_page_dir = get_front_page_dir()
logo_path = Path(front_page_dir).resolve().parent.parent / 'logo.png'


@router.get('/')
def read_root() -> dict[str, object]:
    return {
        'message': 'EasyTour service is running',
        'chat_page': '/chat.html',
        'import_page': '/import',
        'docs': '/docs',
    }


@router.get('/chat.html')
async def chat_page() -> FileResponse:
    return FileResponse(os.path.join(front_page_dir, 'chat.html'))


@router.get('/logo.png')
async def logo_asset() -> FileResponse:
    if not logo_path.exists():
        raise HTTPException(status_code=404, detail='logo not found')
    return FileResponse(logo_path)


@router.get('/import')
@router.get('/import.html')
async def import_page() -> FileResponse:
    return FileResponse(os.path.join(front_page_dir, 'import.html'))
