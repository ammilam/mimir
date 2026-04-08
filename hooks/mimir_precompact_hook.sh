#!/usr/bin/env bash
# Mimir pre-compact hook for Claude Code
# Fires before context compression - emergency save before the context window shrinks.
#
# Setup: Add to your Claude Code settings:
# {
#   "hooks": {
#     "PreCompact": [{
#       "matcher": "",
#       "hooks": [{
#         "type": "command",
#         "command": "/path/to/mimir/hooks/mimir_precompact_hook.sh"
#       }]
#     }]
#   }
# }

set -euo pipefail

SESSION_ID="claude-precompact-$(date +%Y%m%d-%H%M%S)"
SESSION_ID="${SESSION_ID//[^a-zA-Z0-9_-]/}"

echo "Mimir: pre-compact save triggered for session $SESSION_ID"
echo "IMPORTANT: Context is about to be compressed. Store any unsaved decisions, debugging findings, or important context NOW using mem_store or mem_batch_store with session_id='$SESSION_ID'."
