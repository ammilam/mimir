# mimir - Local LLM Memory Store

## Overview
A local MCP (Model Context Protocol) server that acts as a persistent memory and RAG store for LLMs. Any AI coding tool (VS Code Copilot, Claude Code, Cursor, etc.) can connect via stdio transport to store and retrieve contextual memories throughout sessions.

## Architecture

### Why This is Better Than the Official MCP Memory Server
| Feature | Official Memory Server | mimir |
|---------|----------------------|------------|
| Storage | Knowledge graph (JSONL) | SQLite + FTS5 full-text search |
| Search | Simple string matching | BM25 ranking via FTS5 + label filtering + date ranges |
| Organization | Entities/relations only | Labels, content types, sessions |
| Content types | Observations (strings) | Text, code snippets, structured data |
| Timestamps | None | Auto-timestamped, searchable by date |
| Sessions | None | Session tracking for context grouping |
| Language | TypeScript | Python (FastMCP) |
| Dependencies | Node.js + npm | Python + pip (sqlite3 is stdlib) |

### Tech Stack
- **Language**: Python 3.11+
- **MCP SDK**: `mcp[cli]` (FastMCP)
- **Storage**: SQLite with FTS5 extension (built into Python stdlib)
- **Transport**: stdio (for local MCP integration)
- **Build**: hatchling
- **Virtual env**: venv + pip

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
- `created_at` (datetime) - auto-populated
- `updated_at` (datetime) - auto-populated

### MCP Tools Exposed (8 tools)
1. `mem_store` - Store a new memory
2. `mem_search` - Full-text search with optional label/type/date filters (also serves as list)
3. `mem_get` - Get a specific memory by ID
4. `mem_update` - Update an existing memory
5. `mem_delete` - Delete a memory
6. `mem_list_labels` - List all unique labels with counts
7. `mem_list_sessions` - List all sessions
8. `mem_batch_store` - Store multiple memories at once

### Directory Structure
```
llmemstore/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── src/
│   └── mimir/
│       ├── __init__.py
│       ├── server.py        # MCP server (FastMCP) with --location arg
│       ├── models.py        # Pydantic data models
│       └── store.py         # SQLite storage engine + resolve_storage_dir()
└── tests/
    └── test_store.py        # 24 passing tests
```

### VS Code Integration
Add to `.vscode/mcp.json`:
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
- [x] Core implementation (models, store, server)
- [x] Tests (24/24 passing)
- [x] End-to-end MCP stdio validation
- [x] Storage location refactor (global/workspace modes)
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