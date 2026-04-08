"""Pydantic data models for mimir."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Type of content stored in a memory."""
    TEXT = "text"
    CODE = "code"
    SNIPPET = "snippet"
    CONVERSATION = "conversation"
    NOTE = "note"


class Memory(BaseModel):
    """A single memory entry."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    content_type: ContentType = Field(default=ContentType.TEXT)
    labels: list[str] = Field(default_factory=list)
    source: str = Field(default="unknown")
    session_id: str = Field(default="default")
    related_ids: list[str] = Field(default_factory=list)
    expires_at: Optional[str] = Field(default=None)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MemorySearchResult(BaseModel):
    """A search result with relevance info."""
    memory: Memory
    rank: float = 0.0
    snippet: str = ""


class SearchFilters(BaseModel):
    """Filters for searching memories."""
    query: Optional[str] = None
    labels: Optional[list[str]] = None
    content_type: Optional[ContentType] = None
    session_id: Optional[str] = None
    source: Optional[str] = None
    after: Optional[str] = None
    before: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class LabelCount(BaseModel):
    """A label with its usage count."""
    label: str
    count: int


class SessionInfo(BaseModel):
    """Info about a stored session."""
    session_id: str
    memory_count: int
    first_memory: str
    last_memory: str


class MemoryStats(BaseModel):
    """Overall memory store statistics."""
    total_memories: int
    by_content_type: dict[str, int]
    by_source: dict[str, int]
    label_count: int
    session_count: int
    oldest_memory: Optional[str] = None
    newest_memory: Optional[str] = None
    storage_path: str
    db_size_bytes: int


class DuplicateCheck(BaseModel):
    """Result of a duplicate check."""
    is_duplicate: bool
    similar: list[MemorySearchResult] = Field(default_factory=list)


class KnowledgeTriple(BaseModel):
    """A temporal entity-relationship triple."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    valid_from: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    valid_to: Optional[str] = Field(default=None)
    source: str = Field(default="unknown")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class KGStats(BaseModel):
    """Knowledge graph statistics."""
    total_triples: int
    active_triples: int
    unique_subjects: int
    unique_predicates: int
    unique_objects: int
