from typing import Any, Dict, List, Literal, Optional

from lightrag import QueryParam
from pydantic import BaseModel, Field, field_validator, model_validator


class QueryRequest(BaseModel):
    query: str = Field(min_length=3)
    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = "mix"
    include_references: bool = True
    include_chunk_content: bool = False
    stream: Optional[bool] = True
    response_type: Optional[str] = None
    top_k: Optional[int] = None
    chunk_top_k: Optional[int] = None
    max_entity_tokens: Optional[int] = None
    max_relation_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None
    hl_keywords: List[str] = Field(default_factory=list)
    ll_keywords: List[str] = Field(default_factory=list)
    conversation_history: Optional[List[Dict[str, Any]]] = None
    enable_rerank: Optional[bool] = None

    @field_validator("query", mode="after")
    @classmethod
    def strip_query(cls, value: str) -> str:
        return value.strip()

    def to_query_params(self, is_stream: bool) -> QueryParam:
        request_data = self.model_dump(
            exclude_none=True,
            exclude={"query", "include_chunk_content"},
        )
        param = QueryParam(**request_data)
        param.stream = is_stream
        return param


class InsertTextRequest(BaseModel):
    text: str = Field(min_length=1)
    file_source: Optional[str] = None

    @model_validator(mode="after")
    def text_must_be_non_empty_after_strip(self) -> "InsertTextRequest":
        if not self.text.strip():
            raise ValueError("text must not be empty or whitespace only")
        return self


class InsertTextsRequest(BaseModel):
    texts: List[str] = Field(min_length=1)
    file_sources: Optional[List[str]] = None

    @model_validator(mode="after")
    def file_sources_length_must_match(self) -> "InsertTextsRequest":
        if self.file_sources is not None and len(self.file_sources) != len(self.texts):
            raise ValueError("file_sources length must match texts length")
        return self
