from __future__ import annotations

from fastapi.testclient import TestClient


class AsyncChunkIterator:
    def __init__(self, chunks, error: Exception | None = None):
        self._chunks = list(chunks)
        self._error = error

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._chunks:
            return self._chunks.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration


def test_query_route_returns_response(client, fake_raganything):
    response = client.post("/query", json={"query": "demo", "mode": "mix"})

    assert response.status_code == 200
    assert response.json()["response"] == "answer"
    assert fake_raganything.lightrag.query_calls[0]["query"] == "demo"
    assert fake_raganything.lightrag.query_calls[0]["param"].mode == "mix"


def test_query_route_omits_references_when_disabled(client):
    response = client.post(
        "/query",
        json={"query": "demo", "mode": "mix", "include_references": False},
    )

    assert response.status_code == 200
    assert "references" not in response.json()


def test_query_route_rejects_query_shorter_than_three_characters(client):
    response = client.post("/query", json={"query": "hi", "mode": "mix"})

    assert response.status_code == 422


def test_query_data_route_returns_structured_payload(client, fake_raganything):
    response = client.post("/query/data", json={"query": "demo", "mode": "mix"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["data"]["entities"] == []
    assert fake_raganything.lightrag.query_data_calls[0]["query"] == "demo"
    assert fake_raganything.lightrag.query_data_calls[0]["param"].mode == "mix"


def test_query_route_can_include_chunk_content_in_references(client, fake_raganything):
    fake_raganything.lightrag.query_result = {
        "data": {
            "references": [{"reference_id": "1", "file_path": "demo.txt"}],
            "chunks": [
                {"reference_id": "1", "content": "chunk-a"},
                {"reference_id": "1", "content": "chunk-b"},
            ],
        },
        "llm_response": {"content": "answer", "is_streaming": False},
    }

    response = client.post(
        "/query",
        json={"query": "demo", "mode": "mix", "include_chunk_content": True},
    )

    assert response.status_code == 200
    assert response.json()["references"][0]["content"] == ["chunk-a", "chunk-b"]


def test_query_stream_route_returns_ndjson_for_non_stream_response(client, fake_raganything):
    fake_raganything.lightrag.query_result = {
        "data": {
            "references": [{"reference_id": "1", "file_path": "demo.txt"}],
        },
        "llm_response": {"content": "answer", "is_streaming": False},
    }

    response = client.post(
        "/query/stream",
        json={"query": "demo", "mode": "mix", "stream": False},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert (
        response.text
        == '{"response": "answer", "references": [{"reference_id": "1", "file_path": "demo.txt"}]}\n'
    )


def test_query_stream_route_emits_references_then_response_chunks(client, fake_raganything):
    fake_raganything.lightrag.query_result = {
        "data": {
            "references": [{"reference_id": "1", "file_path": "demo.txt"}],
        },
        "llm_response": {
            "is_streaming": True,
            "response_iterator": AsyncChunkIterator(["part-1", "", "part-2"]),
        },
    }

    with client.stream(
        "POST",
        "/query/stream",
        json={"query": "demo", "mode": "mix", "stream": True},
    ) as response:
        lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert lines == [
        '{"references": [{"reference_id": "1", "file_path": "demo.txt"}]}',
        '{"response": "part-1"}',
        '{"response": "part-2"}',
    ]


def test_query_stream_route_appends_error_line_when_streaming_fails(app, fake_raganything):
    fake_raganything.lightrag.query_result = {
        "data": {"references": []},
        "llm_response": {
            "is_streaming": True,
            "response_iterator": AsyncChunkIterator(["part-1"], error=RuntimeError("stream failed")),
        },
    }
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/query/stream",
        json={"query": "demo", "mode": "mix", "stream": True},
    )

    assert response.status_code == 200
    assert response.text.endswith('{"error": "stream failed"}\n')


def test_query_route_returns_503_when_lightrag_not_initialized(app):
    """Routes must return 503, not crash with 500, when lightrag backend is None."""
    app.state.rag.lightrag = None
    client = TestClient(app, raise_server_exceptions=False)

    for path in ("/query", "/query/stream", "/query/data"):
        response = client.post(path, json={"query": "demo", "mode": "mix"})
        assert response.status_code == 503, f"{path} returned {response.status_code}"
        assert "lightrag" in response.json()["detail"].lower(), f"{path} detail: {response.json()['detail']}"
