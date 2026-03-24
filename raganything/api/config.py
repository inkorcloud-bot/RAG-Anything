import os


class ServerConfig:
    host: str
    port: int
    workers: int
    working_dir: str
    log_level: str

    def __init__(self) -> None:
        self.host = os.environ.get("RAGANYTHING_HOST", "0.0.0.0")
        self.port = int(os.environ.get("RAGANYTHING_PORT", "9621"))
        self.workers = int(os.environ.get("RAGANYTHING_WORKERS", "1"))
        self.working_dir = os.environ.get("RAGANYTHING_WORKING_DIR", "./rag_storage")
        self.log_level = os.environ.get("RAGANYTHING_LOG_LEVEL", "info")
