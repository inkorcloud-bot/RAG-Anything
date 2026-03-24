"""
LightRAG-compatible API server for RAG-Anything.

Usage:
    pip install "raganything[api]"
    python examples/lightrag_openapi_server.py

Environment variables:
    RAGANYTHING_HOST         - Bind host (default: 0.0.0.0)
    RAGANYTHING_PORT         - Listen port (default: 9621)
    RAGANYTHING_WORKING_DIR  - Storage working directory (default: ./rag_storage)
    RAGANYTHING_LOG_LEVEL    - Uvicorn log level (default: info)
    RAGANYTHING_WORKERS      - Number of workers (default: 1)

    LLM / embedding env vars are passed through to RAGAnything/LightRAG as normal.

Quick API examples (once running):

    # Upload a document
    curl -X POST http://localhost:9621/documents/upload \
         -F "file=@/path/to/doc.pdf"

    # Insert text directly
    curl -X POST http://localhost:9621/documents/text \
         -H "Content-Type: application/json" \
         -d '{"text": "RAG-Anything supports multimodal document processing.", "file_source": "manual"}'

    # Query (JSON)
    curl -X POST http://localhost:9621/query \
         -H "Content-Type: application/json" \
         -d '{"query": "What does RAG-Anything support?", "mode": "mix"}'

    # Query (streaming NDJSON)
    curl -X POST http://localhost:9621/query/stream \
         -H "Content-Type: application/json" \
         -d '{"query": "What does RAG-Anything support?", "mode": "mix", "stream": true}'

    # List documents
    curl "http://localhost:9621/documents?page=1&page_size=20"

    # Document status counts
    curl http://localhost:9621/documents/status_counts

    # Pipeline status
    curl http://localhost:9621/documents/pipeline_status
"""

import os

import uvicorn

from raganything import RAGAnything
from raganything.api.app import create_app
from raganything.api.config import ServerConfig


def main() -> None:
    config = ServerConfig()

    # Build RAGAnything — adjust constructor args for your LLM/embedding setup.
    # The minimum required fields depend on your LightRAG backend configuration.
    # See README.md for full initialization options.
    rag = RAGAnything(
        working_dir=config.working_dir,
    )

    app = create_app()
    app.state.rag = rag

    print(f"Starting RAG-Anything LightRAG API on http://{config.host}:{config.port}")
    print(f"  Docs:      http://{config.host}:{config.port}/docs")
    print(f"  OpenAPI:   http://{config.host}:{config.port}/openapi.json")
    print(f"  Working dir: {config.working_dir}")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.log_level,
    )


if __name__ == "__main__":
    main()
