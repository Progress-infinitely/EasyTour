from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from easytour.api.routers.documents import router as documents_router
from easytour.api.routers.health import router as health_router
from easytour.api.routers.history import router as history_router
from easytour.api.routers.meta import router as meta_router
from easytour.api.routers.query import router as query_router
from easytour.api.routers.root import router as root_router
from easytour.api.routers.upload import router as upload_router
from easytour.core.paths import get_front_page_dir


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

    app.include_router(root_router)
    app.include_router(health_router)
    app.include_router(meta_router)
    app.include_router(documents_router)
    app.include_router(upload_router)
    app.include_router(query_router)
    app.include_router(history_router)

    return app


app = create_app()


if __name__ == '__main__':
    host = os.getenv('EASYTOUR_API_HOST', os.getenv('KNOWLEDGE_API_HOST', '0.0.0.0'))
    port = int(os.getenv('EASYTOUR_API_PORT', os.getenv('KNOWLEDGE_API_PORT', '8000')))
    uvicorn.run(app=app, host=host, port=port)
