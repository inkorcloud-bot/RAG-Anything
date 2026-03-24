from fastapi import HTTPException, Request


def get_rag(request: Request):
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(status_code=503, detail="RAGAnything instance is not configured")
    return rag
