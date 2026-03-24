from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from raganything.api.app import create_app


class _RAGWithInit:
    """Minimal fake that tracks _ensure_lightrag_initialized calls."""

    def __init__(self) -> None:
        self.init_calls: int = 0
        self.lightrag = None  # starts as None, set by init

    async def _ensure_lightrag_initialized(self) -> dict:
        self.init_calls += 1
        self.lightrag = object()  # simulate successful init
        return {"success": True}


def test_lifespan_calls_ensure_lightrag_initialized_on_startup():
    """The app lifespan must call _ensure_lightrag_initialized() so rag.lightrag
    is set before the first real request arrives.  This is the root cause that
    caused POST /documents/text → 500 and POST /query → 503 in the black-box
    CLI test (CMP-26 QA rejection).
    """
    fake_rag = _RAGWithInit()
    app = create_app()
    app.state.rag = fake_rag

    with TestClient(app):
        # Inside the context manager the lifespan has already run
        assert fake_rag.init_calls == 1, (
            "_ensure_lightrag_initialized must be called once during startup"
        )
        assert fake_rag.lightrag is not None, (
            "rag.lightrag must not be None after lifespan startup"
        )


def test_lifespan_skips_init_when_rag_not_set():
    """Lifespan must not crash when app.state.rag is absent (e.g. test isolation)."""
    app = create_app()
    # deliberately do NOT set app.state.rag
    with TestClient(app):
        pass  # no exception raised


def test_create_app_exposes_openapi_and_docs():
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_server_main_injects_rag_instance(monkeypatch, tmp_path):
    """CLI entrypoint must set app.state.rag before handing off to uvicorn."""
    import raganything.api.server as server_module

    calls: dict = {}

    _sentinel_llm = lambda *a, **kw: None  # noqa: E731
    _sentinel_embed = object()

    class FakeRAGAnything:
        def __init__(self, *, config, llm_model_func=None, embedding_func=None, **kwargs):
            calls["rag_config"] = config
            calls["llm_model_func"] = llm_model_func
            calls["embedding_func"] = embedding_func

    class FakeRAGAnythingConfig:
        def __init__(self, *, working_dir: str):
            self.working_dir = working_dir

    captured_app: list[FastAPI] = []

    def fake_uvicorn_run(app_arg, **kwargs):
        captured_app.append(app_arg)
        calls["uvicorn_kwargs"] = kwargs

    monkeypatch.setattr(server_module, "RAGAnything", FakeRAGAnything)
    monkeypatch.setattr(server_module, "RAGAnythingConfig", FakeRAGAnythingConfig)
    monkeypatch.setattr(server_module, "build_model_funcs", lambda: (_sentinel_llm, _sentinel_embed))
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
    assert calls["llm_model_func"] is _sentinel_llm
    assert calls["embedding_func"] is _sentinel_embed
