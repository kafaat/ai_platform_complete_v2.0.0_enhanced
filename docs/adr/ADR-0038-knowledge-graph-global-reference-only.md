# ADR-0038 — The knowledge graph is a global reference store only

- **Status:** Accepted (owner decision, 14 November 2026); implemented in source by the PR that closes #1472.
- **Date:** 2026-11-15
- **Scope:** `services/knowledge-graph` (`kg_store.py`, `main.py`) and every writer of its store.
- **Issue:** [#1472](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/issues/1472) — global-only knowledge graph vs tenant-partitioned read isolation.

## Context

`SQLiteAgGraphStore` keeps `kg_nodes` and `kg_edges` with no tenant column, and
`query_edges()` takes no tenant. The REST read (`GET /v1/edges`) and the read-only
GraphQL facade (`POST /graphql`) require a gateway-injected `X-Tenant-Id`, but the
handlers never pass it to the store. Authenticating a tenant is not the same as
isolating rows: the issue found no current leak, because the graph holds only the
curated reference ontology, but anything tenant-specific written into this store
would be readable by every tenant.

## Decision

Option **A** of #1472: the knowledge graph is a **global, non-tenant agricultural
reference store only**. Data specific to a tenant, farm, field or user must never
enter it.

1. **Write guard at the store boundary.** `SQLiteAgGraphStore.upsert_node` and
   `upsert_edge` call `assert_global_reference_payload` on the record's properties,
   and the REST handlers call it on the whole request body (extra top-level keys
   included, which the request models now keep instead of dropping). A record is
   refused if any key, at any depth, normalises to `tenant`, `tenant_id`, `farm`,
   `farm_id`, `field`, `field_id`, `user`, `user_id`, `owner` or `owner_id`
   (case and separators ignored), or if it is marked private (`private` /
   `is_private` truthy, or `visibility` / `scope` / `access` set to `private`,
   `tenant`, `farm`, `field` or `user`). The API answers **422** with
   `detail.code = "kg_tenant_scoped_data_forbidden"` and the offending key path.
2. **Reads are global by declaration.** Every authenticated tenant reads the same
   rows through REST and GraphQL. This is the intended behaviour of a reference
   store, not an isolation failure.
3. **`X-Tenant-Id` authenticates only.** A missing or blank header is still refused
   with `403 missing_tenant`; the value is not used as a row filter.
4. Writes still require the internal service token (`X-Agent-Token`), and the
   GraphQL facade stays read-only.

If private graph data is needed later, it goes in a **separate store with its own
isolation model**, which is a new decision, not an extension of this one.

## Rejected alternative

**Option B — tenant-partitioned store** (a `tenant_id` column, tenant/global
policies, filters on both REST and GraphQL). Rejected for now because it is a much
larger change, it needs a reviewed schema and data migration of the KG store, and
no private ingestion into the graph is planned. Its cost buys nothing while the
graph holds only public reference knowledge.

## Consequences

- (+) The invariant that made the reads safe is now enforced at the write boundary
  instead of assumed; the guard and the global reads are covered by
  `tests_v9/test_kg_global_reference_only.py`.
- (+) No schema change, no migration, no change to read consumers or decision
  authority (the graph stays reference-only, non-prescriptive).
- (−) The guard is key-based: it refuses records that declare a scope, but it does
  not inspect free text in names or property values for private content. Curated
  ingestion remains responsible for that.
- (−) A reference property that happens to be named `owner` or `field` is refused;
  it must be renamed (for example `publisher`, `discipline`).
