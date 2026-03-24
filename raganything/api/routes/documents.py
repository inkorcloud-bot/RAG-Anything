import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from ..dependencies import get_rag
from ..models import InsertTextRequest, InsertTextsRequest

router = APIRouter(prefix="/documents")


def _normalize_file_path(file_path: str | None) -> str:
    return file_path.strip() if file_path and file_path.strip() else "unknown_source"


def _serialize_doc(doc_id: str, doc) -> dict:
    if isinstance(doc, dict):
        response = dict(doc)
        response["file_path"] = _normalize_file_path(response.get("file_path"))
        return response

    return {
        "id": doc_id,
        "content_summary": doc.content_summary,
        "content_length": doc.content_length,
        "status": str(doc.status),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "track_id": getattr(doc, "track_id", None),
        "chunks_count": getattr(doc, "chunks_count", None),
        "error_msg": getattr(doc, "error_msg", None),
        "metadata": getattr(doc, "metadata", None),
        "file_path": _normalize_file_path(getattr(doc, "file_path", None)),
    }


@router.post("/text")
async def insert_text(request: InsertTextRequest, rag=Depends(get_rag)):
    text = request.text.strip()
    file_paths = [request.file_source] if request.file_source else None
    await rag.lightrag.ainsert(input=text, file_paths=file_paths)
    return {"status": "success", "message": "Text inserted successfully."}


@router.post("/texts")
async def insert_texts(request: InsertTextsRequest, rag=Depends(get_rag)):
    await rag.lightrag.ainsert(
        input=request.texts,
        file_paths=request.file_sources,
    )
    return {"status": "success", "message": "Texts inserted successfully."}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_id: str | None = Form(default=None),
    parser: str | None = Form(default=None),
    scheme_name: str | None = Form(default=None),
    rag=Depends(get_rag),
):
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=422, detail="Filename cannot be empty")

    temp_dir = None
    temp_path = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="raganything-upload-")
        temp_path = str(Path(temp_dir) / filename)
        with open(temp_path, "wb") as tmp:
            tmp.write(await file.read())

        await rag.process_document_complete_lightrag_api(
            temp_path,
            doc_id=doc_id,
            parser=parser,
            scheme_name=scheme_name,
        )
        return {
            "status": "success",
            "message": f"File '{filename}' uploaded successfully.",
            "track_id": "",
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        if temp_dir and os.path.isdir(temp_dir):
            os.rmdir(temp_dir)


@router.get("")
async def get_documents(
    status_filter: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1),
    sort_field: str = Query(default="updated_at"),
    sort_direction: str = Query(default="desc"),
    rag=Depends(get_rag),
):
    effective_status_filter = status_filter if status_filter is not None else status
    paginated = await rag.lightrag.doc_status.get_docs_paginated(
        status_filter=effective_status_filter,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_direction=sort_direction,
    )
    status_counts = await rag.lightrag.doc_status.get_all_status_counts()

    if isinstance(paginated, dict):
        documents = [_serialize_doc(doc.get("id", ""), doc) for doc in paginated.get("documents", [])]
        total_count = paginated.get("total", len(documents))
        total_pages = (total_count + page_size - 1) // page_size if page_size else 0
        pagination = {
            "page": paginated.get("page", page),
            "page_size": paginated.get("page_size", page_size),
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    else:
        documents_with_ids, total_count = paginated
        documents = [_serialize_doc(doc_id, doc) for doc_id, doc in documents_with_ids]
        total_pages = (total_count + page_size - 1) // page_size if page_size else 0
        pagination = {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    return {
        "documents": documents,
        "pagination": pagination,
        "status_counts": status_counts,
    }


@router.get("/status_counts")
async def get_document_status_counts(rag=Depends(get_rag)):
    return {"status_counts": await rag.lightrag.doc_status.get_all_status_counts()}


@router.get("/pipeline_status")
async def get_pipeline_status(rag=Depends(get_rag)):
    if hasattr(rag, "pipeline_status"):
        status = dict(rag.pipeline_status)
        if not isinstance(status.get("update_status"), dict):
            status["update_status"] = {}
        return status

    from lightrag.kg.shared_storage import (
        get_all_update_flags_status,
        get_namespace_data,
        get_namespace_lock,
    )

    pipeline_status = await get_namespace_data("pipeline_status", workspace=rag.lightrag.workspace)
    pipeline_status_lock = get_namespace_lock("pipeline_status", workspace=rag.lightrag.workspace)
    async with pipeline_status_lock:
        status_dict = dict(pipeline_status)
    status_dict["update_status"] = await get_all_update_flags_status(workspace=rag.lightrag.workspace)
    if "history_messages" in status_dict:
        status_dict["history_messages"] = list(status_dict["history_messages"])
    return status_dict
