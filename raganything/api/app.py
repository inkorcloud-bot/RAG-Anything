from fastapi import FastAPI

from .routes.documents import router as documents_router
from .routes.query import router as query_router


def create_app() -> FastAPI:
    """Create the minimal LightRAG-compatible API application."""
    app = FastAPI(title="RAG-Anything LightRAG API")
    app.include_router(query_router)
    app.include_router(documents_router)
    return app
