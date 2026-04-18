from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile
from fastapi.responses import JSONResponse

from easytour.core.deps import get_import_file_service
from easytour.schema.upload_schema import UploadForceMode, UploadOverride, UploadStatus
from easytour.services.import_file_service import ImportFileService

router = APIRouter()


@router.post('/upload')
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
