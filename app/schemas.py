from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    mode: Literal["auto", "rag", "sql"] = "auto"


class Source(BaseModel):
    job_id: int
    title: str
    company: str
    city: str
    content: str
    score: float


class ChatResponse(BaseModel):
    route: Literal["rag", "sql"]
    route_reason: str
    mode: Literal["demo", "live"]
    answer: str
    sources: List[Source] = Field(default_factory=list)
    sql: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    attempts: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_ms: int = 0
    truncated: bool = False
