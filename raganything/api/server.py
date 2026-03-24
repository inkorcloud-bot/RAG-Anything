import uvicorn

from .app import create_app
from .config import ServerConfig


def main() -> None:
    """CLI entrypoint: raganything-api"""
    config = ServerConfig()
    app = create_app()
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.log_level,
    )


if __name__ == "__main__":
    main()
