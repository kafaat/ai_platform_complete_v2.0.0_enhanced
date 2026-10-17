# Architecture re-measurement — 2026-10-17

**Measurement only.** Nothing here changes the contract, a baseline, a guard threshold, a
frozen path or service code, and nothing here closes a gap: the registry wording is the
lead's decision, and the verdict on each undeclared write belongs to the table's owner.

| | |
|---|---|
| SHA measured | `ec3927cef45a3da53aaa14950093e734ce8e072a` (= `origin/main`, `raw/00_head.txt`) |
| Re-run | `bash certification/evidence/architecture_remeasure_20261017/commands.sh` from the repo root (optional `NATS_SERVER_BIN=<nats-server 2.15.x>` for the live NATS probe) |
| Raw outputs | `raw/NN_*.txt`, each starting with the exact command (`$ …`) and ending with `[exit=N]` |
| Machine-readable | `summary.json` (key numbers + command + SHA) · `ownership_remeasure.json` · `connectivity_remeasure.json` · `edges_baseline.json` |
| Helpers | `measure_ownership.py` and `measure_edges.py` import the existing engines unmodified (`scripts/ci/db_writer_ownership_guard.py`, `scripts/diagnostics/build_main_inventory.py` + `resolve_inventory_edges.py`); they write nothing into the tree |

**Acceptance levels are kept apart everywhere:** *local* = this container (static reads and
unit tests; *local process* = a real binary started here without Docker; *local compose* =
**not available**, Docker daemon absent, `raw/50_live_tools.txt`) · *staging* (Railway) and
*production*: **not accessed by this task**. "Not measured" never means "fails".

## 1. OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01

- `python3 scripts/ci/db_writer_ownership_guard.py --check` → `db_writer_ownership_guard_ok baseline=67`
  (`raw/10_…`). **Baseline is 67, not the last documented 69**; the re-measured set equals the
  baseline key-for-key (`ownership_remeasure.json#baseline_equals_measurement = true`).
- **69 → 67 is not a repair.** `#1205` (`f3fd099e9`) deleted `services/weather-polygon-worker`;
  its two keys (`field_weather_overlay::weather-polygon-worker`, `weather_signals::weather-polygon-worker`)
  left the baseline with the writer (`raw/14_…`). Side effect worth the owner's eye:
  **`field_weather_overlay` now has zero SQL-literal writers** (`raw/14a_…`, exit 1) while
  `weather-signal-engine` still reads it (`services/weather-signal-engine/src/main.py:50`, `raw/14b_…`).
  The scanner sees SQL literals in Python only, so "zero" is "none seen", not proof of absence.
- Contract: 391 tables; **0** owner/writer/reader/mirror names without a directory in the tree
  (no table is declared owned by the deleted worker — the contract never named it).
  `ownership_extraction_alignment_guard`: 382 tables owned by a live extraction target, 0
  extra declared writers (`raw/11_…`). 13 SQLite-only write sites are excluded by the guard's
  rule (2 of them not authorised) — listed in `ownership_remeasure.json#excluded_sqlite_only`.
- By writer: sahool-platform 49 · auth 5 · scripts 5 · raster-service 4 · actuator-service 1 ·
  agents 1 · mcp_servers 1 · weather-signal-engine 1.

### Non-binding hint per write

The hint is derived by declared rules over measured signals (`measure_ownership.py`, `hint()`),
first match wins. **It is a hint for the owner, not a verdict.**

| rule | signal | hint |
|---|---|---|
| R1 | the declared owner also has a SQL write site (dual writer) | code likely wrong |
| R2 | writer is `scripts/` tooling (contract models services only) | cannot tell |
| R3 | owner is `sahool-platform` (the monolith), the only writer is another service, the monolith never writes it | contract likely stale |
| R4 | writer is `sahool-platform`, owner is a live `target_owner` in `platform_extraction_map.json` | code likely wrong (pre-extraction; re-declaring is blocked by `ownership_extraction_alignment_guard`) |
| R5 | service → non-platform service | cannot tell |

Result: **code likely wrong 51** (R4 49 + R1 2) · **contract likely stale 9** · **cannot tell 7**.
Per-row evidence (owner mentions, compose builds, extraction route count, creating migration) is in
`ownership_remeasure.json#rows[].hint_evidence`. Legend below: `code` = code likely wrong,
`contract` = contract likely stale.

