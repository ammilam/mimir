#!/usr/bin/env bash
# Mimir auto-save hook for Claude Code
# Triggers every N messages (configure via Claude Code hooks).
# Asks Claude to store a summary of the current session's decisions,
# code changes, and insights into mimir.
#
# Setup: Add to your Claude Code settings:
# {
#   "hooks": {
#     "Stop": [{
#       "matcher": "",
#       "hooks": [{
#         "type": "command",
#         "command": "/path/to/mimir/hooks/mimir_save_hook.sh"
#       }]
#     }]
#   }
# }

set -euo pipefail

SESSION_ID="claude-$(date +%Y%m%d-%H%M%S)"
# Sanitize SESSION_ID to prevent path traversal
SESSION_ID="${SESSION_ID//[^a-zA-Z0-9_-]/}"

echo "Mimir: auto-save triggered for session $SESSION_ID"
echo "Reminder: Store important decisions, code changes, and insights from this session using mem_store or mem_batch_store with session_id='$SESSION_ID'."
