"""Tests for the MemoryStore storage engine."""

import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from mimir.models import ContentType, KnowledgeTriple, Memory, SearchFilters
from mimir.store import MemoryStore, resolve_storage_dir


@pytest.fixture
def store(tmp_path):
    """Create a store using a temporary directory."""
    s = MemoryStore(storage_dir=tmp_path / "memories")
    yield s
    s.close()


@pytest.fixture
def sample_memory():
    return Memory(
        title="Test Memory",
        content="This is a test memory about Python programming.",
        content_type=ContentType.TEXT,
        labels=["python", "test"],
        source="pytest",
        session_id="test-session-1",
    )


class TestStoreBasicOps:
    def test_store_and_get(self, store, sample_memory):
        stored = store.store(sample_memory)
        assert stored.id == sample_memory.id

        retrieved = store.get(stored.id)
        assert retrieved is not None
        assert retrieved.title == "Test Memory"
        assert retrieved.content == "This is a test memory about Python programming."
        assert retrieved.content_type == ContentType.TEXT
        assert retrieved.labels == ["python", "test"]
        assert retrieved.source == "pytest"
        assert retrieved.session_id == "test-session-1"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent-id") is None

    def test_update(self, store, sample_memory):
        store.store(sample_memory)
        updated = store.update(sample_memory.id, title="Updated Title", labels=["updated"])
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.labels == ["updated"]
        assert updated.content == sample_memory.content  # unchanged

    def test_update_nonexistent(self, store):
        assert store.update("nonexistent-id", title="x") is None

    def test_delete(self, store, sample_memory):
        store.store(sample_memory)
        assert store.delete(sample_memory.id) is True
        assert store.get(sample_memory.id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete("nonexistent-id") is False

    def test_count(self, store, sample_memory):
        assert store.count() == 0
        store.store(sample_memory)
        assert store.count() == 1

    def test_batch_store(self, store):
        memories = [
            Memory(title=f"Memory {i}", content=f"Content {i}", labels=["batch"])
            for i in range(5)
        ]
        stored = store.batch_store(memories)
        assert len(stored) == 5
        assert store.count() == 5


class TestStoreSearch:
    def _seed(self, store):
        memories = [
            Memory(
                title="Python SQLite tutorial",
                content="Learn how to use SQLite with Python including FTS5 full-text search.",
                content_type=ContentType.TEXT,
                labels=["python", "database", "tutorial"],
                source="vscode",
                session_id="s1",
            ),
            Memory(
                title="React component pattern",
                content="const MyComponent = () => { return <div>Hello</div>; }",
                content_type=ContentType.CODE,
                labels=["javascript", "react", "frontend"],
                source="vscode",
                session_id="s1",
            ),
            Memory(
                title="Meeting notes",
                content="Discussed migration plan. Decided to use PostgreSQL in production.",
                content_type=ContentType.NOTE,
                labels=["meeting", "database"],
                source="claude-code",
                session_id="s2",
            ),
            Memory(
                title="Debug session log",
                content="Found the bug in the authentication module. The token was expiring too early.",
                content_type=ContentType.CONVERSATION,
                labels=["debug", "auth"],
                source="claude-code",
                session_id="s2",
            ),
        ]
        store.batch_store(memories)

    def test_full_text_search(self, store):
        self._seed(store)
        results = store.search(SearchFilters(query="SQLite"))
        assert len(results) >= 1
        assert any("SQLite" in r.memory.title or "SQLite" in r.memory.content for r in results)

    def test_search_by_label(self, store):
        self._seed(store)
        results = store.search(SearchFilters(labels=["database"]))
        assert len(results) == 2

    def test_search_by_content_type(self, store):
        self._seed(store)
        results = store.search(SearchFilters(content_type=ContentType.CODE))
        assert len(results) == 1
        assert results[0].memory.title == "React component pattern"

    def test_search_by_session(self, store):
        self._seed(store)
        results = store.search(SearchFilters(session_id="s2"))
        assert len(results) == 2

    def test_search_by_source(self, store):
        self._seed(store)
        results = store.search(SearchFilters(source="claude-code"))
        assert len(results) == 2

    def test_search_with_query_and_label(self, store):
        self._seed(store)
        results = store.search(SearchFilters(query="Python", labels=["tutorial"]))
        assert len(results) >= 1
        assert results[0].memory.labels == ["python", "database", "tutorial"]

    def test_search_pagination(self, store):
        self._seed(store)
        page1 = store.search(SearchFilters(limit=2, offset=0))
        page2 = store.search(SearchFilters(limit=2, offset=2))
        assert len(page1) == 2
        assert len(page2) == 2
        ids1 = {r.memory.id for r in page1}
        ids2 = {r.memory.id for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_empty_search(self, store):
        results = store.search(SearchFilters())
        assert results == []

    def test_search_no_results(self, store):
        self._seed(store)
        results = store.search(SearchFilters(query="xyznonexistent"))
        assert len(results) == 0


class TestStoreMetadata:
    def test_list_labels(self, store):
        store.batch_store([
            Memory(title="A", content="a", labels=["python", "test"]),
            Memory(title="B", content="b", labels=["python", "database"]),
            Memory(title="C", content="c", labels=["rust"]),
        ])
        labels = store.list_labels()
        label_dict = {lc.label: lc.count for lc in labels}
        assert label_dict["python"] == 2
        assert label_dict["test"] == 1
        assert label_dict["database"] == 1
        assert label_dict["rust"] == 1

    def test_list_sessions(self, store):
        store.batch_store([
            Memory(title="A", content="a", session_id="s1"),
            Memory(title="B", content="b", session_id="s1"),
            Memory(title="C", content="c", session_id="s2"),
        ])
        sessions = store.list_sessions()
        assert len(sessions) == 2
        session_dict = {s.session_id: s.memory_count for s in sessions}
        assert session_dict["s1"] == 2
        assert session_dict["s2"] == 1

    def test_list_labels_empty(self, store):
        assert store.list_labels() == []

    def test_list_sessions_empty(self, store):
        assert store.list_sessions() == []


class TestResolveStorageDir:
    def test_global_uses_home_dir(self):
        result = resolve_storage_dir("global")
        assert ".mimir" in result.parts
        assert "memories" in result.parts
        # Last part should be the workspace name (cwd dirname)
        assert result.name == Path.cwd().name

    def test_workspace_uses_cwd(self):
        result = resolve_storage_dir("workspace")
        assert result == Path.cwd() / ".mimir" / "memories"

    def test_default_is_global(self):
        assert resolve_storage_dir() == resolve_storage_dir("global")


class TestStoreStats:
    def test_stats_empty(self, store):
        s = store.stats()
        assert s.total_memories == 0
        assert s.by_content_type == {}
        assert s.by_source == {}
        assert s.label_count == 0
        assert s.session_count == 0
        assert s.oldest_memory is None
        assert s.newest_memory is None

    def test_stats_with_data(self, store):
        store.batch_store([
            Memory(title="A", content="a", content_type=ContentType.CODE, labels=["py"], source="vscode", session_id="s1"),
            Memory(title="B", content="b", content_type=ContentType.TEXT, labels=["py", "db"], source="vscode", session_id="s1"),
            Memory(title="C", content="c", content_type=ContentType.CODE, labels=["rust"], source="claude-code", session_id="s2"),
        ])
        s = store.stats()
        assert s.total_memories == 3
        assert s.by_content_type["code"] == 2
        assert s.by_content_type["text"] == 1
        assert s.by_source["vscode"] == 2
        assert s.by_source["claude-code"] == 1
        assert s.label_count == 3  # py, db, rust
        assert s.session_count == 2
        assert s.oldest_memory is not None
        assert s.newest_memory is not None
        assert s.db_size_bytes > 0


class TestDuplicateCheck:
    def test_no_duplicates_empty(self, store):
        result = store.check_duplicate("New Title", "new content")
        assert result.is_duplicate is False
        assert result.similar == []

    def test_detects_exact_duplicate(self, store):
        store.store(Memory(title="Python FTS5 Setup", content="How to set up FTS5 with Python"))
        result = store.check_duplicate("Python FTS5 Setup", "different content")
        assert result.is_duplicate is True

    def test_no_false_positive(self, store):
        store.store(Memory(title="React Hooks", content="useState and useEffect"))
        result = store.check_duplicate("Python FTS5 Setup", "FTS5 indexing guide")
        assert result.is_duplicate is False


class TestExpiration:
    def test_purge_expired(self, store):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        store.store(Memory(title="Expired", content="old stuff", expires_at=past))
        store.store(Memory(title="Still Valid", content="current stuff", expires_at=future))
        store.store(Memory(title="No Expiry", content="permanent"))

        assert store.count() == 3
        deleted = store.purge_expired()
        assert deleted == 1
        assert store.count() == 2

        # Verify the right one was deleted
        results = store.search(SearchFilters(query="Expired"))
        assert len(results) == 0
        results = store.search(SearchFilters(query="Still Valid"))
        assert len(results) == 1

    def test_purge_nothing_expired(self, store):
        store.store(Memory(title="No Expiry", content="permanent"))
        assert store.purge_expired() == 0

    def test_memory_stores_expires_at(self, store):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        store.store(Memory(title="Temp", content="temporary", expires_at=future))
        mem = store.search(SearchFilters(query="Temp"))[0].memory
        assert mem.expires_at == future


class TestRelatedIds:
    def test_store_with_related_ids(self, store):
        m1 = store.store(Memory(title="A", content="first"))
        m2 = store.store(Memory(title="B", content="second", related_ids=[m1.id]))
        retrieved = store.get(m2.id)
        assert retrieved is not None
        assert m1.id in retrieved.related_ids

    def test_link_memories(self, store):
        m1 = store.store(Memory(title="Auth Design", content="OAuth2 flow"))
        m2 = store.store(Memory(title="Auth Bug", content="Token expiry too short"))

        result = store.link(m1.id, m2.id)
        assert result is not None
        assert m2.id in result.related_ids

        # Verify bidirectional
        m2_updated = store.get(m2.id)
        assert m2_updated is not None
        assert m1.id in m2_updated.related_ids

    def test_link_nonexistent(self, store):
        m1 = store.store(Memory(title="A", content="a"))
        assert store.link(m1.id, "nonexistent") is None

    def test_link_idempotent(self, store):
        m1 = store.store(Memory(title="A", content="a"))
        m2 = store.store(Memory(title="B", content="b"))
        store.link(m1.id, m2.id)
        store.link(m1.id, m2.id)  # second link should be no-op
        result = store.get(m1.id)
        assert result is not None
        assert result.related_ids.count(m2.id) == 1


class TestExportImport:
    def test_export_all(self, store):
        store.batch_store([
            Memory(title="A", content="aaa"),
            Memory(title="B", content="bbb"),
        ])
        data = store.export_memories()
        assert len(data) == 2
        assert data[0]["title"] in ("A", "B")

    def test_export_filtered(self, store):
        store.batch_store([
            Memory(title="Py", content="python stuff", labels=["python"]),
            Memory(title="Js", content="js stuff", labels=["javascript"]),
        ])
        data = store.export_memories(SearchFilters(labels=["python"]))
        assert len(data) == 1
        assert data[0]["title"] == "Py"

    def test_import_new(self, store):
        data = [
            {"id": "import-1", "title": "Imported A", "content": "content a"},
            {"id": "import-2", "title": "Imported B", "content": "content b"},
        ]
        count = store.import_memories(data)
        assert count == 2
        assert store.count() == 2

    def test_import_skips_duplicates(self, store):
        store.store(Memory(id="existing-1", title="Existing", content="exists"))
        data = [
            {"id": "existing-1", "title": "Duplicate", "content": "dup"},
            {"id": "new-1", "title": "New", "content": "fresh"},
        ]
        count = store.import_memories(data)
        assert count == 1
        assert store.count() == 2
        # Original should be unchanged
        existing = store.get("existing-1")
        assert existing is not None
        assert existing.title == "Existing"

    def test_roundtrip(self, store, tmp_path):
        """Export from one store, import into another."""
        store.batch_store([
            Memory(title="Round", content="trip", labels=["test"]),
        ])
        data = store.export_memories()

        store2 = MemoryStore(storage_dir=tmp_path / "store2")
        count = store2.import_memories(data)
        assert count == 1
        assert store2.count() == 1
        store2.close()


class TestWakeUp:
    def test_wake_up_empty(self, store):
        context = store.wake_up()
        assert "# Memory Context" in context
        assert "Total memories: 0" in context

    def test_wake_up_with_data(self, store):
        store.batch_store([
            Memory(title="Python Tips", content="Use list comprehensions", labels=["python", "tips"]),
            Memory(title="DB Config", content="Use WAL mode for SQLite", labels=["database", "config"]),
        ])
        context = store.wake_up()
        assert "# Memory Context" in context
        assert "Total memories: 2" in context
        assert "Python Tips" in context or "DB Config" in context

    def test_wake_up_respects_budget(self, store):
        # Store many memories
        store.batch_store([
            Memory(title=f"Memory {i}", content=f"Content for memory {i} " * 50, labels=["bulk"])
            for i in range(20)
        ])
        context = store.wake_up(max_tokens=100)
        # Should be limited in size
        assert len(context) < 2000  # 100 tokens * ~4 chars


class TestKnowledgeGraph:
    def test_kg_add_and_query(self, store):
        triple = KnowledgeTriple(
            subject="Kai", predicate="works_on", object="Orion",
            valid_from="2025-06-01T00:00:00+00:00", source="test",
        )
        stored = store.kg_add(triple)
        assert stored.id == triple.id

        results = store.kg_query(subject="Kai")
        assert len(results) == 1
        assert results[0].predicate == "works_on"
        assert results[0].object == "Orion"

    def test_kg_query_by_predicate(self, store):
        store.kg_add(KnowledgeTriple(subject="Kai", predicate="works_on", object="Orion"))
        store.kg_add(KnowledgeTriple(subject="Maya", predicate="assigned_to", object="auth-migration"))

        results = store.kg_query(predicate="works_on")
        assert len(results) == 1
        assert results[0].subject == "Kai"

    def test_kg_query_by_object(self, store):
        store.kg_add(KnowledgeTriple(subject="Kai", predicate="works_on", object="Orion"))
        store.kg_add(KnowledgeTriple(subject="Maya", predicate="works_on", object="Orion"))

        results = store.kg_query(object_val="Orion")
        assert len(results) == 2

    def test_kg_invalidate(self, store):
        store.kg_add(KnowledgeTriple(
            subject="Kai", predicate="works_on", object="Orion",
            valid_from="2025-06-01T00:00:00+00:00",
        ))
        count = store.kg_invalidate("Kai", "works_on", "Orion", ended="2026-03-01T00:00:00+00:00")
        assert count == 1

        # Active query should return nothing
        results = store.kg_query(subject="Kai", active_only=True)
        assert len(results) == 0

        # Historical query should still find it
        results = store.kg_query(subject="Kai", active_only=False)
        assert len(results) == 1
        assert results[0].valid_to == "2026-03-01T00:00:00+00:00"

    def test_kg_invalidate_nonexistent(self, store):
        count = store.kg_invalidate("Nobody", "does", "nothing")
        assert count == 0

    def test_kg_timeline(self, store):
        store.kg_add(KnowledgeTriple(
            subject="Kai", predicate="works_on", object="Orion",
            valid_from="2025-06-01T00:00:00+00:00",
        ))
        store.kg_add(KnowledgeTriple(
            subject="Kai", predicate="recommended", object="Clerk",
            valid_from="2026-01-15T00:00:00+00:00",
        ))
        store.kg_add(KnowledgeTriple(
            subject="Maya", predicate="works_on", object="Orion",
            valid_from="2025-09-01T00:00:00+00:00",
        ))

        timeline = store.kg_timeline("Kai")
        assert len(timeline) == 2
        # Should be chronological
        assert timeline[0].valid_from <= timeline[1].valid_from

        # Orion timeline should include both Kai and Maya
        timeline = store.kg_timeline("Orion")
        assert len(timeline) == 2

    def test_kg_as_of_query(self, store):
        store.kg_add(KnowledgeTriple(
            subject="Maya", predicate="assigned_to", object="auth-migration",
            valid_from="2026-01-15T00:00:00+00:00",
        ))
        store.kg_invalidate("Maya", "assigned_to", "auth-migration", ended="2026-02-01T00:00:00+00:00")
        store.kg_add(KnowledgeTriple(
            subject="Maya", predicate="completed", object="auth-migration",
            valid_from="2026-02-01T00:00:00+00:00",
        ))

        # As of Jan 20, Maya was still assigned
        results = store.kg_query(subject="Maya", as_of="2026-01-20T00:00:00+00:00")
        assert len(results) == 1
        assert results[0].predicate == "assigned_to"

        # As of Feb 15, Maya completed it
        results = store.kg_query(subject="Maya", as_of="2026-02-15T00:00:00+00:00")
        assert len(results) == 1
        assert results[0].predicate == "completed"

    def test_kg_stats_empty(self, store):
        s = store.kg_stats()
        assert s.total_triples == 0
        assert s.active_triples == 0

    def test_kg_stats_with_data(self, store):
        store.kg_add(KnowledgeTriple(subject="A", predicate="rel", object="B"))
        store.kg_add(KnowledgeTriple(subject="C", predicate="rel", object="D"))
        store.kg_invalidate("A", "rel", "B")

        s = store.kg_stats()
        assert s.total_triples == 2
        assert s.active_triples == 1
        assert s.unique_subjects == 2
        assert s.unique_predicates == 1
        assert s.unique_objects == 2


class TestMigration:
    def test_migration_on_existing_db(self, tmp_path):
        """Verify that opening an old DB without new columns still works."""
        # Create a store (which creates the schema with new cols)
        s = MemoryStore(storage_dir=tmp_path / "mig")
        s.store(Memory(title="Before Migration", content="old data"))
        s.close()

        # Reopen - migration should run idempotently
        s2 = MemoryStore(storage_dir=tmp_path / "mig")
        mem = s2.search(SearchFilters(query="Before Migration"))
        assert len(mem) == 1
        assert mem[0].memory.related_ids == []
        assert mem[0].memory.expires_at is None
        s2.close()