#### writer `sahool-platform` — 49

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `actuator_command_outbox` | actuator-service | `services/sahool-platform/api/phase_runtime_store.py:181` | code | R4 |
| `decision_policies` | agriai-engine | `services/sahool-platform/api/routers/decision_policies.py:92` | code | R4 |
| `device_telemetry` | actuator-service | `services/sahool-platform/api/routers/devices.py:151` | code | R4 |
| `documents` | rag-retrieval | `services/sahool-platform/api/routers/documents.py:55` | code | R4 |
| `farm_energy_records` | field-management-service | `services/sahool-platform/core/farm_operations_ledger.py:406` | code | R4 |
| `farm_equipment_records` | field-management-service | `services/sahool-platform/core/farm_operations_ledger.py:425` | code | R4 |
| `farm_input_records` | field-management-service | `services/sahool-platform/core/farm_operations_ledger.py:458` | code | R4 |
| `farm_labor_records` | field-management-service | `services/sahool-platform/core/farm_operations_ledger.py:442` | code | R4 |
| `farm_operation_ledger` | field-management-service | `services/sahool-platform/api/routers/farm_operations_ledger.py:254` | code | R4 |
| `farm_revenue_records` | field-management-service | `services/sahool-platform/api/routers/farm_operations_ledger.py:624` | code | R4 |
| `farm_season_budget_lines` | field-management-service | `services/sahool-platform/api/routers/farm_operations_ledger.py:532` | code | R4 |
| `farm_water_records` | field-management-service | `services/sahool-platform/core/farm_operations_ledger.py:386` | code | R4 |
| `farms` | field-management-service | `services/sahool-platform/api/routers/farms.py:51` | code | R4 |
| `feature_set_specs` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:277` | code | R4 |
| `feature_set_versions_runtime` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:562` | code | R4 |
| `field_boundaries` | field-management-service | `services/sahool-platform/api/routers/boundaries.py:61` · `services/sahool-platform/api/routers/boundaries.py:154` · `services/sahool-platform/api/routers/boundaries.py:215` | code | R4 |
| `field_boundary_graph` | field-management-service | `services/sahool-platform/api/field_boundary_graph.py:73` | code | R4 |
| `field_evidence_snapshots` | raster-service | `services/sahool-platform/api/routers/field_intelligence.py:85` | code | R4 |
| `field_feature_store_candidate` | field-management-service | `services/sahool-platform/api/phase_runtime_store.py:346` | code | R4 |
| `field_geometry_history` | field-management-service | `services/sahool-platform/api/spatial_sync.py:38` | code | R4 |
| `field_lifecycle` | field-management-service | `services/sahool-platform/api/field_lifecycle.py:155` | code | R4 |
| `field_lifecycle_transitions` | field-management-service | `services/sahool-platform/api/field_lifecycle.py:301` | code | R4 |
| `field_state` | field-management-service | `services/sahool-platform/api/field_state_projection.py:799` | code | R4 |
| `field_state_snapshots` | raster-service | `services/sahool-platform/api/event_replay.py:670` | code | R4 |
| `field_tasks` | field-management-service | `services/sahool-platform/api/routers/tasks.py:114` · `services/sahool-platform/api/routers/weather.py:2862` | code | R4 |
| `fields` | field-management-service | `services/sahool-platform/api/main.py:1081` · `services/sahool-platform/api/routers/fields.py:191` · `services/sahool-platform/api/routers/fields.py:1618` · `services/sahool-platform/api/routers/fields.py:1720` · `services/sahool-platform/api/routers/fields.py:1903` · `services/sahool-platform/api/routers/fields.py:2034` | code | R4 |
| `geometry_editing_sessions` | field-management-service | `services/sahool-platform/api/routers/gis_cloud_native.py:393` · `services/sahool-platform/api/routers/gis_cloud_native.py:593` | code | R4 |
| `geometry_locks` | field-management-service | `services/sahool-platform/api/routers/gis_cloud_native.py:628` · `services/sahool-platform/api/routers/gis_cloud_native.py:663` | code | R4 |
| `imagery_automation_fields` | raster-service | `services/sahool-platform/api/imagery_automation.py:239` · `services/sahool-platform/api/imagery_automation.py:255` · `services/sahool-platform/api/imagery_automation.py:984` · `services/sahool-platform/api/imagery_automation.py:1006` | code | R4 |
| `iot_command_dispatch` | actuator-service | `services/sahool-platform/api/phase_runtime_store.py:389` | code | R4 |
| `iot_devices` | actuator-service | `services/sahool-platform/api/routers/devices.py:67` · `services/sahool-platform/api/routers/devices.py:163` | code | R4 |
| `marketplace_apps` | erp-bridge | `services/sahool-platform/api/phase_runtime_store.py:724` | code | R4 |
| `marketplace_installations` | erp-bridge | `services/sahool-platform/api/phase_runtime_store.py:771` | code | R4 |
| `model_lifecycle_decisions` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:437` | code | R4 |
| `model_promotion_history_runtime` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:663` | code | R4 |
| `model_registry_version` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:244` | code | R4 |
| `model_rollback_history_runtime` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:699` | code | R4 |
| `model_serving_aliases_runtime` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:682` · `services/sahool-platform/api/phase_runtime_workers.py:374` | code | R4 |
| `model_versions_runtime` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:641` | code | R4 |
| `point_in_time_snapshots_runtime` | raster-service | `services/sahool-platform/api/phase_runtime_store.py:623` | code | R4 |
| `recommendations` | agriai-engine | `services/sahool-platform/api/routers/recommendations.py:106` · `services/sahool-platform/api/routers/weather.py:2956` | code | R4 |
| `scenario_runs` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:541` | code | R4 |
| `soil_lab_tests` | soil-service | `services/sahool-platform/api/routers/fields.py:3249` · `services/sahool-platform/api/routers/fields.py:3390` | code | R4 |
| `training_datasets` | agriai-engine | `services/sahool-platform/api/phase_runtime_store.py:294` | code | R4 |
| `usage_metering_records` | erp-bridge | `services/sahool-platform/api/phase_runtime_store.py:825` | code | R4 |
| `weather_automation_cache` | weather-service | `services/sahool-platform/api/weather_automation.py:161` | code | R4 |
| `weather_automation_locations` | weather-service | `services/sahool-platform/api/weather_automation.py:141` · `services/sahool-platform/api/weather_automation.py:209` | code | R4 |
| `webhook_subscriptions` | erp-bridge | `services/sahool-platform/api/phase_runtime_store.py:799` | code | R4 |
| `workflow_state` | erp-bridge | `services/sahool-platform/core/workflow_engine.py:181` · `services/sahool-platform/core/workflow_engine.py:344` · `services/sahool-platform/core/workflow_engine.py:353` · `services/sahool-platform/core/workflow_engine.py:421` · `services/sahool-platform/core/workflow_engine.py:522` · `services/sahool-platform/core/workflow_engine.py:531` · `services/sahool-platform/core/workflow_engine.py:589` | code | R4 |

#### writer `auth` — 5

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `audit_log` | sahool-platform | `services/auth/main.py:806` | code | R1 |
| `invitations` | sahool-platform | `services/auth/routers/invitations.py:56` · `services/auth/routers/invitations.py:167` · `services/auth/routers/invitations.py:211` | contract | R3 |
| `mfa_audit_events` | sahool-platform | `services/auth/mfa_runtime.py:69` | contract | R3 |
| `mfa_recovery_codes` | sahool-platform | `services/auth/mfa_runtime.py:91` · `services/auth/mfa_runtime.py:94` · `services/auth/mfa_runtime.py:108` · `services/auth/routers/mfa.py:179` | contract | R3 |
| `users` | sahool-platform | `services/auth/main.py:996` · `services/auth/mfa_runtime.py:136` · `services/auth/mfa_runtime.py:184` · `services/auth/mfa_runtime.py:191` · `services/auth/mfa_runtime.py:211` · `services/auth/mfa_runtime.py:343` · `services/auth/routers/email_verify.py:84` · `services/auth/routers/email_verify.py:89` · `services/auth/routers/invitations.py:152` · `services/auth/routers/mfa.py:56` · `services/auth/routers/mfa.py:111` · `services/auth/routers/mfa.py:119` · `services/auth/routers/mfa.py:175` · `services/auth/routers/password_reset.py:58` · `services/auth/routers/registration.py:31` · `services/auth/routers/registration.py:93` · `services/auth/routers/tenants.py:68` · `services/auth/routers/users.py:57` · `services/auth/routers/users.py:96` | contract | R3 |

#### writer `scripts` — 5

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `canonical_projection_requests` | sahool-platform | `scripts/e2e/canonical_projection_jetstream_roundtrip.py:94` · `scripts/e2e/canonical_projection_jetstream_roundtrip.py:186` | cannot tell | R2 |
| `soil_observations` | soil-service | `scripts/soil/reconcile_historical.py:154` · `scripts/soil/reconcile_historical.py:230` | cannot tell | R2 |
| `soil_profile_projection_jobs` | soil-service | `scripts/soil/reconcile_historical.py:179` · `scripts/soil/reconcile_historical.py:306` | cannot tell | R2 |
| `soil_reconciliation_checkpoints` | soil-service | `scripts/soil/reconcile_historical.py:187` · `scripts/soil/reconcile_historical.py:314` | cannot tell | R2 |
| `soil_reconciliation_deferrals` | soil-service | `scripts/soil/reconcile_historical.py:83` · `scripts/soil/reconcile_historical.py:100` | cannot tell | R2 |

#### writer `raster-service` — 4

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `backfill_run_items` | sahool-platform | `services/raster-service/backfill_scan_worker.py:379` · `services/raster-service/backfill_scan_worker.py:406` · `services/raster-service/backfill_scan_worker.py:438` · `services/raster-service/backfill_scan_worker.py:465` · `services/raster-service/backfill_scan_worker.py:489` · `services/raster-service/backfill_scan_worker.py:612` · `services/raster-service/backfill_scan_worker.py:625` · `services/raster-service/backfill_scan_worker.py:637` · `services/raster-service/backfill_scan_worker.py:652` · `services/raster-service/db_persist.py:767` · `services/raster-service/db_persist.py:862` · `services/raster-service/db_persist.py:890` | contract | R3 |
| `backfill_runs` | sahool-platform | `services/raster-service/backfill_scan_worker.py:235` · `services/raster-service/backfill_scan_worker.py:245` · `services/raster-service/backfill_scan_worker.py:330` · `services/raster-service/backfill_scan_worker.py:337` · `services/raster-service/backfill_scan_worker.py:500` · `services/raster-service/backfill_scan_worker.py:548` · `services/raster-service/backfill_scan_worker.py:666` · `services/raster-service/db_persist.py:601` · `services/raster-service/db_persist.py:837` · `services/raster-service/db_persist.py:875` · `services/raster-service/db_persist.py:912` | contract | R3 |
| `field_geometry_versions` | field-management-service | `services/raster-service/db_persist.py:1275` | cannot tell | R5 |
| `stac_item_registry` | sahool-platform | `services/raster-service/db_persist.py:532` | contract | R3 |

#### writer `actuator-service` — 1

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `automation_rules` | sahool-platform | `services/actuator-service/actuator_runtime.py:1011` | contract | R3 |

#### writer `agents` — 1

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `notification_delivery` | sahool-platform | `agents/notification/agent.py:367` · `agents/notification/agent.py:392` | code | R1 |

#### writer `mcp_servers` — 1

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `market_sales_listings` | sahool-platform | `services/mcp_servers/market_server.py:334` | contract | R3 |

#### writer `weather-signal-engine` — 1

| table | declared owner | sites (file:line) | hint | rule |
|---|---|---|---|---|
| `weather_signals` | weather-service | `services/weather-signal-engine/src/main.py:57` · `services/weather-signal-engine/src/main.py:62` | cannot tell | R5 |

### M-03 (card: `docs/architecture/m03_command_path_adjudication.md`) — both still present

| table | contract (`db_ownership.yml`) | measured on `ec3927cef` |
|---|---|---|
| `actuator_command_outbox` | `:24` owner/writer actuator-service, reader sahool-platform | single writer `services/sahool-platform/api/phase_runtime_store.py:181` (`ON CONFLICT (idempotency_key)`), **zero readers** in `*.py/*.sql/*.yml` outside the guard and its test (`raw/15_…`); actuator-service has 0 references (`raw/19_…`, exit 1) |
| `iot_command_dispatch` | `:649` owner/writer actuator-service, reader sahool-platform | written by sahool-platform `phase_runtime_store.py:389`; claimed/finalised by sahool-platform `phase_runtime_workers.py:462-489`, which publishes `sahool.actuator.dispatch.requested` (`:506-507`) with zero consumers. **Changed since the card:** the claim now runs inside `conn.transaction()` with `claim_token`/`lease_until` (`migrations/v228_worker_claim_lease.sql:47-50`), so the card's §4 "claim without transaction" is no longer what the code does. **Unchanged:** still no `idempotency_key` column (`v109:5-23`, `raw/17_…`), actuator-service absent |

Decision options (A-1/A-2, B-1/B-2/B-3) stay as written in the card; the choice is the owner's.

## 2. CONNECTIVITY-AUDIT-20260910

Report `docs/testing/connectivity_repairs_20260910.md` (base `7407eae2`). Its own 9-file
selection now runs **86 passed** on `ec3927cef` (74 at the base; the files grew) — `raw/20_…`.
Details with file:line and proposed fixes: `connectivity_remeasure.json`.

| finding | local static | local process | local compose | staging | production | remaining (file:line) → proposed fix |
|---|---|---|---|---|---|---|
| CONN-01 tile route + tiler | holds (86 passed; `docker-compose.v9.yml:900-901,1505-1508`) | – | not measured | not measured | not measured | no live TileJSON→tile proof with real JWT/RLS/TiTiler → run v9 stack, follow `tiles[0]` as owner (200 PNG) / anonymous / other tenant (401/403) |
| CONN-03 NATS identity/ACL/TLS | **covered for `docker-compose.v9.yml`** by #1205 lineage: 9 identities `nats/nats.conf:85-252`, deny-all default `:75-78`, TLS `:65-69`, every client `tls://<own id>` (`docker-compose.v9.yml:838…3106`); 22 unit passed | 24/25 final run, 1 flaky witness (`tests_v9/test_nats_least_privilege.py:1009`), same test alone 10/10; earlier 25/25 ×2 (nats-server 2.15.0) | not measured (TLS inside Docker) | **open, separate gap** `NATS-ON-RAILWAY-STAGING-HAS-NO-AUTH-AND-A-FLOATING-TAG-01` — #1205 touched compose only, nothing configures Railway NATS | not measured; `docker-compose.production.yml` has no NATS (`raw/53_…` = 0) | contract residuals: durable create by name (`nats.conf:198-215`) · silent ACL denial of frozen Core-NATS publisher (`phase_runtime_workers.py:165-178`, GATE-01) · no `handshake_first` (`nats.conf:65-69`) · plaintext broker passwords (`docker-compose.v9.yml:458-466`); observation: monitoring `http: 8222` on all interfaces (`nats.conf:63`) → bind to 127.0.0.1, exporter via `network_mode: service:sahool-nats` |
| CONN-04 producer subject | **still present**: producer `phase_runtime_workers.py:300-301` `sahool.<type dotted>` vs consumer `shared/notification_consumers.py:33` `sahool.events.>`; ACL `nats.conf:117-125` now encodes the old subjects | – | – | not measured | not measured | **blocked by GATE-01** (`docs/architecture/gate01_policy.json:37`) → owner adjudication, then `f"sahool.events.{event_type}"` + ACL change in the same commit + producer-consumer witness |
| CONN-06 nginx deps / DNS | holds (upstream contract test in the 86; `frontend/nginx.conf:4` resolver valid=10s, `resolve` on all 11 upstreams) | – | not measured | not measured | not measured | cold start + container replacement never observed → `up` from empty volumes, `--force-recreate` each upstream, curl until 200 within resolver TTL + healthcheck |
| CONN-07 native mobile | **partly covered** by `62fc7b014` (#997): android/ + ios/ + `pubspec.lock` tracked; CI builds a debug APK (`.github/workflows/ci.yml:2194-2196`) | flutter not installed | – | no device run | no store build | CI `flutter pub get` without `--enforce-lockfile` (`ci.yml:2186`) → add the flag · no iOS build anywhere, no `Podfile.lock` → macOS job `flutter build ios --debug --no-codesign` · release unsigned (`android/app/build.gradle:38`) → operator keystore · no device evidence for push/offline/restart (`docs/audits/DEEP_REVIEW_SUPPLEMENT_20260913.md:265`) |
| CONN-08 regenerated inventories | holds (generated drift is gated; preflight on this branch below) | – | – | not measured | not measured | boundary statement by design: source wiring is not runtime certification |

Whether CI's `flutter-analyze` job is green on main or a required check was not measured
(GitHub API is out of scope for this task).

## 3. Edges baseline (A-DECLARED-EDGE-WITHOUT-A-CALL-SITE-IS-NEITHER-PROVEN-NOR-ABSENT-01)

`python3 certification/evidence/architecture_remeasure_20261017/measure_edges.py` on `ec3927cef`
(the resolver is **not modified**; another branch changes it) → `edges_baseline.json`:

| declared edges | declared operations | proven | refuted (gateway mode) | unknown |
|---|---|---|---|---|
| 725 | 886 | **333** operations (357 rows; 355 frontend call-site chains + 2 NATS subscriptions) | **170** = 99 `producer_has_no_gateway_upstream` + 71 `operation_not_routed_by_gateway` | **383** = 287 `dynamic_call_may_reach` + 86 `call_site_binding_unproven` + 9 `client_passed_as_value` + 1 `not_seen_by_axios_scanner` |

333 + 170 + 383 = 886; 0 unknown without a reason; 0 exemption problems. The registry row's
refuted 170 (99 + 71) and unknown 383 reproduce on `main` unchanged.
