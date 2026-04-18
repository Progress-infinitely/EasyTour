from __future__ import annotations

from fastapi import APIRouter, Depends

from easytour.core.deps import get_document_service
from easytour.services.document_service import DocumentService
from easytour.services.health_service import check_milvus_connected, check_minio_connected

router = APIRouter()


@router.get('/healthz')
def healthz(
    document_service: DocumentService = Depends(get_document_service),
) -> dict[str, object]:
    return {
        'status': 'ok',
        'mongo_connected': document_service.is_mongo_connected(),
        'milvus_connected': check_milvus_connected(),
        'minio_connected': check_minio_connected(),
    }
