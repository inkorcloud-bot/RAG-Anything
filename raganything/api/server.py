import uvicorn

from raganything import RAGAnything
from raganything.config import RAGAnythingConfig

from .app import create_app
from .config import ServerConfig


def main() -> None:
    """CLI entrypoint: raganything-api"""
    config = ServerConfig()

    rag_config = RAGAnythingConfig(working_dir=config.working_dir)
    rag = RAGAnything(config=rag_config)

    app = create_app()
    app.state.rag = rag

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.log_level,
    )


if __name__ == "__main__":
    main()
