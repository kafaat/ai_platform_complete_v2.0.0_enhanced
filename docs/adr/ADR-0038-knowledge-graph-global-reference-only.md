# ADR-0038 — The knowledge graph is a global reference store only

- **Status:** Accepted (owner decision, 14 November 2026); implemented in source by PR #1478, which closes #1472.
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
   `upsert_edge` call `assert_global_reference_record`, and the REST handlers also
   check the whole request body (extra top-level keys included, which the request
   models now keep instead of dropping). A refused write answers **422** with
   `detail.code = "kg_tenant_scoped_data_forbidden"`, the offending path and a
   reason. Section "What is enforced" below lists the exact rules.
2. **Reads are global by declaration.** Every authenticated tenant reads the same
   rows through REST and GraphQL. This is the intended behaviour of a reference
   store, not an isolation failure.
3. **`X-Tenant-Id` authenticates only.** A missing or blank header is still refused
   with `403 missing_tenant`; the value is not used as a row filter.
4. Writes still require the internal service token (`X-Agent-Token`), and the
   GraphQL facade stays read-only.

If private graph data is needed later, it goes in a **separate store with its own
isolation model**, which is a new decision, not an extension of this one.

## What is enforced

**Keys** in the body, `properties` and any nested mapping or list, and inside
string values that parse as a JSON object or array, are normalised (Unicode NFKC,
case-folded), split on `_ - .`, whitespace and camelCase, and reduced to singular
tokens. A key is refused when:

- a token is a scope word — `tenant`, `farm`, `farmer`, `field`, `plot`, `parcel`,
  `org`, `organization`/`organisation`, `user`, `owner`, `account`, `customer` —
  or such a word glued to `id`/`uuid`/`key`/`ref`/`code` (`tenantid`);
- it contains `created by`, `updated by` or `owned by`;
- a token is `email`, `geometry`, `geom`, `geojson`, `polygon`, `multipolygon`,
  `wkt` or `wkb` (personal or location data, whatever the value).

The only exemption is an explicit allowlist of agronomic compounds, matched as
whole token pairs: `field capacity`, `field crop`, `field pea`, `field bean`,
`farm gate`. A key that holds an allowlisted pair and another scope word
(`field_capacity_tenant`) is still refused.

**Private marks.** `private` / `is_private` refuse the record when true; the strings
`false`, `no`, `0`, `off`, `n` and the empty string count as false. `visibility`,
`scope` and `access` accept only the strings `global` or `public`; any other value,
including lists, `null`, `restricted`, `organization` and `user`, counts as private.

**Identifiers.** `node_id`, `edge_id`, `subject_id`, `object_id`, `label`, `name` and
`relation` are refused when they encode a scope. `tenant`, `org`/`organization`,
`user`, `owner`, `account`, `customer` or `farmer` followed by any further segment
is refused (`tenant-acme-e`, `org:7`). `farm`, `field`, `plot` and `parcel` are also
reference vocabulary, so they are refused only when followed by `:` `/` `=` `#` `@`
or by a segment containing a digit (`field:7`, `farm-12`, `plot_3b`). A bare label
such as `Field` or `Farm` is legitimate reference vocabulary (the class of things,
not one tenant's instance) and stays allowed, as do ids such as `field_crops`.

## What is not enforced

- **Free text.** Values of other properties, and words in names that do not form a
  scope identifier, are not inspected for private content (for example a
  description naming a farmer). Curated ingestion remains responsible for that.
- **Data already stored.** The guard sees only new writes; nothing scans
  `/data/kg.sqlite` automatically. `scan_existing_rows()` in `kg_store.py`, run as
  `python -m kg_store --scan [DB]` (default `KG_SQLITE_PATH`), opens the database
  read-only (`mode=ro`) and reports every stored node and edge that violates the
  rules above as JSON, exiting 1 if any. It deletes nothing; what to do with a
  finding is an owner decision.

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
- (−) The guard is rule-based (see "What is not enforced"): free text and rows
  stored before it are outside its reach; the second is reportable with the scan.
- (−) A reference property whose key holds a scope word outside the allowlist
  (`owner`, `field_notes`) is refused; it must be renamed (for example
  `publisher`, `notes`) or the compound added to the tested allowlist by review.
