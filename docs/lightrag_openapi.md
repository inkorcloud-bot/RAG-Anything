# LightRAG OpenAPI Compatibility — RAG-Anything

> **Status:** v1 delivered. Routes implemented and tested as of 2026-03-24.

## Quick Start

### Install

```bash
pip install "raganything[api]"
```

### Minimum startup requirements

The server **cannot start** without LLM credentials.  Set these before running:

```bash
export OPENAI_API_KEY="sk-..."          # Required — server exits immediately if absent
export OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional; use for any OpenAI-compatible endpoint
export LLM_MODEL="gpt-4o-mini"         # Optional; default: gpt-4o-mini
export EMBEDDING_MODEL="text-embedding-3-small"     # Optional; default: text-embedding-3-small
```

For a local OpenAI-compatible server (e.g. vLLM, Ollama with OpenAI adapter, LM Studio):

```bash
export OPENAI_API_KEY="dummy"          # Any non-empty string if your server doesn't check it
export OPENAI_BASE_URL="http://127.0.0.1:11434/v1"  # Replace with your local endpoint
export LLM_MODEL="llama3.2"            # Replace with the model served locally
export EMBEDDING_MODEL="nomic-embed-text"           # Replace with the embedding model served locally
```

### Environment Variables

**Model configuration (set before starting)**

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key (or any non-empty string for compatible endpoints). Server exits if absent. |
| `OPENAI_BASE_URL` | OpenAI default | Base URL for the OpenAI-compatible API. Set to a local endpoint for self-hosted models. |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name sent to the API. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name sent to the API. |

**Server configuration**

| Variable | Default | Description |
| --- | --- | --- |
| `RAGANYTHING_HOST` | `0.0.0.0` | Bind host |
| `RAGANYTHING_PORT` | `9621` | Listen port |
| `RAGANYTHING_WORKERS` | `1` | Uvicorn worker count |
| `RAGANYTHING_WORKING_DIR` | `./rag_storage` | Working directory for RAG storage |
| `RAGANYTHING_LOG_LEVEL` | `info` | Uvicorn log level |

### Start

```bash
# With OpenAI
OPENAI_API_KEY=sk-... raganything-api

# With a local OpenAI-compatible server
OPENAI_API_KEY=dummy OPENAI_BASE_URL=http://127.0.0.1:11434/v1 LLM_MODEL=llama3.2 EMBEDDING_MODEL=nomic-embed-text raganything-api
```

Or run the example directly:

```bash
OPENAI_API_KEY=sk-... python examples/lightrag_openapi_server.py
```

Then open:

- API docs: `http://localhost:9621/docs`
- OpenAPI schema: `http://localhost:9621/openapi.json`

### Startup behaviour

- If `OPENAI_API_KEY` is missing → server prints an error and exits immediately (`MissingModelConfigError`).
- If credentials are present → LightRAG is eagerly initialized during startup (before the first request). A successful start means the backend is ready to serve `/query` and `/documents/text` immediately.
- Document-upload routes (`POST /documents/upload`) additionally require a document parser (mineru, docling, or paddleocr). If the parser is not installed, upload requests fail with a clear error; query and text-insert routes are unaffected.

---

## Supported Routes (v1)

### Query

| Route | Method | Status | Backend |
| --- | --- | --- | --- |
| `/query` | POST | ✅ supported | `rag.lightrag.aquery_llm(query, param)` |
| `/query/stream` | POST | ✅ supported | `rag.lightrag.aquery_llm(query, param)` — NDJSON |
| `/query/data` | POST | ✅ supported | `rag.lightrag.aquery_data(query, param)` |

**Request fields** (`POST /query`, `/query/stream`, `/query/data`)

```json
{
  "query": "string (min 3 chars)",
  "mode": "mix | local | global | hybrid | naive | bypass",
  "include_references": true,
  "include_chunk_content": false,
  "stream": true,
  "top_k": null,
  "chunk_top_k": null,
  "max_entity_tokens": null,
  "max_relation_tokens": null,
  "max_total_tokens": null,
  "hl_keywords": [],
  "ll_keywords": [],
  "conversation_history": null,
  "response_type": null,
  "enable_rerank": null
}
```

**`/query` response**

```json
{
  "response": "answer text",
  "references": [
    {"reference_id": "1", "file_path": "doc.txt"}
  ]
}
```

