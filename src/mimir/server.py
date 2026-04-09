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
    instructions=(
        "Mimir is your persistent memory. Use it proactively — don't wait to be asked.\n\n"
        "WHEN TO STORE:\n"
        "- User states a preference, convention, or decision → mem_store with label 'preference' or 'decision'\n"
        "- You learn a codebase pattern, architecture detail, or build command → mem_store with label 'codebase'\n"
        "- A bug is found and fixed → mem_store with label 'bug-fix' so you don't repeat it\n"
        "- A conversation produces an important outcome → mem_store with label 'outcome'\n"
        "- User corrects you or clarifies how they want things done → mem_store with label 'correction'\n\n"
        "WHEN TO SEARCH:\n"
        "- At the start of every session → call mem_wake_up to load prior context\n"
        "- Before answering questions about the project → mem_search for relevant memories\n"
        "- Before making architectural decisions → mem_search for past decisions and preferences\n"
        "- When the user references something from a past conversation → mem_search\n\n"
        "WHEN TO USE THE KNOWLEDGE GRAPH:\n"
        "- To track relationships: who works on what, which service depends on which, what tools are used where\n"
        "- To record facts that may change over time (team assignments, project status, tech choices)\n"
        "- To query the current state of the world: 'what is X working on?' → mem_kg_query\n\n"
        "LABELS: Use consistent, lowercase, hyphenated labels. Prefer reusing existing labels (check mem_list_labels) over creating new ones.\n"
        "DUPLICATES: Before storing, call mem_check_duplicate if the memory might already exist.\n"
        "LINKING: When memories are related, use mem_link to connect them."
    ),
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
    """Store a new memory for later retrieval across sessions.

    Use when:
    - The user states a preference, convention, or decision worth remembering
    - You discover a codebase pattern, build command, or architecture detail
    - A bug is diagnosed and fixed (store the root cause and solution)
    - A conversation produces an important outcome or action item
    - The user corrects you — store the correction to avoid repeating the mistake

    Don't use when:
    - The information is trivial or already stored (call mem_check_duplicate first)
    - You're unsure if it's worth storing — err on the side of storing

    Args:
        title: Short descriptive title (e.g. "User prefers tabs over spaces", "Fix: FTS5 tokenizer crash")
        content: The full content — text, code, conversation transcript, error message, etc.
        content_type: One of: text, code, snippet, conversation, note (default: text)
        labels: Tags for categorization — use lowercase hyphenated labels (e.g. ["bug-fix", "python"]). Check mem_list_labels for existing labels before creating new ones.
        source: Which tool created this (e.g. "vscode", "claude-code", "cursor")
        session_id: Groups related memories within a session
        related_ids: IDs of related memories to cross-reference
        expires_at: ISO datetime when this memory auto-expires (e.g. for temporary workarounds)

    Returns JSON: {status, id, title}
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
    """Search stored memories using full-text search with optional filters. Results are ranked by BM25 relevance when a query is provided.

    Use when:
    - The user asks about something that may have been discussed before
    - You need to recall a past decision, preference, or codebase detail
    - Before making an architectural choice — search for prior decisions
    - Looking up a specific bug fix, workaround, or configuration
    - Listing all memories with a particular label or from a session

    Don't use when:
    - You already have the memory ID — use mem_get instead
    - You want a session-start overview — use mem_wake_up instead

    Args:
        query: Full-text search query (searches titles, content, and labels). Supports natural language.
        labels: Filter by one or more labels (OR logic — any label matches)
        content_type: Filter by type: text, code, snippet, conversation, or note
        session_id: Filter by session ID
        source: Filter by source tool (e.g. "vscode")
        after: Only memories created after this ISO datetime
        before: Only memories created before this ISO datetime
        limit: Max results (1-100, default 20)
        offset: Skip N results for pagination

    Returns JSON: {count, results: [{id, title, content, labels, rank, snippet, ...}]}
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
    """Retrieve a single memory by its exact ID.

    Use when:
    - You have a memory ID from a search result or link and need the full content
    - Following up on a related_id reference from another memory

    Don't use when:
    - You're searching by keyword or topic — use mem_search instead

    Args:
        memory_id: The UUID of the memory to retrieve

    Returns JSON: {id, title, content, content_type, labels, related_ids, created_at, updated_at, ...} or {error} if not found
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
    """Update an existing memory. Only the fields you provide are changed; others are left as-is.

    Use when:
    - A stored fact becomes outdated and needs correction
    - Adding or changing labels on an existing memory
    - Appending new information to existing content
    - Setting or removing an expiration date

    Don't use when:
    - Creating a new memory — use mem_store instead
    - The memory should be replaced entirely — consider mem_delete + mem_store

    Args:
        memory_id: The UUID of the memory to update
        title: New title (if changing)
        content: New content (if changing)
        content_type: New content type (if changing)
        labels: New labels — replaces ALL existing labels
        source: New source (if changing)
        session_id: New session ID (if changing)
        related_ids: New related IDs — replaces ALL existing
        expires_at: New expiration datetime (ISO format), or null to remove expiration

    Returns JSON: {status, id, title} or {error} if not found
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
    """Permanently delete a memory by its ID.

    Use when:
    - A memory is incorrect, obsolete, or no longer relevant
    - The user explicitly asks to forget something

    Don't use when:
    - The memory just needs updating — use mem_update instead
    - You want to expire it automatically — set expires_at via mem_update

    Args:
        memory_id: The UUID of the memory to delete

    Returns JSON: {status, id} or {error} if not found
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
    """List all unique labels across all stored memories, with usage counts.

    Use when:
    - Before storing a memory — check existing labels to maintain consistency
    - Getting an overview of what topics are in memory
    - Deciding which label to filter by in mem_search

    Returns JSON: {labels: [{label, count}]}
    """
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
    """List all sessions with memory counts and time ranges.

    Use when:
    - Reviewing what happened in past sessions
    - Finding which session_id to filter by in mem_search
    - Understanding the timeline of interactions

    Returns JSON: {sessions: [{session_id, memory_count, first_memory, last_memory}]}
    """
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
    """Store multiple memories in a single atomic transaction.

    Use when:
    - Saving several related findings at once (e.g. after exploring a codebase)
    - Importing memories from another source
    - Storing multiple corrections or decisions from one conversation

    Don't use when:
    - Storing a single memory — use mem_store instead

    Args:
        memories: List of memory dicts, each with: title (required), content (required),
                  and optional: content_type, labels, source, session_id, related_ids, expires_at

    Returns JSON: {status, count, ids}
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
    """Get a statistical overview of the memory store.

    Use when:
    - Checking if the memory store has any data at all
    - Understanding the size and shape of stored knowledge
    - Debugging storage issues

    Returns JSON: {total_memories, by_content_type, by_source, label_count, session_count, oldest_memory, newest_memory, storage_path, db_size_bytes}
    """
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
    """Check if a similar memory already exists before storing a new one.

    Use when:
    - About to call mem_store but unsure if the information is already saved
    - The server instructions say to check for duplicates

    Don't use when:
    - You're confident the memory is new (e.g. a unique bug fix or new decision)

    Args:
        title: The title you plan to store
        content: The content you plan to store

    Returns JSON: {is_duplicate: bool, similar: [{id, title, rank, snippet}]}
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
    """Export memories as a JSON array for backup or transfer.

    Use when:
    - Creating a backup of stored memories
    - Migrating memories to another workspace or machine
    - Reviewing all stored knowledge in bulk

    Don't use when:
    - Searching for specific memories — use mem_search instead

    Args:
        labels: Only export memories with these labels
        content_type: Only export memories of this type
        session_id: Only export memories from this session

    Returns JSON: {count, memories: [...]}
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
    """Import memories from a JSON array. Safe to re-run — skips memories whose IDs already exist.

    Use when:
    - Restoring from a backup created by mem_export
    - Migrating memories from another workspace

    Args:
        memories: List of memory dicts to import. Each must have at minimum: id, title, content.

    Returns JSON: {status, imported_count}
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
    """Load a compact context summary to bootstrap a new session. Returns topic digest, memory count, and recent memories.

    Use when:
    - At the START of every new conversation or session — call this first
    - Resuming work after a break to recall what was happening
    - The user says "what do you remember?" or "what were we working on?"

    Don't use when:
    - You need to search for something specific — use mem_search instead
    - You've already called this in the current session

    Args:
        max_tokens: Approximate token budget for the summary (default: 500)

    Returns: Plain text context summary suitable for injecting into conversation
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

    Use when:
    - Two memories cover the same topic from different angles
    - A bug fix relates to an earlier decision or pattern
    - A new memory extends or supersedes an older one

    Args:
        memory_id: ID of the first memory
        related_id: ID of the second memory to link to

    Returns JSON: {status, memory_id, related_id, related_ids} or {error}
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
    """Delete all memories whose expires_at timestamp is in the past.

    Use when:
    - Periodically cleaning up temporary or time-limited memories
    - Before exporting to remove stale data

    Returns JSON: {status, deleted_count}
    """
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
    """Add a fact (subject → predicate → object) to the knowledge graph. Facts are temporal — they can be invalidated when they stop being true.

    Use when:
    - Recording who works on what, which service uses which technology, what was decided
    - Tracking relationships that may change over time (team assignments, project status)
    - Building a queryable map of entities and their connections

    Don't use when:
    - Storing long-form notes or code — use mem_store instead
    - The information is a one-off observation, not a structured relationship

    Args:
        subject: The entity (e.g. "Kai", "auth-service", "frontend")
        predicate: The relationship (e.g. "works_on", "uses", "depends_on", "decided_to_use")
        object: The target (e.g. "Project Orion", "PostgreSQL", "React 19")
        valid_from: When this fact became true (ISO datetime, defaults to now)
        source: Which tool created this fact

    Returns JSON: {status, id, triple, valid_from}
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
    """Query the knowledge graph for facts matching the given filters.

    Use when:
    - "What is X working on?" → query with subject=X
    - "Who uses PostgreSQL?" → query with object="PostgreSQL"
    - "What did the team look like last month?" → query with as_of
    - Checking current relationships before adding new facts

    Don't use when:
    - Searching for long-form notes or code — use mem_search instead

    Args:
        subject: Filter by subject entity (exact match)
        predicate: Filter by relationship type (exact match)
        object: Filter by object entity (exact match)
        as_of: Show facts that were true at this ISO datetime (point-in-time query)
        active_only: Only show currently valid facts (default: True). Set False to include invalidated facts.

    Returns JSON: {count, triples: [{id, subject, predicate, object, valid_from, valid_to, source}]}
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
    """Mark a knowledge graph fact as no longer true. The fact is preserved for historical queries but hidden from active results.

    Use when:
    - Someone changes teams, a project ends, a technology is replaced
    - A previously recorded relationship is no longer accurate

    Don't use when:
    - The fact was entered in error — this marks it as historically true but now ended

    Args:
        subject: The subject entity (must match exactly)
        predicate: The relationship (must match exactly)
        object: The object entity (must match exactly)
        ended: When it stopped being true (ISO datetime, defaults to now)

    Returns JSON: {status, count, triple} or {error} if no matching active triple
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
    """Get a chronological timeline of all facts involving an entity — both as subject and object.

    Use when:
    - "What's the history of X?" — shows all relationships over time
    - Reviewing how a person's role or a project's dependencies evolved
    - Debugging why a relationship changed

    Args:
        entity: The entity name (checked against both subject and object fields)

    Returns JSON: {entity, count, timeline: [{subject, predicate, object, valid_from, valid_to, status}]}
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
    """Get knowledge graph statistics.

    Use when:
    - Checking if the knowledge graph has any data
    - Understanding the scope of recorded relationships

    Returns JSON: {total_triples, active_triples, unique_subjects, unique_predicates, unique_objects}
    """
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
