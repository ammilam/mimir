---
description: Instructions for using the Mimir MCP memory tools in this workspace
---

## Memory (Mimir MCP)

You have access to persistent memory via the Mimir MCP tools (prefixed `mcp_mimir_`).
Use these tools proactively — do NOT wait for the user to ask.

### Session Start
- Call `mem_wake_up` at the start of every conversation to load prior context.

### When to Store (call `mem_store`)
- User states a preference, convention, or decision
- You discover a codebase pattern, architecture detail, or build command
- A bug is diagnosed and fixed — store the root cause and solution
- A conversation produces an important outcome or action item
- The user corrects you — store the correction so you don't repeat the mistake

### When to Search (call `mem_search`)
- Before answering questions about the project or user preferences
- Before making architectural or design decisions
- When the user references something from a past conversation

### Labels
- Use lowercase, hyphenated labels (e.g. `bug-fix`, `preference`, `codebase`, `decision`)
- Check `mem_list_labels` before creating new labels to stay consistent
- Before storing, call `mem_check_duplicate` if the memory might already exist

### Knowledge Graph (for structured facts)
- Use `mem_kg_add` to record relationships: who works on what, which service depends on which
- Use `mem_kg_query` to answer "what is X?" or "who works on Y?" questions
- Use `mem_kg_invalidate` when a fact changes (person switches teams, tech is replaced)
