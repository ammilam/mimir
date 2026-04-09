# mimir - Local LLM Memory Store

## Overview
A local MCP (Model Context Protocol) server that acts as a persistent memory and knowledge graph store for LLMs. Any AI coding tool (VS Code Copilot, Claude Code, Cursor, etc.) can connect via stdio transport to store, search, and reason over contextual memories across sessions.

## Architecture

### Why This is Better Than the Official MCP Memory Server
| Feature | Official Memory Server | mimir |
|---------|----------------------|------------|
| Storage | Knowledge graph (JSONL) | SQLite + FTS5 full-text search |
| Search | Simple string matching | BM25 ranking via FTS5 + label filtering + date ranges |
| Organization | Entities/relations only | Labels, content types, sessions, expiration |
| Content types | Observations (strings) | Text, code snippets, structured data |
| Timestamps | None | Auto-timestamped, searchable by date |
| Sessions | None | Session tracking for context grouping |
| Knowledge Graph | Basic | Temporal triples with validity, invalidation, point-in-time queries |
| Duplicate Detection | None | FTS-based similarity check before storing |
| Session Bootstrap | None | Wake-up context digest for new sessions |
| Language | TypeScript | Python (FastMCP) |
| Dependencies | Node.js + npm | Python + pip (sqlite3 is stdlib) |

### Tech Stack
- **Language**: Python 3.11+
- **MCP SDK**: `mcp[cli]` (FastMCP)
- **Storage**: SQLite with FTS5 extension (built into Python stdlib), WAL mode
- **Transport**: stdio (for local MCP integration)
- **Build**: hatchling
- **Package manager**: uv

### Storage Modes
| Mode | Path | Use case |
|------|------|----------|
| `global` (default) | `~/.mimir/memories/<workspace>/` | Shared across tools, per-workspace subdirs |
| `workspace` | `<cwd>/.mimir/memories/` | Project-local, lives with the repo |

Set via `--location=global` or `--location=workspace` CLI arg to the server.

### Data Model
Each memory entry:
- `id` (UUID) - unique identifier
- `title` (str) - short descriptive title
- `content` (str) - the body of the memory (text, code, notes)
- `content_type` (enum) - text | code | snippet | conversation | note
- `labels` (list[str]) - tags for categorization
- `source` (str) - which tool created it (vscode, claude-code, etc.)
- `session_id` (str) - groups memories within a session
- `related_ids` (list[str]) - cross-references to other memory IDs
- `expires_at` (datetime, optional) - auto-purge after this time
- `created_at` (datetime) - auto-populated
- `updated_at` (datetime) - auto-populated

Knowledge graph triples:
- `id` (UUID) - unique identifier
- `subject` (str) - the entity
- `predicate` (str) - the relationship
- `object` (str) - the target
- `valid_from` (datetime) - when the fact became true
- `valid_to` (datetime, optional) - when the fact stopped being true (null = still active)
- `source` (str) - which tool created it

### MCP Tools Exposed (20 tools)

**Core Memory (6):**
1. `mem_store` - Store a new memory
2. `mem_search` - Full-text search with BM25 ranking + label/type/date filters
3. `mem_get` - Get a specific memory by ID
4. `mem_update` - Update an existing memory
5. `mem_delete` - Delete a memory
6. `mem_batch_store` - Store multiple memories in one transaction

**Discovery & Context (5):**
7. `mem_wake_up` - Session-start context summary
8. `mem_list_labels` - List all labels with counts
9. `mem_list_sessions` - List all sessions with time ranges
10. `mem_stats` - Memory store overview (totals, breakdowns, size)
11. `mem_check_duplicate` - Check for similar memories before storing

**Organization (4):**
12. `mem_link` - Bidirectional link between related memories
13. `mem_purge_expired` - Delete memories past their expires_at
14. `mem_export` - Export memories as JSON
15. `mem_import` - Import memories from JSON (idempotent)

**Knowledge Graph (5):**
16. `mem_kg_add` - Add a subject→predicate→object fact
17. `mem_kg_query` - Query facts by subject/predicate/object, point-in-time
18. `mem_kg_invalidate` - Mark a fact as no longer true
19. `mem_kg_timeline` - Chronological history of facts about an entity
20. `mem_kg_stats` - Knowledge graph statistics

