#!/bin/bash
# Stop hook: when the working tree has meaningful code changes, prompt Claude
# (once per distinct change-set) to check whether docs/SPEC.md needs updating.

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root" || exit 0

# Hash the current diff of spec-relevant paths (staged + unstaged vs HEAD),
# plus untracked files under those paths (new modules/eval cases)
diff_hash=$( { git diff HEAD -- cv_agents main.py tests pyproject.toml 2>/dev/null; \
               git ls-files --others --exclude-standard -- cv_agents main.py tests 2>/dev/null; } | shasum | cut -d' ' -f1)
empty_hash=$(printf '' | shasum | cut -d' ' -f1)

# No relevant changes -> nothing to do
[ "$diff_hash" = "$empty_hash" ] && exit 0

# Already reminded for this exact change-set -> stay quiet
cache="$repo_root/.claude/.spec-reminder-hash"
[ -f "$cache" ] && [ "$(cat "$cache")" = "$diff_hash" ] && exit 0
echo "$diff_hash" > "$cache"

cat <<'EOF'
{"decision": "block", "reason": "Spec check: this working tree has changes in cv_agents/, main.py or tests/. Review whether docs/SPEC.md needs updating to stay accurate (agent tree, state keys, eval cases, config, known gaps). If the change is meaningful, update SPEC.md now; if not, briefly say so and finish. You will not be reminded again for this exact change-set."}
EOF
exit 0
