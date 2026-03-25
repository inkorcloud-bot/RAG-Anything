from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from .routes.documents import router as documents_router
from .routes.query import router as query_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Eagerly initialize LightRAG on startup so the first request succeeds."""
    rag = getattr(app.state, "rag", None)
    if rag is not None and hasattr(rag, "_ensure_lightrag_initialized"):
        result = await rag._ensure_lightrag_initialized()
        if result and not result.get("success", True):
            error = result.get("error", "unknown error")
            logger.error("LightRAG initialization failed at startup: %s", error)
            raise RuntimeError(f"LightRAG initialization failed at startup: {error}")
    yield


def create_app() -> FastAPI:
    """Create the minimal LightRAG-compatible API application."""
    app = FastAPI(title="RAG-Anything LightRAG API", lifespan=_lifespan)
    app.include_router(query_router)
    app.include_router(documents_router)
    return app
