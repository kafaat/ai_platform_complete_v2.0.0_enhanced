# PR merge-history secret scanning — 2026-10-20

Base: `main@c9e8c15e03a60a6644b02bb453e54de9cc31f212`.
Gap: `GITLEAKS-PR-SCAN-SKIPS-CONTENT-INTRODUCED-BY-A-MERGE-01`.

The pinned [action source](https://github.com/gitleaks/gitleaks-action/blob/e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e/src/gitleaks.js) uses `--no-merges --first-parent` on pull requests. A supplemental PR-only scan now retains all parents with `--full-history` and emits merge changes relative to the first parent with `--diff-merges=first-parent`. The latter controls the merge diff, not history traversal. Event base/head SHAs are passed through environment variables, checked as existing commits, and bounded with `base..head`. The original action and its scheduled/push scans are unchanged.

## Measured evidence

- `before.log`: four added regression cases fail on the original workflow; eight existing allowlist tests pass.
- `after.log`: all 12 scope cases and 23 text-encoding cases pass (35 total) after correcting explicit UTF-8 handling in the new fixtures. Temporary Git repositories prove second-parent additions, merge-only additions, and a secret later removed from the final tree remain within the scanned history.
- `scanner-proof.json`: real Gitleaks 8.30.1, verified against the release checksum, with default rules and synthetic credentials. The original options exit 0 in all three defect cases. The supplemental options exit 2 in all three; the clean fixture remains 0. Results contain rule names/counts only, not credential values.
- `verify_live.py`: reproduces the scanner acceptance in disposable repositories with `python verify_live.py --gitleaks /absolute/path/to/gitleaks`.
- `sources.json`: source identities for the measured implementation.

## Limits

This closes the tested PR history-selection blind spot in the candidate source. GitHub CI on the final pushed head remains a separate gate; the registry remains open until acceptance. No token rotation, incident investigation, production change, or changes to Gitleaks allowlists. Push-event first-parent behavior remains outside this PR-only correction; the existing scheduled full-history scan remains unchanged. A scanner finding here proves detection, not exposure of a real credential.

Synchronized without source conflicts onto #1244/main@18239b410e220e4a53872a5d8aa7ffbef8c34803 after the initial reproduction. All application, shared runtime, and Compose files remain identical to that main.
