# Mimir

Persistent memory for LLMs via MCP. SQLite + FTS5 full-text search, stdio transport.

Your MCP client launches the server automatically — you never run it manually.

## Quick Start

### 1. Install

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # install uv
git clone <repo-url> mimir && cd mimir
uv sync
```

### 2. Register the MCP Server

Add to your client's MCP config. Replace `/path/to/mimir` with wherever you cloned it.

**VS Code** — `.vscode/mcp.json` or your global MCP config:
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

**Claude Code:**
```bash
claude mcp add mimir -- uv run --directory /path/to/mimir mimir
```

**Cursor** — `Cursor Settings > MCP`:
```json
{
  "mcpServers": {
    "mimir": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mimir", "mimir"]
    }
  }
}
```

### 3. Add Agent Instructions (Required)

Registering the server only makes the tools *available*. The LLM won't use them unless you tell it to. Paste the following into your agent's instruction file:

```markdown
## Memory (Mimir MCP)

You have access to persistent memory via the Mimir MCP tools (prefixed `mem_`).
Use these tools proactively — do NOT wait for the user to ask.

### Session Start
- Call `mem_wake_up` at the start of every conversation to load prior context.

### When to Store (`mem_store`)
- User states a preference, convention, or decision
- You discover a codebase pattern, architecture detail, or build command
- A bug is diagnosed and fixed — store the root cause and solution
- A conversation produces an important outcome or action item
- The user corrects you — store the correction so you don't repeat the mistake

### When to Search (`mem_search`)
- Before answering questions about the project or user preferences
- Before making architectural or design decisions
- When the user references something from a past conversation

### Labels
- Use lowercase, hyphenated labels (e.g. `bug-fix`, `preference`, `codebase`, `decision`)
- Check `mem_list_labels` before creating new labels to stay consistent
- Before storing, call `mem_check_duplicate` if the memory might already exist

### Knowledge Graph
- `mem_kg_add` — record relationships (who works on what, service dependencies)
- `mem_kg_query` — answer "what is X?" or "who owns Y?"
- `mem_kg_invalidate` — mark a fact as no longer true
```

Where to put it depends on your client:

| Client | File | Scope |
|--------|------|-------|
| VS Code / Copilot | `.github/copilot-instructions.md` | per repo |
| Claude Code | `CLAUDE.md` | per repo |
| Claude Code | `~/.claude/CLAUDE.md` | global |
| Cursor | `.cursor/rules/mimir.mdc` | per repo |
| Cursor | `~/.cursor/rules/mimir.mdc` | global |

See each client's docs for additional global instruction options.

## Storage

| Mode | Flag | Path |
|------|------|------|
| global *(default)* | — | `~/.mimir/memories/<workspace>/` |
| workspace | `--location=workspace` | `.mimir/memories/` |

To use workspace mode, append `"--location=workspace"` to the args array in your MCP config.

## Tools

| Tool | Description |
|------|-------------|
| **Core** | |
| `mem_store` | Store a memory |
| `mem_get` | Retrieve by ID |
| `mem_update` | Update fields |
| `mem_delete` | Delete a memory |
| `mem_batch_store` | Store multiple in one transaction |
| `mem_search` | Full-text search with BM25, label/type/date filters |
| **Context** | |
| `mem_wake_up` | Compact context summary — call at session start |
| `mem_check_duplicate` | Check for similar memories before storing |
| `mem_list_labels` | All labels with counts |
| `mem_list_sessions` | All sessions with time ranges |
| `mem_stats` | Totals, breakdowns, storage size |
| **Organization** | |
| `mem_link` | Bidirectional link between memories |
| `mem_purge_expired` | Delete expired memories |
| `mem_export` | Export as JSON |
| `mem_import` | Import from JSON (idempotent) |
| **Knowledge Graph** | |
| `mem_kg_add` | Add a subject→predicate→object fact |
| `mem_kg_query` | Query facts, with point-in-time support |
| `mem_kg_invalidate` | Mark a fact as no longer true |
| `mem_kg_timeline` | History of all facts about an entity |
| `mem_kg_stats` | Triple/entity/predicate counts |

## Development

```bash
uv run pytest
```
