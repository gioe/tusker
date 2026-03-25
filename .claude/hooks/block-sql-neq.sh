#!/bin/bash
# PreToolUse hook: blocks != in SQL contexts.
# Shell history expansion breaks != — use <> instead.

# Read JSON from stdin
input=$(cat)

# Extract the command from tool_input.command, with quoted strings stripped.
# Neither single- nor double-quoted string content can be SQL passed to tusk —
# metadata arguments (commit messages, task summaries, convention text) are not SQL.
# Stripping both quote styles prevents false positives like:
#   tusk commit 38 "fix != false positive"   (double-quoted message)
#   tusk conventions add 'use != syntax'     (single-quoted text)
command=$(echo "$input" | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
cmd = data.get('tool_input', {}).get('command', '')
# Remove single- and double-quoted substrings — neither can be raw SQL
cmd = re.sub(r\"'[^']*'\", '', cmd)
cmd = re.sub(r'\"[^\"]*\"', '', cmd)
print(cmd)
" 2>/dev/null)

# Quick exit: no != means nothing to check
echo "$command" | grep -q '!=' || exit 0

# Only block when tusk is being invoked (the only sanctioned way to run SQL).
# This avoids false positives on git commits, echo strings, etc. that happen
# to mention != alongside SQL keywords as documentation text.
if echo "$command" | grep -qE '(^|[|;&]|&&|\|\||\$\()\s*(bin/)?tusk\b'; then
  echo "Use <> instead of != in SQL — shell history expansion breaks !=."
  exit 2
fi

exit 0
