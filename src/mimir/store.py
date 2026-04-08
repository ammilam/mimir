"""SQLite storage engine with FTS5 full-text search for mimir."""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    ContentType,
    DuplicateCheck,
    KGStats,
    KnowledgeTriple,
    LabelCount,
    Memory,
    MemorySearchResult,
    MemoryStats,
    SearchFilters,
    SessionInfo,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text',
    labels TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'unknown',
    session_id TEXT NOT NULL DEFAULT 'default',
    related_ids TEXT NOT NULL DEFAULT '[]',
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title,
    content,
    labels,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, content, labels)
    VALUES (new.rowid, new.title, new.content, new.labels);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, labels)
    VALUES ('delete', old.rowid, old.title, old.content, old.labels);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, labels)
    VALUES ('delete', old.rowid, old.title, old.content, old.labels);
    INSERT INTO memories_fts(rowid, title, content, labels)
    VALUES (new.rowid, new.title, new.content, new.labels);
END;

CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_content_type ON memories(content_type);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at);

CREATE TABLE IF NOT EXISTS knowledge_graph (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kg_subject ON knowledge_graph(subject);
CREATE INDEX IF NOT EXISTS idx_kg_object ON knowledge_graph(object);
CREATE INDEX IF NOT EXISTS idx_kg_predicate ON knowledge_graph(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_valid_to ON knowledge_graph(valid_to);
"""

_MIGRATION_SQL = """
-- Add columns if missing (idempotent via try/except in Python)
ALTER TABLE memories ADD COLUMN related_ids TEXT NOT NULL DEFAULT '[]';
ALTER TABLE memories ADD COLUMN expires_at TEXT;
"""


def resolve_storage_dir(location: str = "global") -> Path:
    """Resolve the storage directory based on location mode.

    Args:
        location: 'global' stores in ~/.mimir/memories/<workspace>/
                  'workspace' stores in <cwd>/.mimir/memories/
    """
    if location == "workspace":
        return Path.cwd() / ".mimir" / "memories"

    # Global: ~/.mimir/memories/<workspace-name>/
    workspace_name = Path.cwd().name
    # Sanitize workspace name for filesystem safety
    workspace_name = re.sub(r'[^\w\-.]', '_', workspace_name)
    return Path.home() / ".mimir" / "memories" / workspace_name


class MemoryStore:
    """SQLite-backed memory store with FTS5 full-text search."""

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            storage_dir = resolve_storage_dir()
        self._storage_dir = storage_dir
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._storage_dir / "mimir.db"
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA_SQL)
            self._run_migrations()
        return self._conn

    def _run_migrations(self) -> None:
        """Add new columns to existing databases (idempotent)."""
        assert self._conn is not None
        for stmt in _MIGRATION_SQL.strip().split(";"):
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            try:
                self._conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            content_type=ContentType(row["content_type"]),
            labels=json.loads(row["labels"]),
            source=row["source"],
            session_id=row["session_id"],
            related_ids=json.loads(row["related_ids"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def store(self, memory: Memory) -> Memory:
        """Store a new memory. Returns the stored memory."""
        conn = self._get_conn()
        labels_json = json.dumps(memory.labels)
        related_json = json.dumps(memory.related_ids)
        conn.execute(
            """INSERT INTO memories (id, title, content, content_type, labels, source, session_id, related_ids, expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory.id,
                memory.title,
                memory.content,
                memory.content_type.value,
                labels_json,
                memory.source,
                memory.session_id,
                related_json,
                memory.expires_at,
                memory.created_at,
                memory.updated_at,
            ),
        )
        conn.commit()
        return memory

    def batch_store(self, memories: list[Memory]) -> list[Memory]:
        """Store multiple memories in a single transaction."""
        conn = self._get_conn()
        for mem in memories:
            labels_json = json.dumps(mem.labels)
            related_json = json.dumps(mem.related_ids)
            conn.execute(
                """INSERT INTO memories (id, title, content, content_type, labels, source, session_id, related_ids, expires_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mem.id,
                    mem.title,
                    mem.content,
                    mem.content_type.value,
                    labels_json,
                    mem.source,
                    mem.session_id,
                    related_json,
                    mem.expires_at,
                    mem.created_at,
                    mem.updated_at,
                ),
            )
        conn.commit()
        return memories

    def get(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update(self, memory_id: str, **kwargs: object) -> Optional[Memory]:
        """Update a memory. Only provided fields are updated."""
        existing = self.get(memory_id)
        if existing is None:
            return None

        updates: dict[str, object] = {}
        for field in ("title", "content", "content_type", "labels", "source", "session_id", "related_ids", "expires_at"):
            if field in kwargs and kwargs[field] is not None:
                updates[field] = kwargs[field]

        if not updates:
            return existing

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clauses = []
        params: list[object] = []
        for key, val in updates.items():
            set_clauses.append(f"{key} = ?")
            if key in ("labels", "related_ids"):
                params.append(json.dumps(val))
            elif key == "content_type" and isinstance(val, ContentType):
                params.append(val.value)
            else:
                params.append(val)
        params.append(memory_id)

        conn = self._get_conn()
        conn.execute(
            f"UPDATE memories SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory. Returns True if deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cursor.rowcount > 0

    def search(self, filters: SearchFilters) -> list[MemorySearchResult]:
        """Search memories using FTS5 and optional filters.

        When a query is provided, uses FTS5 BM25 ranking.
        Otherwise falls back to recency-ordered listing with filters.
        """
        conn = self._get_conn()

        if filters.query:
            return self._fts_search(conn, filters)
        return self._filtered_list(conn, filters)

    def _fts_search(
        self, conn: sqlite3.Connection, filters: SearchFilters
    ) -> list[MemorySearchResult]:
        """Full-text search with BM25 ranking."""
        assert filters.query is not None
        # Build the FTS query - escape special chars for safety
        fts_query = filters.query.replace('"', '""')

        where_clauses = []
        params: list[object] = []

        # Core FTS match
        base_sql = """
            SELECT m.*, rank
            FROM memories_fts fts
            JOIN memories m ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
        """
        params.append(f'"{fts_query}"')

        if filters.labels:
            placeholders = ",".join("?" for _ in filters.labels)
            # Check if any of the requested labels appear in the stored JSON array
            label_conditions = []
            for label in filters.labels:
                label_conditions.append("m.labels LIKE ?")
                params.append(f'%"{label}"%')
            where_clauses.append(f"({' OR '.join(label_conditions)})")

        if filters.content_type:
            where_clauses.append("m.content_type = ?")
            params.append(filters.content_type.value)

        if filters.session_id:
            where_clauses.append("m.session_id = ?")
            params.append(filters.session_id)

        if filters.source:
            where_clauses.append("m.source = ?")
            params.append(filters.source)

        if filters.after:
            where_clauses.append("m.created_at >= ?")
            params.append(filters.after)

        if filters.before:
            where_clauses.append("m.created_at <= ?")
            params.append(filters.before)

        if where_clauses:
            base_sql += " AND " + " AND ".join(where_clauses)

        base_sql += " ORDER BY rank LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])

        rows = conn.execute(base_sql, params).fetchall()
        results = []
        for row in rows:
            memory = self._row_to_memory(row)
            # Create a snippet from content
            content_preview = memory.content[:200]
            if len(memory.content) > 200:
                content_preview += "..."
            results.append(
                MemorySearchResult(
                    memory=memory,
                    rank=abs(row["rank"]),
                    snippet=content_preview,
                )
            )
        return results

    def _filtered_list(
        self, conn: sqlite3.Connection, filters: SearchFilters
    ) -> list[MemorySearchResult]:
        """List memories with optional filters, ordered by recency."""
        where_clauses = []
        params: list[object] = []

        if filters.labels:
            label_conditions = []
            for label in filters.labels:
                label_conditions.append("m.labels LIKE ?")
                params.append(f'%"{label}"%')
            where_clauses.append(f"({' OR '.join(label_conditions)})")

        if filters.content_type:
            where_clauses.append("m.content_type = ?")
            params.append(filters.content_type.value)

        if filters.session_id:
            where_clauses.append("m.session_id = ?")
            params.append(filters.session_id)

        if filters.source:
            where_clauses.append("m.source = ?")
            params.append(filters.source)

        if filters.after:
            where_clauses.append("m.created_at >= ?")
            params.append(filters.after)

        if filters.before:
            where_clauses.append("m.created_at <= ?")
            params.append(filters.before)

        sql = "SELECT m.* FROM memories m"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY m.created_at DESC LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])

        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            memory = self._row_to_memory(row)
            content_preview = memory.content[:200]
            if len(memory.content) > 200:
                content_preview += "..."
            results.append(
                MemorySearchResult(memory=memory, rank=0.0, snippet=content_preview)
            )
        return results

    def list_labels(self) -> list[LabelCount]:
        """List all unique labels with their usage counts."""
        conn = self._get_conn()
        rows = conn.execute("SELECT labels FROM memories").fetchall()
        label_counts: dict[str, int] = {}
        for row in rows:
            for label in json.loads(row["labels"]):
                label_counts[label] = label_counts.get(label, 0) + 1
        return sorted(
            [LabelCount(label=k, count=v) for k, v in label_counts.items()],
            key=lambda x: x.count,
            reverse=True,
        )

    def list_sessions(self) -> list[SessionInfo]:
        """List all sessions with summary info."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT session_id,
                      COUNT(*) as memory_count,
                      MIN(created_at) as first_memory,
                      MAX(created_at) as last_memory
               FROM memories
               GROUP BY session_id
               ORDER BY last_memory DESC"""
        ).fetchall()
        return [
            SessionInfo(
                session_id=row["session_id"],
                memory_count=row["memory_count"],
                first_memory=row["first_memory"],
                last_memory=row["last_memory"],
            )
            for row in rows
        ]

    def count(self) -> int:
        """Get total memory count."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        return row["cnt"]

    # ── Stats ─────────────────────────────────────────────────

    def stats(self) -> MemoryStats:
        """Get overall memory store statistics."""
        conn = self._get_conn()
        total = self.count()

        # By content_type
        rows = conn.execute(
            "SELECT content_type, COUNT(*) as cnt FROM memories GROUP BY content_type"
        ).fetchall()
        by_type = {row["content_type"]: row["cnt"] for row in rows}

        # By source
        rows = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM memories GROUP BY source"
        ).fetchall()
        by_source = {row["source"]: row["cnt"] for row in rows}

        # Label count
        label_count = len(self.list_labels())

        # Session count
        session_count = len(self.list_sessions())

        # Date range
        row = conn.execute(
            "SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM memories"
        ).fetchone()
        oldest = row["oldest"] if row else None
        newest = row["newest"] if row else None

        # DB size
        db_size = self._db_path.stat().st_size if self._db_path.exists() else 0

        return MemoryStats(
            total_memories=total,
            by_content_type=by_type,
            by_source=by_source,
            label_count=label_count,
            session_count=session_count,
            oldest_memory=oldest,
            newest_memory=newest,
            storage_path=str(self._storage_dir),
            db_size_bytes=db_size,
        )

    # ── Duplicate Detection ───────────────────────────────────

    def check_duplicate(self, title: str, content: str, threshold: int = 3) -> DuplicateCheck:
        """Check if a similar memory already exists using FTS5.

        Returns matches ranked by relevance. is_duplicate is True
        if any result's title closely matches.
        """
        # Search by title first
        filters = SearchFilters(query=title, limit=threshold)
        results = self.search(filters)

        is_dup = False
        for r in results:
            # Exact or near-exact title match
            if r.memory.title.lower().strip() == title.lower().strip():
                is_dup = True
                break

        return DuplicateCheck(is_duplicate=is_dup, similar=results)

    # ── Expiration ────────────────────────────────────────────

    def purge_expired(self) -> int:
        """Delete memories whose expires_at is in the past. Returns count deleted."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        conn.commit()
        return cursor.rowcount

    # ── Linking ───────────────────────────────────────────────

    def link(self, memory_id: str, related_id: str) -> Optional[Memory]:
        """Add a bidirectional link between two memories."""
        mem_a = self.get(memory_id)
        mem_b = self.get(related_id)
        if mem_a is None or mem_b is None:
            return None

        # Add link A -> B
        ids_a = list(mem_a.related_ids)
        if related_id not in ids_a:
            ids_a.append(related_id)
            self.update(memory_id, related_ids=ids_a)

        # Add link B -> A
        ids_b = list(mem_b.related_ids)
        if memory_id not in ids_b:
            ids_b.append(memory_id)
            self.update(related_id, related_ids=ids_b)

        return self.get(memory_id)

    # ── Export / Import ───────────────────────────────────────

    def export_memories(self, filters: Optional[SearchFilters] = None) -> list[dict]:
        """Export memories as a list of dicts (JSON-serializable)."""
        if filters:
            results = self.search(filters)
            memories = [r.memory for r in results]
        else:
            conn = self._get_conn()
            rows = conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()
            memories = [self._row_to_memory(row) for row in rows]

        return [m.model_dump() for m in memories]

    def import_memories(self, data: list[dict]) -> int:
        """Import memories from a list of dicts. Skips duplicates by ID."""
        conn = self._get_conn()
        imported = 0
        for entry in data:
            mem = Memory(**entry)
            existing = self.get(mem.id)
            if existing is not None:
                continue
            self.store(mem)
            imported += 1
        return imported

    # ── Wake-up Context ───────────────────────────────────────

    def wake_up(self, max_tokens: int = 500) -> str:
        """Generate a compact wake-up summary of critical memories.

        Returns a concise text suitable for loading into an LLM context
        at session start. Prioritizes recent, labeled memories.
        """
        conn = self._get_conn()

        # Get label summary
        labels = self.list_labels()
        label_summary = ", ".join(f"{lc.label}({lc.count})" for lc in labels[:10])

        # Get most recent memories (last 10)
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        recent = [self._row_to_memory(row) for row in rows]

        lines = ["# Memory Context"]
        if label_summary:
            lines.append(f"Topics: {label_summary}")
        lines.append(f"Total memories: {self.count()}")
        lines.append("")

        char_budget = max_tokens * 4  # rough chars-per-token
        used = sum(len(l) for l in lines)

        for mem in recent:
            label_str = ", ".join(mem.labels) if mem.labels else ""
            entry = f"- [{mem.content_type.value}] {mem.title}"
            if label_str:
                entry += f" ({label_str})"
            snippet = mem.content[:150].replace("\n", " ")
            if len(mem.content) > 150:
                snippet += "..."
            entry += f": {snippet}"

            if used + len(entry) > char_budget:
                break
            lines.append(entry)
            used += len(entry)

        return "\n".join(lines)

    # ── Knowledge Graph ───────────────────────────────────────

    def kg_add(self, triple: KnowledgeTriple) -> KnowledgeTriple:
        """Add a fact triple to the knowledge graph."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO knowledge_graph (id, subject, predicate, object, valid_from, valid_to, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                triple.id,
                triple.subject,
                triple.predicate,
                triple.object,
                triple.valid_from,
                triple.valid_to,
                triple.source,
                triple.created_at,
            ),
        )
        conn.commit()
        return triple

    def kg_query(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_val: Optional[str] = None,
        as_of: Optional[str] = None,
        active_only: bool = True,
    ) -> list[KnowledgeTriple]:
        """Query the knowledge graph with optional filters."""
        conn = self._get_conn()
        where = []
        params: list[object] = []

        if subject:
            where.append("subject = ?")
            params.append(subject)
        if predicate:
            where.append("predicate = ?")
            params.append(predicate)
        if object_val:
            where.append("object = ?")
            params.append(object_val)
        if as_of:
            # Point-in-time query: show triples that were active at as_of
            where.append("valid_from <= ?")
            params.append(as_of)
            where.append("(valid_to IS NULL OR valid_to > ?)")
            params.append(as_of)
        elif active_only:
            where.append("valid_to IS NULL")

        sql = "SELECT * FROM knowledge_graph"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY valid_from DESC"

        rows = conn.execute(sql, params).fetchall()
        return [
            KnowledgeTriple(
                id=row["id"],
                subject=row["subject"],
                predicate=row["predicate"],
                object=row["object"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                source=row["source"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def kg_invalidate(
        self, subject: str, predicate: str, object_val: str, ended: Optional[str] = None
    ) -> int:
        """Mark matching triples as ended. Returns count invalidated."""
        conn = self._get_conn()
        ended = ended or datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """UPDATE knowledge_graph SET valid_to = ?
               WHERE subject = ? AND predicate = ? AND object = ? AND valid_to IS NULL""",
            (ended, subject, predicate, object_val),
        )
        conn.commit()
        return cursor.rowcount

    def kg_timeline(self, entity: str) -> list[KnowledgeTriple]:
        """Get the chronological timeline for an entity (as subject or object)."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM knowledge_graph
               WHERE subject = ? OR object = ?
               ORDER BY valid_from ASC""",
            (entity, entity),
        ).fetchall()
        return [
            KnowledgeTriple(
                id=row["id"],
                subject=row["subject"],
                predicate=row["predicate"],
                object=row["object"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                source=row["source"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def kg_stats(self) -> KGStats:
        """Get knowledge graph statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_graph").fetchone()["cnt"]
        active = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_graph WHERE valid_to IS NULL"
        ).fetchone()["cnt"]
        subjects = conn.execute(
            "SELECT COUNT(DISTINCT subject) as cnt FROM knowledge_graph"
        ).fetchone()["cnt"]
        predicates = conn.execute(
            "SELECT COUNT(DISTINCT predicate) as cnt FROM knowledge_graph"
        ).fetchone()["cnt"]
        objects = conn.execute(
            "SELECT COUNT(DISTINCT object) as cnt FROM knowledge_graph"
        ).fetchone()["cnt"]

        return KGStats(
            total_triples=total,
            active_triples=active,
            unique_subjects=subjects,
            unique_predicates=predicates,
            unique_objects=objects,
        )
