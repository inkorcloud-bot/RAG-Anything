# LightRAG OpenAPI Compatibility Matrix

> **Status:** Backend gap inventory — pre-implementation reference for [CMP-10](/CMP/issues/CMP-10)
>
> **Last updated:** 2026-03-24

---

## Route Compatibility Summary

| Route | Method | Compatibility | Backend call | Notes |
|-------|--------|--------------|--------------|-------|
| `/query` | POST | **supported in v1** | `rag.lightrag.aquery_llm(query, param)` | Returns `{response, references}` |
| `/query/stream` | POST | **supported in v1** | `rag.lightrag.aquery_llm(query, param)` with streaming param | NDJSON; first chunk references, subsequent chunks response text |
| `/query/data` | POST | **supported in v1** | `rag.lightrag.aquery_data(query, param)` | Returns structured `{status, message, data, metadata}` — native LightRAG call, **no helper needed** |
| `/documents/upload` | POST | **supported in v1** | `rag.process_document_complete_lightrag_api(file_path, ...)` | Save upload to temp path, call processor, clean up |
| `/documents/text` | POST | **supported in v1** | `rag.lightrag.ainsert(text, file_paths=file_source)` | Single-text insertion via LightRAG directly |
| `/documents/texts` | POST | **supported in v1** | `rag.lightrag.ainsert(texts, file_paths=file_sources)` | Batch text insertion via LightRAG directly |
| `/documents` | GET | **supported in v1** | `rag.lightrag.get_docs_by_status(status)` per status | Returns grouped doc statuses; cap at 1 000 records |
| `/documents/status_counts` | GET | **supported in v1** | `rag.lightrag.doc_status.get_all_status_counts()` | Returns `{status_name: count}` dict |
| `/documents/pipeline_status` | GET | **supported in v1** | `lightrag.kg.shared_storage.get_namespace_data("pipeline_status")` | Returns busy flag, cur_batch, history_messages, etc. |
| `/documents/scan` | POST | deferred | LightRAG doc_manager scan loop | Requires input_dir file-watcher; deferred |
| `/documents/paginated` | GET | deferred | `rag.lightrag.doc_status` paginated query | Deferred until basic list is working |
| `/documents/delete_document` | DELETE | deferred | `rag.lightrag.adelete_by_doc_id()` | Deferred to post-v1 |
| `/documents/reprocess_failed` | POST | deferred | `rag.lightrag.apipeline_process_enqueue_documents()` | Deferred |
| Graph mutation routes | * | deferred | LightRAG graph API | Out of v1 scope |
| Ollama/OpenAI-compatible routes | * | deferred | N/A | Different compatibility target |

---

## Backend Call Map (v1 routes in detail)

### `/query` → `/query/stream`

```
POST /query        → rag.lightrag.aquery_llm(query, param=QueryParam(mode=..., stream=False))
POST /query/stream → rag.lightrag.aquery_llm(query, param=QueryParam(mode=..., stream=True|False))
```

- `RAGAnything.aquery` delegates directly to `self.lightrag.aquery` with a `QueryParam`.
- The API layer should call `rag.lightrag.aquery_llm` (returns `{llm_response, data}`) rather than the lower-level `aquery`, because `aquery_llm` exposes references alongside the response — the shape the route contract requires.
- `QueryParam` fields that need to survive from HTTP request to backend: `mode`, `top_k`, `chunk_top_k`, `max_entity_tokens`, `max_relation_tokens`, `max_total_tokens`, `hl_keywords`, `ll_keywords`, `conversation_history`, `response_type`, `only_need_context`, `only_need_prompt`, `enable_rerank`, `include_references`.
- `stream=True` causes `aquery_llm` to return an async generator in `llm_response["response_iterator"]`; route must yield NDJSON chunks from that iterator.

### `/query/data`

```
POST /query/data → rag.lightrag.aquery_data(query, param=QueryParam(..., stream=False))
```

- `aquery_data` is a **first-class LightRAG method** (available since lightrag-hku 1.4.x).
- Returns `{"status": "success"|"failure", "message": str, "data": {entities, relationships, chunks, references}, "metadata": {query_mode, keywords, processing_info}}`.
- **No helper needed in `raganything/query.py`** — call directly on `rag.lightrag`.
- Only the route's request model and response model translation work is needed.
- `stream` parameter must be forced to `False` for this endpoint.