### Directory Structure
```
mimir/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── .gitignore
├── hooks/
│   ├── mimir_save_hook.sh         # Claude Code auto-save hook
│   └── mimir_precompact_hook.sh   # Claude Code pre-compact hook
├── src/
│   └── mimir/
│       ├── __init__.py
│       ├── server.py        # MCP server (FastMCP) with context-aware tool descriptors
│       ├── models.py        # Pydantic data models (Memory, KnowledgeTriple, etc.)
│       └── store.py         # SQLite storage engine + knowledge graph + migrations
└── tests/
    └── test_store.py        # 54 tests (8 test classes)
```

### VS Code Integration
Global config at `%APPDATA%\Code\User\mcp.json` or per-workspace `.vscode/mcp.json`:
```json
{
  "servers": {
    "mimir": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mimir", "mimir"]
    }
  }
}
```

### Claude Code Integration
```bash
claude mcp add mimir -- uv run --directory /path/to/mimir mimir
```

## Status
- [x] Research and design
- [x] Project setup (pyproject.toml, hatchling, venv)
- [x] Core implementation (models, store, server) — 8 original tools
- [x] Tests (24/24 passing) — original suite
- [x] End-to-end MCP stdio validation
- [x] Storage location refactor (global/workspace modes)
- [x] Feature expansion: knowledge graph, duplicate detection, expiration, wake-up context, stats, linking, export/import (12 new tools)
- [x] Tests expanded to 54 (30 new across 8 test classes)
- [x] Context-aware tool descriptors (MCP best practices: "Use when" / "Don't use when" docstrings)
- [x] Comprehensive server instructions telling LLMs when to proactively use memory

## Bug Fixes

### 2026-04-08: kg_query as_of logic
- **Bug**: When `as_of` was provided, `active_only=True` default added `valid_to IS NULL` which excluded invalidated triples — even for point-in-time queries.
- **Fix**: `as_of` now overrides `active_only`. When `as_of` is provided, the query uses temporal bounds (`valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`) instead of the `valid_to IS NULL` filter.

### 2026-04-08: MCP server path mismatch
- **Bug**: Global MCP config at `%APPDATA%\Code\User\mcp.json` referenced old directory `C:\Users\Andrew\Documents\llmemstore` instead of `C:\Users\Andrew\Documents\mimir`.
- **Fix**: Updated the path in the global MCP config.

## Recurring Issues / Patterns

### Use `uv` not `pip` for package operations
- `pip install -e .` silently does nothing in this project. Always use `uv pip install -e .` or `uv sync`.

### VS Code MCP config location
- Global MCP config lives at `%APPDATA%\Code\User\mcp.json` (not in VS Code user settings.json and not in `.vscode/mcp.json` per workspace unless explicitly created).
- [x] Pylance type errors fixed (ToolAnnotations, Optional narrowing)

## Bugs / Fixes
- **2026-04-07**: Fixed Pylance `reportArgumentType` errors — `@mcp.tool(annotations=...)` required `ToolAnnotations(...)` objects, not plain dicts. Fixed all 8 tool decorators.
- **2026-04-07**: Fixed Pylance `reportOptionalMemberAccess` on `filters.query.replace()` — added `assert filters.query is not None` guard in `_fts_search()` (only called when query is truthy).
- **2026-04-07**: Removed unnecessary `MIMIR_DIR` env var. Simplified to `resolve_storage_dir()` with global/workspace modes.

## Recurring Issues / Patterns
- **ToolAnnotations must be typed**: FastMCP's `@mcp.tool(annotations=...)` requires `ToolAnnotations(...)` from `mcp.types`, not a plain dict. Pylance catches this.
- **Optional narrowing**: When a method is only called after a truthy check on an Optional field, add an `assert` at the call site to satisfy type checkers.
- **MCP client config must use `uv`, not venv paths**: Stdio MCP servers are spawned by the client. Use `"command": "uv", "args": ["run", "--directory", "<project>", "<entrypoint>"]` — never reference `.venv/Scripts/python.exe` or any venv internals. The whole point of `uv run --directory` is it handles the environment transparently.
- **No hardcoded user paths in docs**: README and config examples must use generic placeholders like `/path/to/mimir`, never absolute user-specific paths.