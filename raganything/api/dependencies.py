from fastapi import Depends, HTTPException, Request


def get_rag(request: Request):
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(status_code=503, detail="RAGAnything instance is not configured")
    return rag


def get_lightrag(rag=Depends(get_rag)):
    if getattr(rag, "lightrag", None) is None:
        raise HTTPException(
            status_code=503,
            detail="LightRAG backend is not initialized. Provide llm_model_func and embedding_func.",
        )
    return rag.lightrag
