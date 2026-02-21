#!/bin/bash
# PreToolUse hook: warns when raw 'git commit -m' is used with a message
# that doesn't start with [TASK-<id>]. Advisory only — exits 0.
# tusk commit already enforces this format; this is a nudge for raw git calls.

input=$(cat)

command=$(echo "$input" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('tool_input', {}).get('command', ''))
" 2>/dev/null)

# Quick exit: no 'git commit' in command
echo "$command" | grep -q 'git commit' || exit 0

# Quick exit: tusk commit invocations already enforce the format — skip them
if echo "$command" | grep -qE '(^|[|;&]|&&|\|\||\$\()\s*(bin/)?tusk\s+commit\b'; then
  exit 0
fi

# Write checker to a temp file to avoid heredoc-inside-subshell quoting issues
tmppy=$(mktemp /tmp/commit-msg-check.XXXXXX.py)
cat << 'PYEOF' > "$tmppy"
import sys, re, os

cmd = os.environ.get('TUSK_CMD', '')

# Skip --amend (no new message required)
if '--amend' in cmd:
    sys.exit(0)

# Skip -F / --file (message comes from file, not -m)
if re.search(r'(\s|^)(-F\b|--file\b)', cmd):
    sys.exit(0)

# Skip if -m value is a subshell expression (can't inspect at hook time)
if re.search(r'(?:-m|--message)\s+["\']?\s*\$\(', cmd):
    sys.exit(0)

# Skip if no -m / --message flag
if not re.search(r'(?:-m|--message)\b', cmd):
    sys.exit(0)

# Message has [TASK-<id>] prefix — OK
if re.search(r'(?:-m|--message)\s+["\']?\[TASK-[0-9]+\]', cmd):
    sys.exit(0)

print('WARN')
PYEOF

result=$(TUSK_CMD="$command" python3 "$tmppy" 2>/dev/null)
rm -f "$tmppy"

if [[ "$result" == "WARN" ]]; then
  echo "Warning: commit message does not start with [TASK-<id>]. Use 'tusk commit <id> \"<message>\" <files>' to enforce this format automatically."
fi

exit 0
