from __future__ import annotations

from fastapi import APIRouter, Depends

from easytour.core.deps import get_meta_service
from easytour.services.meta_service import MetaService

router = APIRouter()


@router.get('/meta/content_types')
async def get_content_types(
    service: MetaService = Depends(get_meta_service),
) -> list[dict[str, str]]:
    return [item.model_dump() for item in service.get_content_types()]


@router.get('/meta/regions')
async def get_regions(
    service: MetaService = Depends(get_meta_service),
) -> list[dict[str, str]]:
    return [item.model_dump() for item in service.get_regions()]


@router.get('/meta/items')
async def get_items(
    service: MetaService = Depends(get_meta_service),
) -> list[dict[str, str]]:
    return [item.model_dump() for item in service.get_items()]