**`/query/stream` response** — NDJSON (`application/x-ndjson`)

```
{"references": [...]}
{"response": "chunk 1"}
{"response": "chunk 2"}
```

On error during streaming:

```
{"error": "message"}
```

**`/query/data` response**

```json
{
  "status": "success",
  "message": "...",
  "data": {"entities": [], "relationships": [], "chunks": [], "references": []},
  "metadata": {"mode": "mix"}
}
```

---

### Documents

| Route | Method | Status | Backend |
| --- | --- | --- | --- |
| `/documents/upload` | POST | ✅ supported | `rag.process_document_complete_lightrag_api(path, doc_id, parser, scheme_name)` |
| `/documents/text` | POST | ✅ supported | `rag.lightrag.ainsert(input, file_paths)` |
| `/documents/texts` | POST | ✅ supported | `rag.lightrag.ainsert(input, file_paths)` |
| `/documents` | GET | ✅ supported | `rag.lightrag.doc_status.get_docs_paginated(...)` |
| `/documents/status_counts` | GET | ✅ supported | `rag.lightrag.doc_status.get_all_status_counts()` |
| `/documents/pipeline_status` | GET | ✅ supported | `rag.pipeline_status` dict |

**`POST /documents/upload`** — multipart form

```
file=<binary>
doc_id=<optional string>
parser=<optional string>
scheme_name=<optional string>
```

Response:

```json
{"status": "success", "message": "File 'demo.txt' uploaded successfully."}
```

**`POST /documents/text`**

```json
{"text": "content", "file_source": "optional source label"}
```

**`POST /documents/texts`**

```json
{"texts": ["text 1", "text 2"], "file_sources": ["a.txt", "b.txt"]}
```

`file_sources` length must match `texts` length when provided.

**`GET /documents`**

Query params: `status_filter`, `page` (default 1), `page_size` (default 50), `sort_field` (default `updated_at`), `sort_direction` (default `desc`)

Response:

```json
{
  "documents": [...],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_count": 42,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  },
  "status_counts": {"processed": 40, "processing": 2}
}
```

**`GET /documents/status_counts`**

```json
{"status_counts": {"processed": 40, "processing": 2}}
```

**`GET /documents/pipeline_status`**

```json
{
  "busy": false,
  "job_name": null,
  "job_start": null,
  "docs": 0,
  "batchs": 0,
  "cur_batch": 0,
  "request_pending": 0,
  "latest_message": "",
  "history_messages": [],
  "update_status": {},
  "scan_disabled": false
}
```

---

## Deferred Routes (not in v1)

| Route | Reason |
| --- | --- |
| Graph mutation routes | Requires direct LightRAG graph storage access not exposed via `RAGAnything` |
| `DELETE /documents/{id}` | No stable remove-by-id helper in current `RAGAnything` |
| Document reprocess / cancel | No async queue layer in v1 |
| Ollama/OpenAI-compatible chat routes | Out of v1 scope |
| `POST /documents/paginated` (LightRAG native) | Replaced by `GET /documents` with query params in v1 |

---

## Deliberate Divergences from LightRAG

| Topic | LightRAG behavior | v1 behavior | Reason |
| --- | --- | --- | --- |
| Document listing route | `POST /documents/paginated` | `GET /documents` | REST convention; `status_filter` via query param |
| Upload response | Async track-id + status | Synchronous success/failure | No async document queue in v1 |
| Pipeline status source | Shared namespace storage | `rag.pipeline_status` dict | Simpler source of truth; normalizes non-dict `update_status` to `{}` |
| Query validation | None | `query` min length 3 | Prevents accidental empty queries |
| Text insert whitespace | Forwarded as-is | Trimmed; whitespace-only rejected | Prevents silent empty inserts |

---

## Running Tests

```bash
# API contract tests only
pytest tests/api -q

# Full suite (one pre-existing failure in test_callbacks.py, not introduced by API)
pytest tests/ -q
```

---

## Release Guardrails

- Compatibility target is **LightRAG route shape**, not internal implementation parity.
- Unsupported routes return `404`, not a silent empty response.
- Route modules are thin adapters around `RAGAnything` — no retrieval logic belongs in HTTP handlers.
- Every deliberate divergence from upstream LightRAG is documented in the table above.
