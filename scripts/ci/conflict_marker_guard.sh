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
#
# `*.md` was missing from this list, and that is not a cosmetic gap. The files that conflict on
# EVERY rebase here are `sahool-brain/*.md` — they are append-only, so both sides always add
# different entries. A bare `=======` survived a resolve into `log.md` and both conflict guards
# went green: this one never looked at Markdown, and the Python guard ignores a lone `=======`
# by design (it is a legitimate setext underline). So the one file class that conflicts most
# often was the one class nobody checked.
#
# Extending the pathspec is safe here, measured not assumed: zero tracked `*.md`/`*.txt`/`*.toml`
# `*.cfg`/`*.ini` files contain a line matching this pattern today. And a stray `=======` in
# Markdown is never harmless — it turns the line ABOVE it into an H1 heading, so the damage is
# silent rather than loud.
set -euo pipefail
cd "$(dirname "$0")/../.."

if git grep -nE '^(<<<<<<< |=======$|>>>>>>> )' -- \
     '*.py' '*.pyi' '*.conf' '*.yml' '*.yaml' '*.ts' '*.tsx' '*.js' '*.jsx' '*.sh' '*.sql' '*.json' \
     '*.md' '*.txt' '*.toml' '*.cfg' '*.ini'; then
  echo "❌ conflict_marker_guard: committed git conflict markers found above — an unresolved merge"
  echo "   landed in tracked source. Resolve the conflict and recommit; do not ship markers."
  exit 1
fi
echo "✓ conflict_marker_guard: no unresolved git conflict markers in tracked source"
