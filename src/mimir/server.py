"""Mimir MCP Server - Local LLM Memory Store."""

import json
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .models import ContentType, KnowledgeTriple, Memory, SearchFilters
from .store import MemoryStore, resolve_storage_dir

mcp = FastMCP(
    "mimir",
    instructions="Mimir is a local memory store for LLMs. Use it to persist context, code snippets, notes, and conversations across sessions. Store memories with labels for easy retrieval later.",
)

_store: Optional[MemoryStore] = None
_location: str = "global"  # Set via --location arg or MCP config


def _get_store() -> MemoryStore:
    global _store
    if _store is None:
        storage_dir = resolve_storage_dir(_location)
        _store = MemoryStore(storage_dir)
    return _store


@mcp.tool(
    name="mem_store",
    annotations=ToolAnnotations(
        title="Store Memory",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def mem_store(
    title: str,
    content: str,
    content_type: str = "text",
    labels: Optional[list[str]] = None,
    source: str = "unknown",
    session_id: str = "default",
    related_ids: Optional[list[str]] = None,
    expires_at: Optional[str] = None,
) -> str:
    """Store a new memory. Use this to save context, code, notes, or conversations for later retrieval.

    Args:
        title: Short descriptive title for the memory (e.g. "Python FTS5 setup", "User preferences")
        content: The full content to store - text, code, conversation transcript, etc.
        content_type: Type of content: text, code, snippet, conversation, or note (default: text)
        labels: List of tags for categorization (e.g. ["python", "database", "setup"])
        source: Which tool created this memory (e.g. "vscode", "claude-code")
        session_id: Session identifier to group related memories
        related_ids: List of memory IDs this memory is related to
        expires_at: ISO datetime when this memory should expire and be auto-purged (optional)
    """
    store = _get_store()
    memory = Memory(
        title=title,
        content=content,
        content_type=ContentType(content_type),
        labels=labels or [],
        source=source,
        session_id=session_id,
        related_ids=related_ids or [],
        expires_at=expires_at,
    )
    stored = store.store(memory)
    return json.dumps({"status": "stored", "id": stored.id, "title": stored.title})


@mcp.tool(
    name="mem_search",
    annotations=ToolAnnotations(
        title="Search Memories",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_search(
    query: Optional[str] = None,
    labels: Optional[list[str]] = None,
    content_type: Optional[str] = None,
    session_id: Optional[str] = None,
    source: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Search stored memories using full-text search with optional filters.

    When a query is provided, results are ranked by relevance (BM25).
    Without a query, returns recent memories matching the filters.

    Args:
        query: Full-text search query (searches titles, content, and labels)
        labels: Filter by one or more labels (OR logic)
        content_type: Filter by content type: text, code, snippet, conversation, or note
        session_id: Filter by session ID
        source: Filter by source tool
        after: Only return memories created after this ISO datetime
        before: Only return memories created before this ISO datetime
        limit: Maximum results to return (1-100, default 20)
        offset: Number of results to skip for pagination
    """
    store = _get_store()
    ct = ContentType(content_type) if content_type else None
    filters = SearchFilters(
        query=query,
        labels=labels,
        content_type=ct,
        session_id=session_id,
        source=source,
        after=after,
        before=before,
        limit=limit,
        offset=offset,
    )
    results = store.search(filters)
    return json.dumps(
        {
            "count": len(results),
            "results": [
                {
                    "id": r.memory.id,
                    "title": r.memory.title,
                    "content": r.memory.content,
                    "content_type": r.memory.content_type.value,
                    "labels": r.memory.labels,
                    "source": r.memory.source,
                    "session_id": r.memory.session_id,
                    "related_ids": r.memory.related_ids,
                    "expires_at": r.memory.expires_at,
                    "created_at": r.memory.created_at,
                    "rank": r.rank,
                    "snippet": r.snippet,
                }
                for r in results
            ],
        },
        indent=2,
    )


@mcp.tool(
    name="mem_get",
    annotations=ToolAnnotations(
        title="Get Memory",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_get(memory_id: str) -> str:
    """Get a specific memory by its ID.

    Args:
        memory_id: The unique ID of the memory to retrieve
    """
    store = _get_store()
    memory = store.get(memory_id)
    if memory is None:
        return json.dumps({"error": "Memory not found", "id": memory_id})
    return json.dumps(
        {
            "id": memory.id,
            "title": memory.title,
            "content": memory.content,
            "content_type": memory.content_type.value,
            "labels": memory.labels,
            "source": memory.source,
            "session_id": memory.session_id,
            "related_ids": memory.related_ids,
            "expires_at": memory.expires_at,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
        },
        indent=2,
    )


@mcp.tool(
    name="mem_update",
    annotations=ToolAnnotations(
        title="Update Memory",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_update(
    memory_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    content_type: Optional[str] = None,
    labels: Optional[list[str]] = None,
    source: Optional[str] = None,
    session_id: Optional[str] = None,
    related_ids: Optional[list[str]] = None,
    expires_at: Optional[str] = None,
) -> str:
    """Update an existing memory. Only provided fields are changed.

    Args:
        memory_id: The unique ID of the memory to update
        title: New title (if changing)
        content: New content (if changing)
        content_type: New content type (if changing)
        labels: New labels (replaces all existing labels)
        source: New source (if changing)
        session_id: New session ID (if changing)
        related_ids: New related memory IDs (replaces all existing)
        expires_at: New expiration datetime (ISO format)
    """
    store = _get_store()
    kwargs: dict = {}
    if title is not None:
        kwargs["title"] = title
    if content is not None:
        kwargs["content"] = content
    if content_type is not None:
        kwargs["content_type"] = ContentType(content_type)
    if labels is not None:
        kwargs["labels"] = labels
    if source is not None:
        kwargs["source"] = source
    if session_id is not None:
        kwargs["session_id"] = session_id
    if related_ids is not None:
        kwargs["related_ids"] = related_ids
    if expires_at is not None:
        kwargs["expires_at"] = expires_at

    updated = store.update(memory_id, **kwargs)
    if updated is None:
        return json.dumps({"error": "Memory not found", "id": memory_id})
    return json.dumps({"status": "updated", "id": updated.id, "title": updated.title})


@mcp.tool(
    name="mem_delete",
    annotations=ToolAnnotations(
        title="Delete Memory",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_delete(memory_id: str) -> str:
    """Delete a memory by its ID.

    Args:
        memory_id: The unique ID of the memory to delete
    """
    store = _get_store()
    deleted = store.delete(memory_id)
    if not deleted:
        return json.dumps({"error": "Memory not found", "id": memory_id})
    return json.dumps({"status": "deleted", "id": memory_id})


@mcp.tool(
    name="mem_list_labels",
    annotations=ToolAnnotations(
        title="List Labels",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_list_labels() -> str:
    """List all unique labels across all memories, with usage counts. Useful for discovering what categories of memories exist."""
    store = _get_store()
    labels = store.list_labels()
    return json.dumps(
        {"labels": [{"label": lc.label, "count": lc.count} for lc in labels]}
    )


@mcp.tool(
    name="mem_list_sessions",
    annotations=ToolAnnotations(
        title="List Sessions",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_list_sessions() -> str:
    """List all sessions with memory counts and time ranges. Sessions group related memories from a single interaction."""
    store = _get_store()
    sessions = store.list_sessions()
    return json.dumps(
        {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "memory_count": s.memory_count,
                    "first_memory": s.first_memory,
                    "last_memory": s.last_memory,
                }
                for s in sessions
            ]
        }
    )


@mcp.tool(
    name="mem_batch_store",
    annotations=ToolAnnotations(
        title="Batch Store Memories",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def mem_batch_store(memories: list[dict]) -> str:
    """Store multiple memories at once in a single transaction. Efficient for bulk imports.

    Args:
        memories: List of memory objects, each with: title (required), content (required),
                  and optional: content_type, labels, source, session_id
    """
    store = _get_store()
    parsed = []
    for m in memories:
        parsed.append(
            Memory(
                title=m["title"],
                content=m["content"],
                content_type=ContentType(m.get("content_type", "text")),
                labels=m.get("labels", []),
                source=m.get("source", "unknown"),
                session_id=m.get("session_id", "default"),
                related_ids=m.get("related_ids", []),
                expires_at=m.get("expires_at"),
            )
        )
    stored = store.batch_store(parsed)
    return json.dumps(
        {
            "status": "stored",
            "count": len(stored),
            "ids": [s.id for s in stored],
        }
    )


# ── New tools ─────────────────────────────────────────────────


@mcp.tool(
    name="mem_stats",
    annotations=ToolAnnotations(
        title="Memory Statistics",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_stats() -> str:
    """Get an overview of the memory store: total memories, breakdowns by type/source, label and session counts, date range, and storage size."""
    store = _get_store()
    s = store.stats()
    return json.dumps(
        {
            "total_memories": s.total_memories,
            "by_content_type": s.by_content_type,
            "by_source": s.by_source,
            "label_count": s.label_count,
            "session_count": s.session_count,
            "oldest_memory": s.oldest_memory,
            "newest_memory": s.newest_memory,
            "storage_path": s.storage_path,
            "db_size_bytes": s.db_size_bytes,
        },
        indent=2,
    )


@mcp.tool(
    name="mem_check_duplicate",
    annotations=ToolAnnotations(
        title="Check for Duplicate Memory",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_check_duplicate(title: str, content: str) -> str:
    """Check if a similar memory already exists before storing. Returns whether a duplicate was found and the closest matches.

    Args:
        title: The title of the memory you plan to store
        content: The content of the memory you plan to store
    """
    store = _get_store()
    result = store.check_duplicate(title, content)
    return json.dumps(
        {
            "is_duplicate": result.is_duplicate,
            "similar": [
                {
                    "id": r.memory.id,
                    "title": r.memory.title,
                    "rank": r.rank,
                    "snippet": r.snippet,
                }
                for r in result.similar
            ],
        },
        indent=2,
    )


@mcp.tool(
    name="mem_export",
    annotations=ToolAnnotations(
        title="Export Memories",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_export(
    labels: Optional[list[str]] = None,
    content_type: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Export memories as JSON. Optionally filter by labels, content type, or session. Returns a JSON array of all matching memories.

    Args:
        labels: Only export memories with these labels
        content_type: Only export memories of this type
        session_id: Only export memories from this session
    """
    store = _get_store()
    filters = None
    if labels or content_type or session_id:
        ct = ContentType(content_type) if content_type else None
        filters = SearchFilters(
            labels=labels, content_type=ct, session_id=session_id, limit=100
        )
    data = store.export_memories(filters)
    return json.dumps({"count": len(data), "memories": data}, indent=2, default=str)


@mcp.tool(
    name="mem_import",
    annotations=ToolAnnotations(
        title="Import Memories",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_import(memories: list[dict]) -> str:
    """Import memories from a JSON array. Skips any memories whose IDs already exist (safe to re-run).

    Args:
        memories: List of memory objects to import. Each must have at minimum: id, title, content.
    """
    store = _get_store()
    imported = store.import_memories(memories)
    return json.dumps({"status": "imported", "imported_count": imported})


@mcp.tool(
    name="mem_wake_up",
    annotations=ToolAnnotations(
        title="Wake-up Context",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_wake_up(max_tokens: int = 500) -> str:
    """Load a compact summary of your memory context for session start. Returns a digest of topics, total memory count, and the most recent memories — designed to be injected into system context so the AI 'remembers' the user.

    Args:
        max_tokens: Approximate token budget for the summary (default: 500)
    """
    store = _get_store()
    context = store.wake_up(max_tokens=max_tokens)
    return context


@mcp.tool(
    name="mem_link",
    annotations=ToolAnnotations(
        title="Link Memories",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_link(memory_id: str, related_id: str) -> str:
    """Create a bidirectional link between two related memories.

    Args:
        memory_id: ID of the first memory
        related_id: ID of the second memory to link to
    """
    store = _get_store()
    result = store.link(memory_id, related_id)
    if result is None:
        return json.dumps({"error": "One or both memory IDs not found"})
    return json.dumps(
        {
            "status": "linked",
            "memory_id": memory_id,
            "related_id": related_id,
            "related_ids": result.related_ids,
        }
    )


@mcp.tool(
    name="mem_purge_expired",
    annotations=ToolAnnotations(
        title="Purge Expired Memories",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_purge_expired() -> str:
    """Delete all memories whose expires_at timestamp is in the past. Returns the count of purged memories."""
    store = _get_store()
    count = store.purge_expired()
    return json.dumps({"status": "purged", "deleted_count": count})


# ── Knowledge Graph tools ─────────────────────────────────────


@mcp.tool(
    name="mem_kg_add",
    annotations=ToolAnnotations(
        title="Add Knowledge Triple",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def mem_kg_add(
    subject: str,
    predicate: str,
    object: str,
    valid_from: Optional[str] = None,
    source: str = "unknown",
) -> str:
    """Add a fact (subject-predicate-object triple) to the knowledge graph. Facts have temporal validity and can be invalidated later.

    Args:
        subject: The entity the fact is about (e.g. "Kai", "auth-service")
        predicate: The relationship (e.g. "works_on", "decided_to_use", "assigned_to")
        object: The target of the relationship (e.g. "Project Orion", "PostgreSQL")
        valid_from: When this fact became true (ISO datetime, defaults to now)
        source: Which tool created this fact
    """
    store = _get_store()
    triple = KnowledgeTriple(
        subject=subject,
        predicate=predicate,
        object=object,
        source=source,
    )
    if valid_from:
        triple.valid_from = valid_from
    stored = store.kg_add(triple)
    return json.dumps(
        {
            "status": "added",
            "id": stored.id,
            "triple": f"{stored.subject} → {stored.predicate} → {stored.object}",
            "valid_from": stored.valid_from,
        }
    )


@mcp.tool(
    name="mem_kg_query",
    annotations=ToolAnnotations(
        title="Query Knowledge Graph",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_kg_query(
    subject: Optional[str] = None,
    predicate: Optional[str] = None,
    object: Optional[str] = None,
    as_of: Optional[str] = None,
    active_only: bool = True,
) -> str:
    """Query the knowledge graph for facts. Filter by subject, predicate, object, or point-in-time.

    Args:
        subject: Filter by subject entity
        predicate: Filter by relationship type
        object: Filter by object entity
        as_of: Show facts as of this ISO datetime (for historical queries)
        active_only: Only show currently valid facts (default: True)
    """
    store = _get_store()
    triples = store.kg_query(
        subject=subject,
        predicate=predicate,
        object_val=object,
        as_of=as_of,
        active_only=active_only,
    )
    return json.dumps(
        {
            "count": len(triples),
            "triples": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object,
                    "valid_from": t.valid_from,
                    "valid_to": t.valid_to,
                    "source": t.source,
                }
                for t in triples
            ],
        },
        indent=2,
    )


@mcp.tool(
    name="mem_kg_invalidate",
    annotations=ToolAnnotations(
        title="Invalidate Knowledge Triple",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_kg_invalidate(
    subject: str,
    predicate: str,
    object: str,
    ended: Optional[str] = None,
) -> str:
    """Mark a fact as no longer true. The fact is kept for historical queries but won't appear in active results.

    Args:
        subject: The subject entity
        predicate: The relationship
        object: The object entity
        ended: When the fact stopped being true (ISO datetime, defaults to now)
    """
    store = _get_store()
    count = store.kg_invalidate(subject, predicate, object, ended=ended)
    if count == 0:
        return json.dumps({"error": "No matching active triple found"})
    return json.dumps(
        {
            "status": "invalidated",
            "count": count,
            "triple": f"{subject} → {predicate} → {object}",
        }
    )


@mcp.tool(
    name="mem_kg_timeline",
    annotations=ToolAnnotations(
        title="Entity Timeline",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_kg_timeline(entity: str) -> str:
    """Get the chronological timeline of all facts involving an entity (as subject or object).

    Args:
        entity: The entity name to get the timeline for
    """
    store = _get_store()
    triples = store.kg_timeline(entity)
    return json.dumps(
        {
            "entity": entity,
            "count": len(triples),
            "timeline": [
                {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object,
                    "valid_from": t.valid_from,
                    "valid_to": t.valid_to,
                    "status": "ended" if t.valid_to else "active",
                }
                for t in triples
            ],
        },
        indent=2,
    )


@mcp.tool(
    name="mem_kg_stats",
    annotations=ToolAnnotations(
        title="Knowledge Graph Statistics",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def mem_kg_stats() -> str:
    """Get knowledge graph statistics: total triples, active triples, unique entities and predicates."""
    store = _get_store()
    s = store.kg_stats()
    return json.dumps(
        {
            "total_triples": s.total_triples,
            "active_triples": s.active_triples,
            "unique_subjects": s.unique_subjects,
            "unique_predicates": s.unique_predicates,
            "unique_objects": s.unique_objects,
        },
        indent=2,
    )


def main():
    """Entry point for the mimir MCP server.

    Accepts --location=global|workspace to control storage location.
    Default is 'global' (~/.mimir/memories/<workspace>/).
    'workspace' stores in <cwd>/.mimir/memories/.
    """
    global _location
    for arg in sys.argv[1:]:
        if arg.startswith("--location="):
            value = arg.split("=", 1)[1]
            if value in ("global", "workspace"):
                _location = value
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
