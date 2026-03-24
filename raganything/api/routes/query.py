import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..dependencies import get_lightrag
from ..models import QueryRequest

router = APIRouter()


def _enrich_references(result: dict, include_chunk_content: bool) -> list[dict]:
    references = list(result.get("data", {}).get("references", []))
    if not include_chunk_content:
        return references

    ref_id_to_content = {}
    for chunk in result.get("data", {}).get("chunks", []):
        ref_id = chunk.get("reference_id")
        content = chunk.get("content")
        if ref_id and content:
            ref_id_to_content.setdefault(ref_id, []).append(content)

    enriched_references = []
    for ref in references:
        ref_copy = ref.copy()
        ref_id = ref.get("reference_id")
        if ref_id in ref_id_to_content:
            ref_copy["content"] = ref_id_to_content[ref_id]
        enriched_references.append(ref_copy)
    return enriched_references


@router.post("/query")
async def query_text(request: QueryRequest, lightrag=Depends(get_lightrag)):
    result = await lightrag.aquery_llm(
        request.query,
        param=request.to_query_params(False),
    )
    llm_response = result.get("llm_response", {})
    response = {"response": llm_response.get("content", "") or "No relevant context found for the query."}
    if request.include_references:
        response["references"] = _enrich_references(result, request.include_chunk_content)
    return response


@router.post("/query/stream")
async def query_text_stream(request: QueryRequest, lightrag=Depends(get_lightrag)):
    result = await lightrag.aquery_llm(
        request.query,
        param=request.to_query_params(request.stream if request.stream is not None else True),
    )

    async def stream_generator():
        references = _enrich_references(result, request.include_chunk_content)
        llm_response = result.get("llm_response", {})

        if llm_response.get("is_streaming"):
            if request.include_references:
                yield f"{json.dumps({'references': references})}\n"
            response_stream = llm_response.get("response_iterator")
            if response_stream:
                try:
                    async for chunk in response_stream:
                        if chunk:
                            yield f"{json.dumps({'response': chunk})}\n"
                except Exception as exc:
                    yield f"{json.dumps({'error': str(exc)})}\n"
            return

        complete_response = {
            "response": llm_response.get("content", "") or "No relevant context found for the query."
        }
        if request.include_references:
            complete_response["references"] = references
        yield f"{json.dumps(complete_response)}\n"

    return StreamingResponse(stream_generator(), media_type="application/x-ndjson")


@router.post("/query/data")
async def query_data(request: QueryRequest, lightrag=Depends(get_lightrag)):
    return await lightrag.aquery_data(
        request.query,
        param=request.to_query_params(False),
    )
