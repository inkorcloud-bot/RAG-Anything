"""
Env-driven model configuration for the RAG-Anything API server.

The server needs a ``llm_model_func`` and an ``embedding_func`` before
LightRAG can be initialized.  This module reads standard environment
variables (same conventions as LightRAG's own API) and returns ready-to-use
callables.

Supported provider: OpenAI (default).  Set ``OPENAI_API_KEY`` to enable.

Environment variables
---------------------
OPENAI_API_KEY     Required.  OpenAI secret key.
LLM_MODEL          LLM model name (default: gpt-4o-mini).
EMBEDDING_MODEL    Embedding model name (default: text-embedding-3-small).
OPENAI_BASE_URL    Optional custom base URL for the OpenAI-compatible API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Tuple


# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------

class MissingModelConfigError(RuntimeError):
    """Raised when required model env vars are not set at server startup."""


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    openai_api_key: str | None
    llm_model: str
    embedding_model: str
    base_url: str | None = field(default=None)

    # Default models kept in sync with LightRAG conventions
    _DEFAULT_LLM_MODEL: str = field(default="gpt-4o-mini", init=False, repr=False)
    _DEFAULT_EMBEDDING_MODEL: str = field(default="text-embedding-3-small", init=False, repr=False)

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )

    def is_configured(self) -> bool:
        """Return True iff the minimum required credentials are present."""
        return bool(self.openai_api_key)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_model_funcs(
    cfg: ModelConfig | None = None,
) -> Tuple[Callable, Callable]:
    """Return ``(llm_model_func, embedding_func)`` built from env / *cfg*.

    Raises
    ------
    MissingModelConfigError
        When ``OPENAI_API_KEY`` (or equivalent) is not set.
    """
    if cfg is None:
        cfg = ModelConfig.from_env()

    if not cfg.is_configured():
        raise MissingModelConfigError(
            "RAG-Anything API requires LLM credentials to initialize LightRAG. "
            "Set OPENAI_API_KEY (and optionally LLM_MODEL / EMBEDDING_MODEL) "
            "before starting the server."
        )

    # Import here so the rest of the module is importable without LightRAG
    # installed (e.g. during unit-test collection on a CI that only has stubs).
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed  # type: ignore
    from lightrag.utils import EmbeddingFunc  # type: ignore

    # LightRAG calls llm_model_func(prompt, system_prompt=..., history_messages=..., **kwargs).
    # openai_complete_if_cache signature is (model, prompt, system_prompt=..., ...).
    # Using partial(openai_complete_if_cache, model=...) causes "multiple values for
    # argument 'model'" because LightRAG passes the prompt as the first positional arg.
    # The correct pattern is an explicit wrapper that maps the LightRAG call convention
    # to the openai_complete_if_cache positional signature.
    _llm_model = cfg.llm_model
    _api_key = cfg.openai_api_key
    _base_url = cfg.base_url

    async def llm_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list | None = None,
        **kwargs,
    ) -> str:
        extra: dict = {}
        if _base_url:
            extra["base_url"] = _base_url
        return await openai_complete_if_cache(
            _llm_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=_api_key,
            **extra,
            **kwargs,
        )

    _embed_model = cfg.embedding_model
    _embed_extra: dict = {}
    if cfg.base_url:
        _embed_extra["base_url"] = cfg.base_url

    embedding_func = EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8192,
        func=partial(
            openai_embed,
            model=_embed_model,
            api_key=cfg.openai_api_key,
            **_embed_extra,
        ),
    )

    return llm_func, embedding_func
