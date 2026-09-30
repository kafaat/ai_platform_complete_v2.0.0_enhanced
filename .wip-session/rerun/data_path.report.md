STATUS: COMPLETE
BASE: bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1

## RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01
class: A-already-closed-on-main
commit: — (closed by ebcf4527, #1033)
defect measured: re-checked on bcb7f0ed. scripts/soil/reconcile_historical.py:270-302 now re-examines open rows in soil_reconciliation_deferrals (migrations/v231_soil_reconciliation_deferrals.sql) BEFORE scanning forward; skipped rows are written with a closed-vocabulary reason (_defer :78-88, _resolve_deferral :96, _open_deferrals :111). `pytest tests_v9/test_reconciliation_cursor_resumption.py tests_v9/test_reconciliation_resumption_live_pg.py` → 15 passed, 3 skipped (live-PG, no DB here).
fix: none needed. Not a GATE-01 file (scripts/soil/, not phase_runtime_*/event_bus).
falsification: n/a (existing tests owned by #1033).
brain row (proposed status + text): registry.md TABLE row (line ~5813) still reads **open** while the `##` section (line 5412-5414) reads **fixed** — the table row is stale. Proposed: flip the table row to `fixed` citing ebcf4527 (#1033), v231, tests_v9/test_reconciliation_cursor_resumption.py (15) + test_reconciliation_resumption_live_pg.py (live acceptance in the Integration Tests job). Keep `verified` off unless the live-PG job run is cited.
blocker / decision needed: none.

## SENSOR-TELEMETRY-INGEST-REACHES-NO-AGRONOMIC-CONSUMER-01
class: A-already-closed-on-main
commit: — (closed by 14c674bf, #1049)
defect measured: re-checked on bcb7f0ed. services/sahool-platform/api/routers/devices.py:177-195 forwards agronomic properties through api/soil_evidence_bridge.py:159 `forward_observation` to the owner endpoint (soil-service POST /v1/soil/observations) and returns `agronomic_path` with a named reason. `pytest tests_v9/test_sensor_telemetry_consumer_reachability.py` → 8 passed.
fix: none needed.
falsification: n/a (existing tests owned by #1049).
brain row (proposed status + text): table row (line ~5812) still reads **open** while the `##` section (5440-5442) reads **fixed (2026-09-20)** — stale table row. Proposed: `fixed` citing 14c674bf (#1049). Limits unchanged from the section: not measured live with a running soil-service; manual bridge reconcile_historical.py still exists as a registered ownership violation (item 4).
blocker / decision needed: none.

## EDGE-MODEL-DIGEST-CONTRACT-UNENFORCED-01
class: A-fixed (residual; sub-defects a/b/c named in the row were already closed by baf1a647 #1022)
commit: 10b4aaa6
defect measured: on bcb7f0ed, #1022 binds manifest <-> main.py:_MODEL_ENV (both directions, AST, sha256_env threaded to getenv). Two further declaration sites were unbound:
  (1) services/edge-inference/download_models.py:23-36 REQUIRED_MODELS re-declares filenames + os.getenv("PEST_MODEL_SHA256"/"YIELD_MODEL_SHA256"). Mutating to PEST_MODEL_SHA265 there alone → `pytest tests_v9/test_edge_model_digest_contract.py tests_v9/test_edge_model_artifact_integrity.py` = 22 passed; edge_model_contract_guard.py and production_honesty_guard.py both pass. Effect: downloader reads an unset var, refuses download (download_models.py:62), every inference 503 forever, silently.
  (2) services/edge-inference/main.py:63,72,133,134 call _model_path/_model_capability with duplicated literal (env, filename) pairs instead of _MODEL_ENV. Mutating "PEST_MODEL_PATH"→"PEST_MODEL_FILE" at :63 alone → 22 passed + guard passes. Effect: gate (_require_approved_model :111-118) hashes the file at PEST_MODEL_PATH while the detector loads the default /models file — integrity verified on bytes not used.
fix: tests only (main.py not refactored — edge readiness belongs to another agent). tests_v9/test_edge_model_digest_contract.py: `_downloader_digest_envs` + `test_the_downloader_reads_the_declared_digest_names_for_the_declared_models` (exact dict equality with manifest filename→sha256_env); `_literal_calls` + `test_every_literal_model_call_in_main_names_the_path_the_gate_hashes` (every 2-literal _model_path/_model_capability matches _MODEL_ENV, each covers every model, and _require_approved_model gates exactly the model set). Idea of binding the downloader and literal call sites came from salvage 3116b861; code re-written and extended (per-model coverage + gate-set checks are new).
falsification: scratchpad/falsify_edge.sh — M1 downloader SHA env rename → red; M2 main.py:63 path env → red; M3 main.py:134 readiness env swap → red; M4 remove yield gate call :298 → red; M5 extra model in downloader → red. Restored → 6/6 green.
brain row (proposed status + text): **fixed** — «#1022 ربط البيان بـ`_MODEL_ENV`؛ و10b4aaa6 ربط الموضعين الباقيين: `download_models.py:REQUIRED_MODELS` (اسمُ متغيّر البصمة كان نثراً — إعادةُ تسميته وحدَه أبقت ٢٢ شاهداً والحارسَين أخضر) والحروفَ المكرَّرة في `main.py:63/72/133/134` (البوّابةُ تُجزّئ ملفّاً والمُحمِّلُ يقرأ آخر). ٥/٥ طفرات. حدّ: شواهدُ ساكنة لا إعادةُ تشكيل — التكرارُ في main.py باقٍ مربوطاً لا مُزالاً؛ ولا وزنَ معتمدٌ في الشجرة.» Sources: tests_v9/test_edge_model_digest_contract.py, services/edge-inference/download_models.py:23, services/edge-inference/main.py:63.
blocker / decision needed: none. Optional follow-up for the edge-readiness owner: derive the literals in main.py from _MODEL_ENV to remove the duplication at source.

## TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01
class: A-fixed (non-wind fields only; wind untouched per owner deferral)
commit: 7c0bb88b + a9f813d9 (a9f813d9 removes a `fake_conn` stub the full unit run flagged under fake_connection_debt_guard; the test now uses contextlib.nullcontext — no connection at all — instead of growing the debt baseline)
defect measured: scratchpad/measure_typed.py on bcb7f0ed (no network, _fetch_json stubbed):
  `_build_daily` without temperature_2m_* / weather_code → `0 0 0`; FieldAlertContext(tmax/tmin from it) → evaluate_field_alerts → `[('frost_risk', 'critical')]`;
  `fetch_current` without temperature_2m/relative_humidity_2m/cloud_cover/weather_code → `0 0 0 0` and describe_weather_ar → «صافٍ».
  Source: services/sahool-platform/api/connectors/openmeteo.py:207-229 (types), :273-279 (_build_daily), :334-342 and :394-402 (fetch_current / fetch_current_batch).
fix:
  - openmeteo.py: CurrentWeather.temperature_c/humidity_pct/cloud_cover_pct → float|None, weather_code → int|None; DailyForecast.temp_max_c/temp_min_c → float|None, weather_code → int|None; all three construction sites stop defaulting to 0; describe_weather_ar(None) → «غير معروف»; spraying_condition_score (zero callers) no longer TypeErrors on None rain/temp and returns `unknown` instead of permission. Comment above CurrentWeather rewritten with the measured effects.
  - routers/etc_dual.py `_resolve_weather`: absent temp_max_c/temp_min_c/humidity_pct → 503 naming each (same pattern as the existing solar-radiation guard).
  - routers/fields.py `field_disease_risk`: absent temperature/humidity → 503 (was: 200 scored from 0°C/0%, and round(None) → 500 after the type change).
  - season_simulation.py DayWeather.t_min_c/t_max_c → float|None (engine already returns None per missing day and simulate_season already declares missing GDD/ET0 days — measured weather-service/et0.py:246-275, weather_runtime.py:859-913).
  - Consumers already None-safe and left unchanged: alert_rules FieldAlertContext (tmax/tmin/temp/humidity Optional, rules skip None), recommendations_hub, fields.py:2875 / season_workspace.py:387 (ctx Optional), field_ai_context.py:574, weather_automation.py:257 (JSON passthrough).
  - Wind NOT touched: wind_speed_ms / wind_max_ms stay `float` with 0 coercion (PLATFORM-CONNECTOR-STILL-COERCES-AN-ABSENT-WIND-TO-ZERO-01); etc_dual guard excludes wind.
  - docs/architecture/platform_extraction_map.json: 28 `line` anchors updated (+8 fields.py, +18 etc_dual.py) — hand-maintained policy doc per CLAUDE.md, not a generated artifact; only `line` values changed, JSON round-trip byte-identical; platform_route_ownership_guard.py passes.
  Salvage 3116b861 used as lead for the shape of the etc_dual/disease guards; its wind changes, weather-service changes, tile `or`→nvl change and seasons rain change were NOT taken (out of scope / other agents' areas).
tests: services/sahool-platform/tests/test_absent_reading_is_not_zero_at_the_edge.py (6 new) + tests_v9/test_etc_dual_weather.py (+2). Each absence case is paired with an observed-zero case that must stay zero.
falsification: scratchpad/falsify_typed.sh (reverts taken from bcb7f0ed, re-run after a9f813d9) — F1 restore the edge `, 0` defaults → 7 red; F2 revert etc_dual guard → 1 red; F3 revert disease guard → 1 red; F4 revert spray body → 1 red. Restored → 12/12 green.
brain row (proposed status + text): **fixed (non-wind)** — «أُغلِق الباقي عدا الريح في 7c0bb88b: الحرارتان والرطوبةُ والسُّحُبُ ورمزُ الطقس (آنيّاً ويوميّاً) `| None`، والمواضعُ الثلاثة كفّت عن الصفر. الأثرُ المقيسُ قبله: غيابُ الصغرى ⇒ `frost_risk` حرج؛ غيابُ الرمز ⇒ «صافٍ». المستهلكون: etc_dual وdisease-risk ⇒ ٥٠٣ يُسمّي الناقص؛ الباقون كانوا يقبلون `None`. `fao56.WeatherDay` بقي `float` لأنّ كلَّ مسارٍ إليه صار يفشل مغلقاً قبله. **الريحُ باقيةٌ مفتوحةً** في PLATFORM-CONNECTOR-STILL-COERCES-AN-ABSENT-WIND-TO-ZERO-01.» Sources: services/sahool-platform/api/connectors/openmeteo.py:196-230, routers/etc_dual.py:211-229, routers/fields.py:2641-2648, services/sahool-platform/tests/test_absent_reading_is_not_zero_at_the_edge.py.
blocker / decision needed: none for this scope. Residual findings NOT fixed (outside the row's named fields): (a) routers/seasons.py:243 `rain_mm=d.precipitation_mm or 0.0` still re-coerces an absent historical rain to 0 in the season simulation (DayWeather.rain_mm: float = 0.0); (b) openmeteo.py fetch_weather_tile_data `(c.get(k) if use_current else None) or hv(k)` treats an observed 0 as absent (reverse class). Both worth their own rows.
limits: no live Open-Meteo call; frontend rendering of `null` temperature/code not checked.

## CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01
class: B-GATE01 (durable part) + D-live (the historical incident); code area also held by a concurrent agent
commit: —
defect measured: on bcb7f0ed, services/raster-service/raster_cdse_tile_runtime.py:431-451 already logs the full request for each empty scene (window, bbox, MAX_CLOUD_PCT, mosaicking, byte count, polygon_mask) at INFO, then deletes the bytes (`_unlink_best_effort`, :451) and returns None. `grep -rln "cdse_empty|empty_scene|scene_diagnostic" migrations/ services/raster-service` → no table stores failed-scene diagnostics. So new occurrences are attributable only while logs are retained; nothing is durable and the original incident stays unattributable.
fix: none. Reasons:
  (1) The brief lists `services/raster-service` as a concurrently-owned area (do not touch) — every remaining code change for this gap lives there.
  (2) Durable attribution needs a place to store per-scene diagnostics. Every candidate is a new table ⇒ a new migration ⇒ `migrations/MANIFEST.txt`, which is GATE-01 frozen (docs/architecture/gate01_policy.json `frozen_paths`).
  (3) The already-open incident can only be attributed by re-querying CDSE (Catalog API for that bbox/window) — a live operation.
  The brief's caution (do not touch field.created imagery invalidation) was respected: nothing read or changed there.
brain row (proposed status + text): stays **open** — «مقيسٌ على bcb7f0ed: السطرُ يحمل الطلبَ كاملاً (raster_cdse_tile_runtime.py:437-450) والبايتاتُ تُحذَف (:451)، ولا جدولَ يحفظ تشخيص المشهد الفارغ. الباقي مُحتجَز: (أ) الإدامةُ تحتاج جدولاً ⇒ هجرةً ⇒ MANIFEST المجمّد (GATE-01)؛ (ب) الواقعةُ المفتوحة لا تُنسَب إلّا باستعلام CDSE Catalog حيّ لنافذتها.»
blocker / decision needed: GATE-01 unfreeze (or owner approval) for a migration adding e.g. `raster_empty_scene_diagnostics(field_id, window_from, window_to, bbox, max_cloud_pct, mosaicking, bytes, polygon_mask, observed_at)` plus a writer in raster_cdse_tile_runtime.py next to the INFO line; and a live CDSE Catalog query for the original incident window. A cheaper non-migration alternative is a structured JSON log event with a stable name (log-retention bound) — owner of services/raster-service to decide.

## CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01
class: B-GATE01
commit: —
defect measured: on bcb7f0ed, `grep -l -i correlation migrations/*.sql` → only v148_field_evidence_snapshots, v17_workflow_state_full, v195/v205 irrigation reservation; none mention decision_record / execution_ledger / approvals. Tables defined at migrations/v78_decision_record.sql:21 and migrations/v68_execution_ledger.sql:13; zero ALTER adds a correlation column. Writers: services/decision-service/persistence.py, services/sahool-platform/api/routers/decision_record.py, routers/decision_dispatch.py.
fix: none. A correlation column on three tables requires a new migration, and registering it requires migrations/MANIFEST.txt (GATE-01 frozen, docs/architecture/gate01_policy.json) — plus db_ownership.yml review (also frozen). Writers can't carry a column that does not exist; stuffing the id into existing JSON payloads would be a second, divergent convention (design decision, not a fix).
brain row (proposed status + text): stays **open** — «أُعيد القياسُ ساكناً على bcb7f0ed: صفرُ هجرةٍ تضيف `correlation` إلى الجداول الثلاثة (v78:21 · v68:13)؛ الإصلاحُ هجرةٌ جديدة ⇒ MANIFEST المجمّد (GATE-01) — محتجَزٌ لا منسيّ.»
blocker / decision needed: GATE-01 unfreeze for one migration: `ALTER TABLE decision_record/execution_ledger/approvals ADD COLUMN IF NOT EXISTS correlation_id text` (+ index), then thread the request's correlation id through decision-service persistence.py and the two platform routers, with a live-PG test in the Integration Tests job. Owner to confirm the id's source (X-Correlation-ID header vs. decision_id as root).

## REPORT2-C03-DEDUP-FOLLOWS-STREAM-MESSAGE-NOT-EVENT-ID-01
class: C-owner
commit: —
defect measured: on bcb7f0ed, agents/notification/agent.py:258-264 `_delivery_key` = `_delivery_id or event_id or alert_key` (+ user_id); `_delivery_id` is set at :483 as `f"{metadata.stream}:{metadata.sequence.stream}"`. So redelivery of the same JetStream message dedups; a re-publish of the same logical event in a new message gets a new key. Row text is accurate; line moved 247→258.
fix: none — which idempotency is wanted (redelivery-only, as now, vs. logical-event re-publish) is a product/scope decision, and the second requires a trustworthy producer event identity. Also a HELD path (agents/**, notification agent redeploy on Railway currently failing).
brain row (proposed status + text): stays **open — قرارُ نطاق**; update source anchor to `agents/notification/agent.py:258` (key) and `:483` (`_delivery_id` from stream:sequence). Measured unchanged on bcb7f0ed.
blocker / decision needed: owner chooses redelivery-only (then close as "by design" with the existing test) or event-level idempotency (then: producer-guaranteed event_id, key = tenant+user+channel+event_id preferred over `_delivery_id`, two separate tests: redelivery and re-publish).

## REPORT2-C04-QUEUED-PUSH-RECEIPTS-HAVE-NO-CONSUMER-01
class: C-owner
commit: —
defect measured: on bcb7f0ed, `record_only` path (agents/notification/agent.py:188-195 decision, :428 branch) writes `notification_delivery` rows with status 'queued' via `_deliver_channel` (:281-285) and acks. Readers of `notification_delivery` in the tree: the agent itself (:291 SELECT … FOR UPDATE for its own key) and services/sahool-platform/api/routers/notifications.py:179-220 (`upsert_notification_delivery`, a writer/upsert for receipts, not a drainer). No component selects queued rows to send/expire them. (guardrails-engine only has a literal `notification_delivery: "not_configured"` field, unrelated.) Row anchor moved 315→428.
fix: none — drain policy (resend on FCM enable? max age? cancel?) is a product decision; plus HELD path (agents/**).
brain row (proposed status + text): stays **open — قرارُ سياسة**; anchors `agents/notification/agent.py:428` (record_only) and `:281` (INSERT 'queued'). Measured unchanged on bcb7f0ed.
blocker / decision needed: owner policy for queued receipts (resend window / TTL / cancel), then a test: flag off → queued → flag on → exactly one delivery or documented expiry.

## IRRIGATION-WATER-SUITABILITY
class: C-owner (data/product authority), with a B component for any new storage
commit: —
defect measured (bcb7f0ed; corrected after an initial wrong grep — I first wrote "EC only", which is false):
  - H5.1 is built and closed in its own row `H5.1-BINDING-INTEGRITY` (**fixed**, 3033765; tests_v9/test_h51_field_source_binding_pg.py).
  - Pure classifiers exist: api/salinity_management.py (classify_soil_salinity on ECe :34, classify_water_salinity, sodium_hazard, leaching_requirement) and the water-sample analysis endpoint routers/irrigation.py:401 (SAR/RSC + FAO-29/USDA/USSL classes, informational).
  - A multi-hazard reconciliation kernel exists: api/canonical_salinity_state.py:126 `build_canonical_salinity_state` (water SAR/Cl/B, drainage, crop stage, CropSalinityTolerance Cl/B thresholds, freshness, fail-closed) persisted via persisted_canonical_repositories.py:216.
  - But `grep "CropSalinityTolerance(|build_canonical_salinity_state("` outside tests → **zero production callers**: nothing supplies crop tolerance thresholds, and there is no irrigation-method input and no ECw→ECe conversion anywhere (salinity_management.py works on ECe directly). So the engine is a kernel without an authoritative data feed — exactly the row's BLOCKED_DESIGN_DATA_AUTHORITY.
fix: none. Feeding the kernel requires an accepted threshold authority (FAO-29 / USDA-60 crop tolerance tables for EC/Cl/B, ECw→ECe factor, leaching policy, method-specific foliar-injury rules) and Yemeni calibration (H5.4); the row forbids shipping "local truth" from international references without calibration. Persisting a tolerance catalogue would also need a migration (MANIFEST frozen, GATE-01).
brain row (proposed status + text): stays **open — BLOCKED_DESIGN_DATA_AUTHORITY** — «أُعيد القياس على bcb7f0ed: H5.1 مُغلَقٌ في صفّه (3033765)؛ ونواةُ التوفيق متعدّدة الأخطار موجودة (`canonical_salinity_state.py:126`: SAR/Cl/B/صرف/طور/نضارة، تفشل مغلقة) **بلا مستدعٍ إنتاجيٍّ واحد** — لا مصدرَ لعتبات تحمّل المحصول، ولا مُدخَلَ لطريقة الريّ، ولا تحويلَ ECw→ECe. المانعُ سلطةُ بياناتٍ لا شيفرة.»
blocker / decision needed: owner/agronomy authority to (1) adopt tolerance tables + ECw→ECe + leaching policy with citations, (2) define where tolerance/method data live (catalogue file vs. table — the latter needs GATE-01), (3) Yemeni calibration. Then wire `build_canonical_salinity_state` from the irrigation path as informational first.

## CAP-INT-004-INTEGRATION
class: D-live (INT-004B/C need physical controllers/implements) + C-owner (which controller/transport to target)
commit: —
defect measured: on bcb7f0ed, docs/capability-registry/domains/precision.yaml:336-351 still declares device_delivery_verified / machine_consumption_verified / physical_execution_verified / runtime_verified / production_certified = false, with "INT-004B device transport (CAN/ISOBUS upload to a controller) — not implemented" and "INT-004C machine-consumption / execution confirmation — not implemented". services/sahool-platform/api/machinery_export.py:9-11 states the boundary (produces + persists the TaskData ZIP; does not connect to a controller or transmit over CAN/ISOBUS). No CAN/ISOBUS transport code in services/ (grep isobus/can_bus/j1939 → only ISOXML generators and the export adapter). INT-004A remains closed as recorded.
fix: none. INT-004B is a device-side transport (ISOBUS TC upload / vendor cloud API / USB hand-off) whose choice depends on the target controllers — an owner decision — and whose verification needs real hardware or a vendor sandbox. INT-004C needs a consumption/execution receipt from the machine (e.g. ISOXML TaskData with TimeLog back from the controller) — only producible by a real implement. Writing either without hardware would be a simulator claiming delivery.
brain row (proposed status + text): unchanged **open** — «أُعيد القياس على bcb7f0ed: INT-004A مُغلَق؛ وأعلامُ precision.yaml:344-348 كلُّها false، ولا نقلَ CAN/ISOBUS في الشجرة. INT-004B/C يحتاجان عتاداً حيّاً وقرارَ المالك في المتحكّم المستهدَف.»
blocker / decision needed: owner picks the first target controller/transport (e.g. a specific ISOBUS TC or vendor API) and supplies hardware or a vendor sandbox; then INT-004B = upload + ack, INT-004C = ingest returned TimeLog as execution evidence.

## CONNECTIVITY-AUDIT-20260910
class: mixed — CONN-04 B-GATE01 · CONN-03 C-owner + D-live · CONN-07 D-live · live Compose/DNS D-live (CONN-01/02/05/06/08 were repaired in the audit PR and stay as recorded)
commit: —
defect measured (bcb7f0ed):
  - CONN-04 = `NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE` in docs/architecture/nats_subject_ownership_contract.json: services/sahool-platform/api/phase_runtime_workers.py:300-302 publishes `f"sahool.{event_type.replace('_', '.')}"` (e.g. sahool.field.updated) while the canonical consumer agents/notification/agent.py subscribes `sahool.events.>`. phase_runtime_workers.py is in gate01_policy.json `frozen_paths` → cannot be edited.
  - CONN-03: the same contract's `NATS-AUTHORIZATION-NOT-ENFORCED` is OPEN — shared broker credentials exist (nats.conf authorization via $NATS_USER/$NATS_PASSWORD); per-service identities/ACLs and TLS absent. Closing needs a coordinated producer/consumer rollout + live negative/positive probes — the brief forbids NATS operations and credential handling.
  - CONN-07: native Android/iOS projects/lockfiles/build evidence still outside the tree scope of this audit (no native build can be produced or verified here).
  - Live Compose cold start / container replacement / DNS recovery: unmeasured by construction (no live environment).
fix: none in code. Proposed patch for CONN-04 (for whoever holds GATE-01 adjudication), not applied:
```diff
--- a/services/sahool-platform/api/phase_runtime_workers.py
+++ b/services/sahool-platform/api/phase_runtime_workers.py
@@ (run_plugin_runtime_once, ~:300)
-                await _publish_nats(
-                    f"sahool.{str(row['event_type']).replace('_', '.')}",
-                    {"event_id": row["event_id"], "payload": row["payload"]},
-                )
+                # CONN-04: الموضوعُ القانونيّ `sahool.events.<event_type>` الذي يستهلكه
+                # وكيلُ الإشعارات (`sahool.events.>`)؛ النشرُ المزدوج نافذةُ توافقٍ مؤقّتة
+                # حتّى يُثبَت ألّا مستهلكَ خارجيّاً للصيغة القديمة.
+                for subject in (
+                    f"sahool.events.{row['event_type']}",
+                    f"sahool.{str(row['event_type']).replace('_', '.')}",  # legacy — remove after window
+                ):
+                    await _publish_nats(
+                        subject, {"event_id": row["event_id"], "payload": row["payload"]}
+                    )
```
  plus: update nats_subject_ownership_contract.json (gap → CLOSED_IN_CODE with the window), a producer↔consumer subject test that imports both the worker's subject builder and the agent's subscription pattern, and a note that the notification agent dedups by `_delivery_id` (REPORT2-C03) so the dual publish would NOT double-notify only if the legacy subject has no subscriber — verify first. FEATURE_NATS_PUBLISHERS stays false; nothing here enables publishing.
brain row (proposed status + text): stays **OPEN** — «أُعيد القياس على bcb7f0ed: CONN-04 هو `NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE` (phase_runtime_workers.py:300-302 ينشر `sahool.<type.dotted>` ووكيلُ الإشعارات يشترك `sahool.events.>`) في ملفٍّ مجمّد GATE-01 — رقعةٌ مقترحة في تقرير الوكيل؛ CONN-03 يحتاج هويّاتٍ/ACL/TLS لكلّ خدمة ومِسباراتٍ حيّة؛ CONN-07 والتحقّقُ الحيّ من Compose/DNS يحتاجان بيئةً حيّة.»
blocker / decision needed: GATE-01 adjudication for phase_runtime_workers.py (CONN-04); owner-led NATS identity/TLS rollout with live probes (CONN-03); a native mobile build environment (CONN-07); a live Compose stack for cold-start/DNS recovery.

## PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01
class: A-fixed (structural half of "unreachable") + D-live (what remains is real evidence, not code)
commit: 82dca782
defect measured: scratchpad/best_world.py on bcb7f0ed — builds a perfect `runs` payload (every workflow ran on the SHA, every job/step `success`, including workflow_dispatch-only ones) from `guard_catalogue.discover_invocation_sites()` and feeds scripts/ci/collect_guard_surface_evidence.py::evaluate. Output: `guards_declared: 277` vs catalogue `discover_invocations` = 276; `unproven in best world: 1 — scripts/ci/gap_registry_measure.py ['non_blocking_by_declaration']`. Root cause: evaluate() (collect_guard_surface_evidence.py:188-230 before the fix) demanded every invoked guard, while judge_site():147-149 marks every continue-on-error site `non_blocking_by_declaration`, a status no run can change. gap_registry_measure.py's only site is continue-on-error (gap-registry-report, report-only by #1028), so `guards_unproven` could never be empty → main() exits 1 → GUARDS never emitted → production_certified unreachable even with perfect evidence. This also contradicted the declared producer contract (docs/architecture/certification_evidence_producers.json "GUARDS.witness": "the blocking list derived from guard_catalogue").
fix: evaluate() now demands exactly the catalogue's blocking set (guard with ≥1 site without continue-on-error — the same predicate as guard_catalogue.discover_invocations:141-149). Guards blocking nowhere are listed in the evidence as `non_blocking_excluded`, printed in the log, and not counted in guards_declared. A guard with any blocking site stays demanded, and its continue-on-error sites still never prove it. No verdict, threshold, waiver or certification field was touched; production_certified stays false. Idea came from salvage 3116b861 (lead); re-measured independently, implemented differently (predicate on sites instead of on judged statuses, so self-witnessing precedence is unchanged), and the registered mutation expect-test was preserved rather than left to go stale.
tests (tests_v9/test_collect_guard_surface_evidence.py, 25 pass): `test_continue_on_error_is_not_a_blocking_run` previously PINNED the bug (asserted the guard sits in guards_unproven); corrected and extended with the mixed-site case so it still kills its registered mutation (`if site["continue_on_error"]:` → `if False:`). New: `test_one_blocking_site_keeps_the_guard_demanded`, `test_the_demanded_set_is_the_catalogues_blocking_set` (real tree), `test_the_legitimate_path_is_reachable_in_the_best_possible_world` (real tree).
falsification: scratchpad/falsify_cert.sh — C1 revert script → 4 red; C2 exclusion leaks to every guard → 18 red; C3 exclusion leaks to mixed guards → 2 red; restored → 25/25. `guard_mutation_guard.py --run --only scripts/ci/collect_guard_surface_evidence.py` → 10/10 killed; static guard_mutation_guard ok.
does it make certification easier without evidence? No: the only guard un-demanded is one that cannot block by declaration (its run proves nothing about blocking); every blocking guard still needs a `success` step on the same SHA, and all negative vectors (skipped/missing/renamed/matrix-leg/failed) still fail.
brain row (proposed status + text): stays **open**, narrowed — «تحديث: النصفُ «تعذّرُ النجاح» كان ما يزال **بنيويّاً**: بمحاكاة أفضل عالَمٍ ممكن على bcb7f0ed يُطالِب الشاهدُ بـ٢٧٧ والكتالوجُ يعدّ ٢٧٦، ويبقى `gap_registry_measure.py` (continue-on-error في كلّ مواضعه) غيرَ مُثبَتٍ أبداً ⇒ لا يُنبعَث GUARDS ولو صدق كلُّ شيء. أُصلح في 82dca782: المُطالَبُ هو الحاجبُ بمحمول الكتالوج نفسِه، وغيرُ الحاجب يُنشَر `non_blocking_excluded`. والباقي الآن **دليلٌ حيٌّ لا شيفرة**: ٥ حرّاسٍ حاجبةٍ لا تُستدعى إلّا في workflows يدويّة (path3-runtime-verification · runtime-verification-promotion: path3_runtime_activation · prepare_attested_runtime_images · provenance_receipt · runtime_replay_guard · runtime_verification_apply) و٢ عبر workflow_run (certify-run: certify_artifact_contract · run_outcome_guard)، زائداً P-CERT-4 غيرِ القابل للإعفاء (دليلُ تزويدٍ من النشر).» Sources: scripts/ci/collect_guard_surface_evidence.py (evaluate), tests_v9/test_collect_guard_surface_evidence.py, scripts/ci/guard_catalogue.py:141.
blocker / decision needed (D): run the Path-3 runtime workflows (workflow_dispatch) and certify-run on the release SHA against a live runtime, and produce P-CERT-4 provisioning evidence at deployment. Not something code can supply; never set any certification field by hand.
note on scope: collect_guard_surface_evidence.py is under scripts/ci; I treated it as this gap's own evidence producer (the row names it), not as shared guard-framework internals — guard_catalogue.py, preflight.sh and the mutation registry were not modified. Flag for the coordinator in case another agent owns it.

## HELD PATHS
none — no file under agents/, shared/ or migrations/ was changed in any commit.

## COMMITS (worktree branch `worktree-agent-ab89aa24bc3a3f618`, base bcb7f0ed, not pushed)
- 10b4aaa6 EDGE-MODEL-DIGEST-CONTRACT-UNENFORCED-01 (tests only)
- 7c0bb88b TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 (platform code + tests + platform_extraction_map.json line anchors)
- a9f813d9 TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 (test: no fake connection)
- 82dca782 PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01 (scripts/ci/collect_guard_surface_evidence.py + tests)

## GENERATED ARTIFACTS TO REGENERATE (not regenerated here, per brief)
Likely stale because they embed line numbers / hashes / test inventories of files changed above:
- docs/architecture/generated/platform_route_budget_inventory.json and platform_route_ownership_inventory.json (fields.py +8, etc_dual.py +18 line shifts)
- docs/capability-registry/generated/** (capability_registry.json, mapping/capability_mapping.json, mapping/unmapped_artifacts.json — new test file, changed sources)
- docs/runbooks/GUARD_CATALOGUE.md (collect_guard_surface_evidence.py changed; first docstring line unchanged, so possibly identical)
- api_versioning_inventory.csv + api_versioning_inventory.generated.json (measured: 28 route line shifts; the unit run rewrote them, I restored them uncommitted) — makes tests_v9/test_api_versioning_policy_guard.py::test_api_versioning_policy_guard_inventory_is_current fail until regenerated
- execution-audit/generated/duplicate_definitions.json (measured: only `python_files_parsed` 1917→1918, from the new test file) — makes test_generated_artifact_contract.py[duplicate_definition_guard] fail until regenerated
- release bundle (hashes everything) — build last.
Commands (coordinator, clean tree, after integration): `python scripts/ci/verify_all_generated.py --fix` then `python scripts/release/build_release_bundle.py`.
Hand-maintained (NOT generated) file updated in 7c0bb88b: docs/architecture/platform_extraction_map.json — 28 `line` values only.

## TESTS RUN
- tests_v9/test_edge_model_digest_contract.py: 6 passed (5/5 mutations red, scratchpad/falsify_edge.sh)
- tests_v9/test_etc_dual_weather.py + services/sahool-platform/tests/test_absent_reading_is_not_zero_at_the_edge.py: 12 passed (4 revert scenarios red, scratchpad/falsify_typed.sh)
- tests_v9/test_collect_guard_surface_evidence.py: 25 passed (3 revert scenarios red, scratchpad/falsify_cert.sh); guard_mutation_guard --run for collect_guard_surface_evidence.py 10/10, openmeteo.py 3/3, routers/fields.py 1/1 killed; static guard_mutation_guard ok
- services/sahool-platform tests (CI invocation `PYTHONPATH=. pytest tests`, -n 8): 4445 passed
- tests_v9 -m unit subset weather/etc/season/alert/route: 724 passed, 5 skipped; subset certif/evidence/catalogue: 211 passed, 5 skipped
- full `pytest -m unit` (serial, before a9f813d9): 7921 passed, 17 skipped, 5 failed:
  * test_fake_connection_debt_guard (2) — caused by my test's fake_conn → FIXED in a9f813d9 (16/16 pass after)
  * test_api_versioning_policy_guard_inventory_is_current — stale generated inventory from my line shifts (regenerate)
  * test_generated_artifact_contract[duplicate_definition_guard] — stale generated count from my new test file (regenerate)
  * test_dockerfile_pip_mirror_guard (found 0 Dockerfiles) — environmental, unrelated (no Dockerfile touched)
- reconciliation/sensor tests on main: 15 passed + 3 skipped (live PG), 8 passed
- bash scripts/ci/preflight.sh --fast: 0 failures, 0 skipped (after final commit); brain_commit_claim_guard PASS (6 claims)
- ruff check + ruff format --check clean on every changed file; platform_route_ownership_guard, platform_route_budget_guard (629/629, unchanged), ownership_extraction_alignment_guard pass.
- NOT run: full preflight (suites+sweep), integration/live-PG, bandit/pip-audit (no dependency changes).
