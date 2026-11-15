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
   reason (or the limit codes below). Section "What is enforced" below lists the exact rules.
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

The rule refuses what is **shaped like** a scope identifier, not every key that
contains a scope word (a first, broader token rule had both bypasses and false
positives; it was replaced in the second #1478 review round).

**Normalisation** of keys, ids, labels and names: Unicode NFKC; format characters
(category Cf, such as zero-width spaces) removed; a small confusables table maps
Cyrillic and Greek look-alikes (а е о р с у х і …) and dotless `ı` to ASCII;
Unicode hyphens (U+2010 to U+2015) and the minus sign (U+2212) mapped to `-`;
Arabic diacritics and tatweel removed; case-folded; split on `_ - . : /`,
whitespace, camelCase and digit/letter boundaries (`field7` → `field`, `7`).
English plurals reduce to the singular, and the Arabic article `ال` is dropped.

**Scope words:** tenant, farm, farmer, field, plot, parcel, org, organization,
organisation, user, owner, account, customer, grower, holding, site, company,
client, member, person, landlord, and مستأجر, مزرعة, مزارع, حقل, قطعة, مالك,
مستخدم, منظمة, عميل.

**Keys** in the body, `properties`, any nested mapping or list, and inside string
values holding JSON (a leading BOM and one JSON string-literal layer are
unwrapped) are refused when:

- the key is a scope word or its plural on its own (`owner`, `tenants`, `حقل`);
- a scope word is immediately followed by an identifier suffix — `id`, `ids`,
  `uuid`, `key`, `ref`, `code`, `no`, `number`, `name` — or glued to one
  (`farm_id`, `tenantID`, `tenant.id`, `farmname`); in Arabic an identifier word
  (`معرف`, `رقم`, `رمز`, `اسم`, `هوية`) next to a scope word (`معرف_المزرعة`);
- it carries personal or location data: a token `email`, `phone`, `geometry`,
  `geojson`, `coordinates`, `latitude`, `longitude` or `address`, or the whole key
  is `location`, `lat`, `lon`, `lng`, `boundary`, `author`, `geo_point`,
  `created_by`, `submitted_by`, `updated_by` or `owned_by`;
- its value is a GeoJSON object (a mapping whose `type` is a GeoJSON geometry or
  feature type), under any key.

So `field_resistance`, `field_trial_results`, `field_emergence_pct`,
`farm_size_ha`, `plot_size_m2`, `user_guide_url`, `source_organization`,
`data_owner` and `owner_institution` pass; they are regression tests.

**Private markers.** `private` / `is_private` refuse when true (the strings
`false`, `no`, `0`, `off`, `n` and the empty string are false). A key whose tokens
include visibility, privacy, access, scope, sharing, audience, acl, shared or public
refuses an explicit marker: a value (or list element) in private, restricted,
organization, tenant, internal; `public` / `is_public` false; `shared_with`
non-empty. Free text such as "Applies to cereals in arid zones" or "open data", and
values such as `user`, are not markers and pass.

**Ids, labels and names** (`node_id`, `edge_id`, `subject_id`, `object_id`,
`label`, `name`, `relation`): a scope word is refused only next to a token that
looks like an identifier.

- After the scope word, behind `:` `#` `/` `=` `@`, any token: `tenant:acme`,
  `field/7`, `farm=acme`, `user@acme`, `مزرعة:12`.
- After it, behind `-` or glued (camelCase or digit boundary), a token with a
  digit or an id suffix (`id`, `ids`, `uuid`, `key`, `ref`, `code`): `farm-12`,
  `field7`, `farm12`, `customerId42`. For `tenant`, `org`, `organization` and
  `organisation`, which are never agronomic prose, any token behind `-`:
  `tenant-acme`.
- After it, behind `_`, an id suffix: `farm_id`.
- Before the scope word, a token with a digit behind `:` `#` `/` `=` `@`, `-` or
  glued: `7:field`, `12farm`.

Hyphenated prose, CURIEs and reference ids pass, and are regression tests:
`Site-specific nutrient management`, `On-farm research`, `Farmer-led
irrigation`, `Farm-to-fork strategy`, `Multi-site trial`, `Farm-gate price 2024`,
`field-capacity`, `on-farm-trial`, `wheat-field-guide`, `fao:field_capacity`
(the term before `:` has no digit and `field_capacity` has no id suffix),
`Farmer field schools`, `Tenant farming systems`, `FieldTrial2019`,
`plot_2x2_design`, and the bare labels `Field` and `Farm`, which name the class of
things, not one tenant's instance.

**Limits.** Nesting deeper than 64 levels answers 422 `kg_payload_too_deep`; more
than 10 000 keys and list items answers 413 `kg_payload_too_large`. A body too
deep for the JSON parser itself is refused by the framework with 400. A lone
surrogate in a key, value or identifier, and any other unexpected error inside
the guard, answers 422 `kg_payload_unprocessable`; the echoed path is escaped so
the error response itself is valid JSON. These are the failures the tests
exercise; a 500 from outside the guard (for example the database being
unavailable) is not ruled out.

## What is not enforced

- **Free text.** Descriptions and other prose values are not inspected for
  private content (for example a description naming a farmer).
- **Synonyms beyond the lists** (for example `estate`, `ranch`, `household`).
- **Identifier shapes not refused:** a word before a scope word behind `-`
  (`acme-tenant`; refusing it would refuse `Multi-tenant` and `On-farm`); an
  alphabetic short code after `-` (`farm-ab`); ids joined only by `_` or spaces
  (`plot_3b`, `farm twelve`); and the separators `.`, `|`, `;`, `,` (treated as
  prose separators), and `+`, `(`, `)`, `\` (not split at all), so
  `farm.12`, `farm|12`, `farm+12` and `farm(12)` pass. `@` and `=` are enforced
  after a scope word only.
- **Key false positives (documented, not changed):** any key holding a personal
  or location token is refused even when it names a reference property, for
  example `leaf_geometry`, `latitude_range` or `address_space`.
- **Other scripts** beyond the confusables table and the listed Arabic words.
- **Other encodings**: base64, Python `repr`, URL-encoding or anything that is not
  JSON text inside a string.
- **Data already stored.** The guard sees only new writes; nothing scans
  `/data/kg.sqlite` automatically. `scan_existing_rows()` in `kg_store.py`, run as
  `python -m kg_store --scan [DB]` (default `KG_SQLITE_PATH`), opens the database
  through a `mode=ro` connection that SQLite refuses to write through, and
  reports as JSON every stored node and edge that breaks the rules above,
  including rows whose `properties_json` is not valid JSON. It exits 1 if any are
  found and deletes nothing; what to do with a finding is an owner decision.

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
- (−) A reference property named exactly as a scope word or a scope identifier
  (`owner`, `site_code`) is refused; it must be renamed (for example `publisher`).
