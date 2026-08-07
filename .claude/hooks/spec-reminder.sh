#!/bin/bash
# Stop hook: when the working tree has meaningful code changes, prompt Claude
# (once per distinct change-set) to check whether SPEC.md needs updating.
#
# Watches the WHOLE repo and excludes noise, rather than allow-listing folders
# — so any new package (api/, frontend/, …) is covered without editing this.

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root" || exit 0

# Paths that should NOT trigger a spec review: docs (incl. SPEC.md itself, so
# updating it doesn't re-fire), the .claude/ tooling, and lockfiles.
excludes=(':(exclude)*.md' ':(exclude)docs' ':(exclude).claude'
          ':(exclude)*.lock' ':(exclude)package-lock.json')

# Hash the diff of everything-but-noise vs HEAD (staged + unstaged), plus
# untracked files (new modules/cases). Gitignored paths (node_modules, dist,
# .env) are excluded by --exclude-standard / by not being tracked.
diff_hash=$( { git diff HEAD -- . "${excludes[@]}" 2>/dev/null; \
               git ls-files --others --exclude-standard -- . "${excludes[@]}" 2>/dev/null; \
             } | shasum | cut -d' ' -f1)
empty_hash=$(printf '' | shasum | cut -d' ' -f1)

# No relevant changes -> nothing to do
[ "$diff_hash" = "$empty_hash" ] && exit 0

# Already reminded for this exact change-set -> stay quiet
cache="$repo_root/.claude/.spec-reminder-hash"
[ -f "$cache" ] && [ "$(cat "$cache")" = "$diff_hash" ] && exit 0
echo "$diff_hash" > "$cache"

cat <<'EOF'
{"decision": "block", "reason": "Spec check: this working tree has code changes. Review whether SPEC.md needs updating to stay accurate (agent tree, state keys, web layer, guardrails, eval cases, config, known gaps). If the change is meaningful, update SPEC.md now; if not, briefly say so and finish. You will not be reminded again for this exact change-set."}
EOF
exit 0