### `/documents/upload`

```
POST /documents/upload → temp write → rag.process_document_complete_lightrag_api(file_path, ...)
```

- `ProcessorMixin.process_document_complete_lightrag_api` is the canonical LightRAG-API-facing method.
- It manages `doc_status` entries itself (READY → HANDLING → PROCESSED/FAILED).
- Route must: receive `UploadFile`, write to a temp path, call the method in a background task, return `{status, message, track_id}`.
- Cleanup of temp file should happen after the background task completes (success or failure).
- The LightRAG `upload` route uses `input_dir`-based file management and a doc_manager; RAG-Anything's route can skip the doc_manager layer and call `process_document_complete_lightrag_api` directly.

### `/documents/text` and `/documents/texts`

```
POST /documents/text  → rag.lightrag.ainsert(text,  file_paths=file_source)
POST /documents/texts → rag.lightrag.ainsert(texts, file_paths=file_sources)
```

- `ainsert` accepts a single string or list and an optional `file_paths` parameter.
- Duplicate detection: check `rag.lightrag.doc_status.get_doc_by_file_path(file_source)` before inserting if `file_source` is provided.
- Both routes should return `{status, message, track_id}` compatible with `InsertResponse`.
- `track_id` can be a generated string (`"insert_<timestamp>_<random>"`); at v1 it is informational only, not queryable via `/documents/track_status`.

### `GET /documents`

```
GET /documents → rag.lightrag.get_docs_by_status(DocStatus.PENDING|PROCESSING|PREPROCESSED|PROCESSED|FAILED)
```

- `get_docs_by_status` returns `dict[str, DocProcessingStatus]` per status value.
- Must be called concurrently for all five statuses and merged into `DocsStatusesResponse`.
- Cap total records at 1 000 (round-robin fairness across statuses, same as LightRAG reference).
- `DocProcessingStatus` contains: `content_summary`, `content_length`, `file_path`, `status`, `created_at`, `updated_at`, `track_id`, `chunks_count`, `error_msg`, `metadata`, `multimodal_processed`.
- `multimodal_processed=False` + `status=PROCESSED` is normalised to `DocStatus.PREPROCESSED` by `DocProcessingStatus.__post_init__` — no extra logic needed in the route.

### `GET /documents/status_counts`

```
GET /documents/status_counts → rag.lightrag.doc_status.get_all_status_counts()
```

- Returns `dict[str, int]` keyed by status string (e.g. `{"PROCESSED": 12, "FAILED": 1, ...}`).
- Access path: `rag.lightrag.doc_status` is the underlying storage object; this method is not on `LightRAG` directly but on the storage instance.

### `GET /documents/pipeline_status`

```
GET /documents/pipeline_status →
    from lightrag.kg.shared_storage import get_namespace_data, get_namespace_lock
    pipeline_status = await get_namespace_data("pipeline_status", workspace=rag.lightrag.workspace)
```

- Returns a dict with keys: `busy`, `autoscanned`, `job_name`, `job_start`, `docs`, `batchs`, `cur_batch`, `request_pending`, `latest_message`, `history_messages`, `scan_disabled`.
- History messages should be capped (e.g. last 1 000 entries) before returning.
- `rag.lightrag.workspace` provides the namespace scope needed for shared storage lookups.

---

## Known Parity Gaps

### Gap 1 — `doc_status.get_all_status_counts()` method

**Risk:** Low — almost certainly available, but not confirmed against the RAG-Anything-installed version.

**Resolution plan:** Call `dir(rag.lightrag.doc_status)` at bootstrap time and assert the method exists. If missing (older lightrag-hku), add a fallback that counts by calling `get_docs_by_status` per status.

### Gap 2 — `doc_status.get_doc_by_file_path()` for duplicate detection

**Risk:** Low — used in LightRAG's own upload route; present in lightrag-hku 1.4.x.

**Resolution plan:** Check method availability during integration testing. If unavailable, skip pre-flight duplicate check and rely on content-hash dedup in `ainsert`.

