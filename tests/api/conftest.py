from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from raganything.api.app import create_app


class FakeDocStatus:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.get_docs_paginated_calls: list[dict[str, Any]] = []

    async def get_by_id(self, doc_id: str) -> dict[str, Any] | None:
        return self.docs.get(doc_id)

    async def get_doc_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if doc.get("file_path") == file_path:
                return doc
        return None

    async def get_docs_paginated(
        self,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_field: str = "updated_at",
        sort_direction: str = "desc",
    ) -> tuple[list[tuple[str, Any]], int]:
        self.get_docs_paginated_calls.append(
            {
                "status_filter": status_filter,
                "page": page,
                "page_size": page_size,
                "sort_field": sort_field,
                "sort_direction": sort_direction,
            }
        )
        docs = list(self.docs.values())
        if status_filter:
            docs = [doc for doc in docs if doc.get("status") == status_filter]
        reverse = sort_direction.lower() == "desc"
        docs.sort(key=lambda doc: doc.get(sort_field) or "", reverse=reverse)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        paged_docs = []
        for doc in docs[start:end]:
            paged_docs.append(
                (
                    doc["id"],
                    SimpleNamespace(
                        content_summary=doc.get("content_summary", ""),
                        content_length=doc.get("content_length", 0),
                        status=doc.get("status", "unknown"),
                        created_at=doc.get("created_at"),
                        updated_at=doc.get("updated_at"),
                        track_id=doc.get("track_id"),
                        chunks_count=doc.get("chunks_count"),
                        error_msg=doc.get("error_msg"),
                        metadata=doc.get("metadata"),
                        file_path=doc.get("file_path"),
                    ),
                )
            )
        return paged_docs, len(docs)

    async def get_all_status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for doc in self.docs.values():
            status = doc.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    async def upsert(self, payload: dict[str, Any]) -> None:
        self.docs[payload["id"]] = payload

    async def index_done_callback(self) -> None:
        return None


class FakeLightRAG:
    def __init__(self, doc_status: FakeDocStatus) -> None:
        self.doc_status = doc_status
        self.query_calls: list[dict[str, Any]] = []
        self.query_data_calls: list[dict[str, Any]] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.query_exception: Exception | None = None
        self.query_data_exception: Exception | None = None
        self.insert_exception: Exception | None = None
        self.query_result = {
            "data": {"references": []},
            "llm_response": {"content": "answer", "is_streaming": False},
        }
        self.query_data_result = {
            "status": "success",
            "message": "ok",
            "data": {
                "entities": [],
                "relationships": [],
                "chunks": [],
                "references": [],
            },
            "metadata": {"mode": "mix"},
        }

    async def aquery_llm(self, query: str, param: Any) -> dict[str, Any]:
        self.query_calls.append({"query": query, "param": param})
        if self.query_exception is not None:
            raise self.query_exception
        return self.query_result

    async def aquery_data(self, query: str, param: Any) -> dict[str, Any]:
        self.query_data_calls.append({"query": query, "param": param})
        if self.query_data_exception is not None:
            raise self.query_data_exception
        return self.query_data_result

    async def ainsert(
        self,
        input: Any,
        file_paths: list[str] | None = None,
        ids: list[str] | None = None,
        multimodal_content: Any = None,
        scheme_name: str | None = None,
    ) -> dict[str, str]:
        self.insert_calls.append(
            {
                "input": input,
                "file_paths": file_paths,
                "ids": ids,
                "multimodal_content": multimodal_content,
                "scheme_name": scheme_name,
            }
        )
        if self.insert_exception is not None:
            raise self.insert_exception
        return {"status": "ok"}


class FakeRAGAnything:
    def __init__(self, lightrag: FakeLightRAG, pipeline_status: dict[str, Any]) -> None:
        self.lightrag = lightrag
        self.pipeline_status = pipeline_status
        self.processor_calls: list[dict[str, Any]] = []
        self.processor_exception: Exception | None = None

    async def process_document_complete_lightrag_api(
        self,
        file_path: str,
        doc_id: str | None = None,
        scheme_name: str | None = None,
        parser: str | None = None,
    ) -> dict[str, Any]:
        self.processor_calls.append(
            {
                "file_path": file_path,
                "doc_id": doc_id,
                "scheme_name": scheme_name,
                "parser": parser,
                "path_exists_during_call": Path(file_path).exists(),
            }
        )
        if self.processor_exception is not None:
            raise self.processor_exception
        return {"status": "success", "doc_id": doc_id or Path(file_path).stem}

    async def get_document_processing_status(self, doc_id: str) -> dict[str, Any]:
        return {"doc_id": doc_id, "status": "processed"}

    async def is_document_fully_processed(self, doc_id: str) -> bool:
        return True


@pytest.fixture
def fake_doc_status() -> FakeDocStatus:
    return FakeDocStatus()


@pytest.fixture
def fake_pipeline_status() -> dict[str, Any]:
    return {
        "busy": False,
        "job_name": None,
        "job_start": None,
        "docs": 0,
        "batchs": 0,
        "cur_batch": 0,
        "request_pending": 0,
        "latest_message": "",
        "history_messages": [],
        "scan_disabled": False,
    }


@pytest.fixture
def fake_lightrag(fake_doc_status: FakeDocStatus) -> FakeLightRAG:
    return FakeLightRAG(fake_doc_status)


@pytest.fixture
def fake_raganything(
    fake_lightrag: FakeLightRAG,
    fake_pipeline_status: dict[str, Any],
) -> FakeRAGAnything:
    return FakeRAGAnything(fake_lightrag, fake_pipeline_status)


@pytest.fixture
def app(fake_raganything: FakeRAGAnything):
    app = create_app()
    app.state.rag = fake_raganything
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)
