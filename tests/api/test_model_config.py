"""
Tests for the env-driven model configuration factory.

The factory reads LLM and embedding config from environment variables and
returns callables that can be passed to RAGAnything. If the required env
vars are absent the factory raises a clear RuntimeError so the server
fails fast at startup rather than silently returning 503 on every query.
"""
from __future__ import annotations

import pytest

from raganything.api.model_config import (
    ModelConfig,
    build_model_funcs,
    MissingModelConfigError,
)


class TestModelConfig:
    def test_reads_openai_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

        cfg = ModelConfig.from_env()

        assert cfg.openai_api_key == "sk-test"
        assert cfg.llm_model == "gpt-4o-mini"
        assert cfg.embedding_model == "text-embedding-3-small"

    def test_uses_default_models_when_env_not_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

        cfg = ModelConfig.from_env()

        assert cfg.llm_model is not None
        assert cfg.embedding_model is not None

    def test_is_configured_false_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = ModelConfig.from_env()

        assert cfg.is_configured() is False

    def test_is_configured_true_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        cfg = ModelConfig.from_env()

        assert cfg.is_configured() is True


class TestBuildModelFuncs:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(MissingModelConfigError, match="OPENAI_API_KEY"):
            build_model_funcs()

    def test_returns_callables_when_configured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        llm_func, embedding_func = build_model_funcs()

        assert callable(llm_func)
        assert callable(embedding_func)

    def test_funcs_accept_custom_model_names(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")

        llm_func, embedding_func = build_model_funcs()

        assert callable(llm_func)
        assert callable(embedding_func)


    def test_llm_func_call_convention_matches_lightrag_expectation(self, monkeypatch):
        """LightRAG calls llm_model_func(prompt, system_prompt=..., history_messages=..., **kwargs).
        Using partial(openai_complete_if_cache, model=...) causes 'multiple values for
        argument model' because openai_complete_if_cache takes model as its first positional
        param.  The wrapper returned by build_model_funcs must accept prompt as the first
        positional argument, not model.
        """
        import asyncio
        import inspect

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        llm_func, _ = build_model_funcs()

        sig = inspect.signature(llm_func)
        params = list(sig.parameters.values())
        assert params[0].name == "prompt", (
            f"First parameter must be 'prompt', got '{params[0].name}'. "
            "LightRAG calls llm_func(query_text, system_prompt=...) so the first "
            "positional arg must be the prompt, not the model name."
        )
        # Verify it's awaitable (async function)
        assert asyncio.iscoroutinefunction(llm_func), (
            "llm_func must be an async function (LightRAG awaits it)"
        )


    """Verify server.py wires model funcs into RAGAnything."""

    def test_server_main_passes_model_funcs_to_raganything(self, monkeypatch, tmp_path):
        """When OPENAI_API_KEY is set, server.main() must pass llm_model_func
        and embedding_func to RAGAnything so rag.lightrag can be initialized."""
        import raganything.api.server as server_module
        from types import SimpleNamespace

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        captured: dict = {}
        sentinel_llm = lambda *a, **kw: None  # noqa: E731
        sentinel_embed = lambda *a, **kw: None  # noqa: E731

        class FakeRAGAnything:
            def __init__(self, *, config, llm_model_func=None, embedding_func=None, **kwargs):
                captured["llm_model_func"] = llm_model_func
                captured["embedding_func"] = embedding_func
                captured["config"] = config

        monkeypatch.setattr(server_module, "RAGAnything", FakeRAGAnything)
        monkeypatch.setattr(
            server_module,
            "build_model_funcs",
            lambda: (sentinel_llm, sentinel_embed),
        )
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
        monkeypatch.setattr(server_module.uvicorn, "run", lambda app_arg, **kw: None)

        server_module.main()

        assert captured["llm_model_func"] is sentinel_llm, (
            "llm_model_func must be passed to RAGAnything"
        )
        assert captured["embedding_func"] is sentinel_embed, (
            "embedding_func must be passed to RAGAnything"
        )

    def test_server_main_raises_when_no_model_config(self, monkeypatch, tmp_path):
        """When model env vars are absent, server.main() must raise MissingModelConfigError
        at startup, not silently allow a 503-producing RAGAnything instance."""
        import raganything.api.server as server_module
        from types import SimpleNamespace

        monkeypatch.setenv("OPENAI_API_KEY", "")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

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
        monkeypatch.setattr(server_module.uvicorn, "run", lambda *a, **kw: None)

        with pytest.raises(MissingModelConfigError):
            server_module.main()
