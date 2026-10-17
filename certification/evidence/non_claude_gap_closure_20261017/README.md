# Non-Claude source closure — 2026-10-17

Base: `2ca779c6e3341467ef4f79a98f30e7a18632f3b7` (merged #1201).
Branch: `chatgpt/non-claude-gap-closure-20261017`.

The owner requested implementation of gaps outside Claude's reported batch.
This slice implements three source changes without modifying Claude's fifteen
gap areas, frozen runtime paths, migrations, deployment configuration or gates.
It does not claim closure of the whole remaining inventory.

## Source outcomes

- `OFFLINE-CURSOR-BOUND-TO-A-NAIVE-TIMESTAMP-01`: source fixed. Compare UTC
  instants, interpreting legacy offset-free values as UTC, matching their old
  producer. Invalid cursors replay all operations; invalid operation timestamps
  are retained and cannot become the newest cursor. New operation/attempt stamps
  carry UTC explicitly. Retention compares instants and preserves unknown stamps.
  No stored timestamp is rewritten; the original newest timestamp is returned.
  This does not redesign cursor tie-breaking or prove device/server rollout.
- `SPECTRAL-MSI-ABSENT-FROM-DEFAULT-PRODUCTS-01`: source fixed. Add MSI to
  `AutoBackfillPolicy.default_indices` and `CORE_TIMELINE_INDICES`. Default
  requests now include the already implemented MSI calculation, and explicit MSI
  requests receive the same cloud quality ceiling as the core spectral set.
  No backfill was started and no satellite scene or field acceptance is claimed.
- `JWT-DECODE-OUTSIDE-SHARED-SECURITY-01`: partial. Both MCP call sites now use
  the canonical decoder, preserving PyJWT semantics, existing keys/algorithms,
  issuer checks and observe mode. A narrow security-subpackage bridge supports
  the source layout without exposing unrelated root `shared` modules through
  MCP's shadow package. The image already merges these sources. The frozen
  actuator call and rollout of enforce mode remain outside this source change.

## Evidence and limits

`tests_v9/test_non_claude_gap_closure.py` executes service modules in isolated
Python processes. The same eleven cases on the clean base yielded ten failures
and one passing control; the candidate passes all eleven. Failures include the
actual timestamp comparison/retention behaviour, absent default MSI and absent
canonical security imports under the MCP shadow package. Broader suites and
generated-artifact verification are recorded in the final validation receipt.

The UTC debt ratchet now has an empty debt set; the direct JWT call ratchets
shrink from three sites to one. No mutation was added, removed or re-anchored.
No architecture ceiling or security gate was relaxed.

## Migrator observation — not closed

The complete registry entry for
`MIGRATOR-SCRIPT-DEFAULT-ROLE-PASSWORDS-01` records that the source fix already
landed in #1170. This supersedes the earlier audit summary that suggested the
source repair itself was still pending. On this follow-up, the Railway read
interface lists APP_DB_PASSWORD, JOBS_DB_PASSWORD, ODOO_DB_PASSWORD and
INGEST_DB_PASSWORD for `sahool-migrate-main` in both staging and production.
OAuth redacts all values: existence of names proves neither nonempty values nor
absence of historical defaults, and no apply was enabled. The gap stays open.

## Remaining boundaries

Restricted-role live PostgreSQL/RLS acceptance, Decision SoR promotion,
SECURITY DEFINER ownership, tenant-GUC migrations, device signature changes and
edge idempotency migrations require their scoped operational/frozen-path
processes. Hardware, field agronomy, RAG acceptance datasets, licenses and
service ownership cannot be replaced with invented evidence or owner choices.
Claude's OUTBOX, frozen-path, locale, TTS sandbox, TLS, auth-IP, edge evidence,
text/PR-finding guards, TAW/Kc, restart, compose and weather-worker work is not
duplicated here. Its unpublished bytes are not part of this branch.

## Existing correlation fix — final native proof reconciled

`CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01`
is now source-fixed in the registry. The missing native PG16 proof did run on
#1201's final PR head: all 62 tests passed, including Decision036 and platform
v235. `correlation_pg16_receipt.json` preserves the job URL, exact head and
merge-tree identity, and relevant timestamped test lines. This is reconciliation
of an already merged repair, not a new migration or production acceptance.
The candidate registry therefore has 96 open canonical IDs, 431 fixed and
3 verified; two former section-only gaps now have canonical fixed state lines.

## Local pre-push result

The first default preflight ran all suites. Unit tests reported 9349 passed,
40 skipped and one failure: the orphan-heading baseline still said 211 after
two entries gained canonical states. The baseline is tightened to the measured
209; all 13 guard cases and 11 behavioral witnesses then passed (24 total).
Repository and platform suites both exited zero. The full raster CI-shaped
suite passed 614 tests; two PostgreSQL-dependent cases skipped locally.
Gitleaks 8.30.1 found no leaks in the staged diff.

The other preflight failure/skip was the expected rejection of Capability-Impact
before committing a dirty tree. Post-commit range checks and the derived PR
declaration are verified separately and reported in the PR. No all-green new
monolithic preflight or zero-test-skip run is asserted by this receipt.
