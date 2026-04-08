# Mimir

Local MCP server for persistent LLM memory. SQLite + FTS5 full-text search, stdio transport.

MCP clients (VS Code, Claude Code, Cursor, etc.) launch the server automatically — you never run it manually.

## Install

```bash
# Install uv (if you don't have it)
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and sync
git clone <repo-url> mimir
cd mimir
uv sync
```

## Client Configuration

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json` in any workspace where you want memory available:

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

With workspace-local storage:

```json
{
  "servers": {
    "mimir": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mimir", "mimir", "--location=workspace"]
    }
  }
}
```

Replace `/path/to/mimir` with the absolute path to where you cloned this repo.

### Claude Code

```bash
claude mcp add mimir -- uv run --directory /path/to/mimir mimir
```

### Cursor

Add to MCP settings (`Cursor Settings > MCP`):

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

## Storage Modes

| Mode | Path | Use Case |
|------|------|----------|
| `global` (default) | `~/.mimir/memories/<workspace>/` | Shared across sessions, per-workspace isolation |
| `workspace` | `<cwd>/.mimir/memories/` | Project-specific, lives with the repo |

Pass `--location=workspace` to switch modes (see config examples above).

## Tools

| Tool | Description |
|------|-------------|
| `mem_store` | Store a new memory |
| `mem_search` | Full-text search with label, type, and date filters |
| `mem_get` | Get a memory by ID |
| `mem_update` | Update an existing memory |
| `mem_delete` | Delete a memory |
| `mem_list_labels` | List all labels with counts |
| `mem_list_sessions` | List all sessions |
| `mem_batch_store` | Store multiple memories at once |

## Development

```bash
uv run pytest
```
