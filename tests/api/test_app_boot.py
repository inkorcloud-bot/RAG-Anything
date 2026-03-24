from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from raganything.api.app import create_app


def test_create_app_exposes_openapi_and_docs():
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_server_main_injects_rag_instance(monkeypatch, tmp_path):
    """CLI entrypoint must set app.state.rag before handing off to uvicorn."""
    import raganything.api.server as server_module

    calls: dict = {}

    class FakeRAGAnything:
        def __init__(self, *, config):
            calls["rag_config"] = config

    class FakeRAGAnythingConfig:
        def __init__(self, *, working_dir: str):
            self.working_dir = working_dir

    captured_app: list[FastAPI] = []

    def fake_uvicorn_run(app_arg, **kwargs):
        captured_app.append(app_arg)
        calls["uvicorn_kwargs"] = kwargs

    monkeypatch.setattr(server_module, "RAGAnything", FakeRAGAnything)
    monkeypatch.setattr(server_module, "RAGAnythingConfig", FakeRAGAnythingConfig)
    monkeypatch.setattr(server_module.uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setattr(
        server_module,
        "ServerConfig",
        lambda: SimpleNamespace(
            host="127.0.0.1",
            port=9621,
            workers=1,
            log_level="info",
            working_dir=str(tmp_path),
        ),
    )

    server_module.main()

    assert len(captured_app) == 1, "uvicorn.run should have been called once"
    app = captured_app[0]
    assert hasattr(app.state, "rag"), "app.state.rag must be set before uvicorn.run"
    assert isinstance(app.state.rag, FakeRAGAnything)
    assert calls["rag_config"].working_dir == str(tmp_path)
