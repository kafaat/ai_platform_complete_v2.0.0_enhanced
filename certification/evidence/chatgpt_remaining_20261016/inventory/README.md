# Remaining inventory work — 2026-10-16

Base: `9f0bcece487a8e9e2fc1ea590af5f2af5ab17504`.

Added a read-only diagnostic tool and 25 unit tests. No database, production inventory, historical correction, or migration was run. Both assigned gaps remain open.

## Inventory invocation (operator preparation only)

```bash
# Supply a separately authorized SELECT-only role in SAHOOL_INVENTORY_DATABASE_URL.
python3 scripts/diagnostics/element84_legacy_inventory.py \
  --tenant-id '<one authorized tenant UUID>' \
  --output '/private/evidence/element84-tenant-inventory.json' \
  --limit 10000
```

No default tenant, database URL, provider, or processing version is inferred. The tool refuses superuser/BYPASSRLS roles, unsupported or missing tenant RLS context, missing tables, schema/permission errors, and any returned cross-tenant row. Queries execute in one read-only repeatable-read transaction with a 30-second per-statement deadline and explicit tenant predicates. Each table query fetches at most limit+1 rows; exit 3 reports truncation, exit 2 reports failure, exit 0 only means the bounded role-visible snapshot completed. Output is a new mode-0600 file and never overwrites an existing receipt. Complete raw error/request/result/geometry/COG URL payloads are excluded.

The inventory reads six actual tables: raster_assets (v14/v143/v154), raster_registry (v114), backfill_run_items/backfill_runs (v144/v146), raster_batch_jobs (v154), distributed_raster_jobs (v116). Selected JSON paths may legitimately be absent and remain NULL. `algorithm_version` is displayed separately and never renamed `processing_version`. Current raster_assets writer historically omitted provider in provenance; provider-unknown records stay in the candidate set. A sibling change adds explicit request provider for future writes; it cannot retroactively attribute old rows.

The tool inventories all role-visible products and failed durable jobs, retaining non-Element84 rows with explicit provider classification. Counts are source-row counts, not deduplicated damaged-product totals. HTTP 422 attribution requires literal HTTP/status evidence; arbitrary 422 digits in IDs are not accepted. Historical API failures that were never durably stored cannot be recovered by this tool.

Validation:
- `red-tool-absent.log`: tests fail to import the missing tool on the untouched base. This is an absent-capability witness, **not** proof of the historical production defect.
- `green-unit.log`: 25 passed / 0 skipped. Async mocks exercise driver call contracts, not PostgreSQL syntax/RLS enforcement.
- Native PostgreSQL is unavailable in this environment. Real SQL, restricted-role RLS and authorized tenant census remain required before operational acceptance.
- `correlation-audit.md`: precise source chain, owner boundaries, and proposed change scope; no approvals table invented.