### Gap 3 — `rag.lightrag.workspace` attribute

**Risk:** Low — present in lightrag-hku 1.4.11 (confirmed in `LightRAG.working_dir` synonyms).

**Resolution plan:** Fall back to `workspace=None` if the attribute is absent; shared storage uses a default namespace.

### Gap 4 — Background task / async pipeline interaction

**Risk:** Medium — `process_document_complete_lightrag_api` is designed for background use but interacts with `pipeline_status` shared state. Running two concurrent uploads may contend on the lock (`scan_disabled`).

**Resolution plan:** Accept one-at-a-time behaviour for v1. Document as known limitation. If needed, implement a simple queue wrapper.

### Gap 5 — Auth mode

**Risk:** Low — orthogonal to route implementation.

**Resolution plan:** v1 default is **no auth** (disabled). Optionally support a static bearer token via `RAGANYTHING_API_KEY` env var. Mirror LightRAG's `combined_auth` pattern in `raganything/api/dependencies.py`.

### Gap 6 — `track_id` lifecycle for `/documents/text` and `/documents/texts`

**Risk:** Low for v1 — no `/documents/track_status` endpoint in v1 scope.

**Resolution plan:** Generate a local track_id string and return it in the response. Actual status tracking via track_id is deferred.

### Gap 7 — multimodal upload routing

**Risk:** Medium — `process_document_complete_lightrag_api` parses PDF/image/Office files via MinerU or similar. This requires MinerU to be installed in the server environment.

**Resolution plan:** Document the optional extra dependency (`raganything[api]` extras). Return HTTP 500 with a clear error if MinerU is unavailable and an unsupported file type is uploaded.

---

## Deferred Scope

These are **explicitly out of v1** and must not be silently swallowed by routes:

- `POST /documents/scan` — requires input_dir file-watching and LightRAG's `doc_manager`
- `GET /documents/paginated` — requires offset/limit storage query
- `DELETE /documents/delete_document` — requires `adelete_by_doc_id`
- `POST /documents/reprocess_failed` — requires pipeline enqueue API
- `DELETE /documents/clear` — destructive; deferred
- `POST /documents/cancel_pipeline` — pipeline cancel flag management
- All graph mutation routes (`/graphs/*`)
- Ollama/OpenAI-compatible chat routes

Unsupported routes must return **HTTP 501 Not Implemented** (not 404, not silent success).

---

## Required Helpers in `raganything/query.py` or `raganything/processor.py`

**None required for v1.**

- `/query/data` calls `rag.lightrag.aquery_data` directly — no helper needed.
- `/documents/status_counts` calls `rag.lightrag.doc_status.get_all_status_counts()` directly — no helper needed.
- `/documents/pipeline_status` reads from `lightrag.kg.shared_storage` directly — no helper needed.

If `get_all_status_counts()` is absent (see Gap 1), a single helper in `processor.py` would suffice:

```python
async def get_doc_status_counts(self) -> dict[str, int]:
    """Fallback status counter if doc_status.get_all_status_counts() is unavailable."""
    from lightrag.base import DocStatus
    counts = {}
    for status in (DocStatus.PENDING, DocStatus.PROCESSING, DocStatus.PREPROCESSED, DocStatus.PROCESSED, DocStatus.FAILED):
        docs = await self.lightrag.get_docs_by_status(status)
        counts[status] = len(docs)
    return counts
```

---

## Stop Conditions

Escalate and do not merge v1 if:

1. `rag.lightrag.aquery_data` does not return the expected `{status, message, data, metadata}` shape in integration testing.
2. `doc_status.get_all_status_counts()` is absent **and** the per-status fallback causes unacceptable latency under load.
3. `process_document_complete_lightrag_api` introduces pipeline_status lock contention that corrupts status for concurrent uploads.

---

## Startup Requirements (v1)

```
pip install raganything[api]
# Extras to add to pyproject.toml:
#   fastapi>=0.111, uvicorn[standard], python-multipart, aiofiles
```

```bash
# Example startup
RAGANYTHING_WORKING_DIR=./rag_storage \
RAGANYTHING_LLM_MODEL=gpt-4o \
raganything-api
```
