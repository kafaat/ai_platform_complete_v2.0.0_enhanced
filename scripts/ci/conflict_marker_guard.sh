#!/usr/bin/env bash
# Fail CI if any committed git conflict markers survive in tracked source.
#
# Why: a parallel session once merged a branch that left unresolved `<<<<<<< / ======= / >>>>>>>`
# markers in nginx.v9.conf and vegetation_runtime.py — the latter a hard SyntaxError (unimportable)
# — yet CI went green because the main suite imports neither. "CI green measures only what it
# tests." One structural grep would have caught it at commit time; this is that grep.
#
# Pattern is precise to git's markers so it does NOT flag comment banners (e.g. a 70-char `====`
# line): the middle marker must be exactly seven `=` on its own line; the outer two need the
# trailing space git always writes.
set -euo pipefail
cd "$(dirname "$0")/../.."

if git grep -nE '^(<<<<<<< |=======$|>>>>>>> )' -- \
     '*.py' '*.pyi' '*.conf' '*.yml' '*.yaml' '*.ts' '*.tsx' '*.js' '*.jsx' '*.sh' '*.sql' '*.json'; then
  echo "❌ conflict_marker_guard: committed git conflict markers found above — an unresolved merge"
  echo "   landed in tracked source. Resolve the conflict and recommit; do not ship markers."
  exit 1
fi
echo "✓ conflict_marker_guard: no unresolved git conflict markers in tracked source"
