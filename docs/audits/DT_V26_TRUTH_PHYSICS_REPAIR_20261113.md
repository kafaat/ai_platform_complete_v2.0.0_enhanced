# SAHOOL v26 — Digital Twin Truth, Physics and Decision Boundary Repair
**Reviewed:** 2026-11-13. **Baseline:** `main@fe67d0f8f6eb7c22ea8e8f3cb43da84dc1613fe2`.

## Scope and authority

This patch changes **derived/read-only twins and previews**, not the authoritative
`canonical_field_state.v1` schema, `decision-service` cutover policy, database writers,
actuator commands, or existing migrations. It does not assert that a field-validated
crop/yield digital twin is already operational.

### Implemented

| Gate | Repair | Proof |
|---|---|---|
| DT-01 | NDVI-specific timestamp, absent/future NDVI => stale; newer EVI cannot mask old NDVI. Nonfinite values ignored. | `test_field_twin.py`, `test_field_twin_endpoint.py` |
| DT-02 | Field Twin publishes the active-season identifier/crops/cultivar separately from legacy `fields.crop`, with explicit derived-view authority. | `test_field_twin_endpoint.py` |
| DT-03 | Instantaneous net irrigation screening uses `Dr` and `TAW` in mm, and `RAW` to classify stress; without source state, all post-irrigation percentages remain `None`. | `test_v26_digital_twin_regressions.py` |
| DT-04 | Full `canonical_field_state` proposal eligibility blocks the twin even if products are present but owner quality is insufficient. | `test_v26_digital_twin_regressions.py` |
| DT-05 | Crop Twin distinguishes missing/nonfinite GDD from **observed 0 GDD**, and withholds stage, growth progress and cumulative nutrient uptake when no trustworthy GDD exists. | `test_v26_digital_twin_regressions.py` |
| DT-06 | Decision candidates reject NaN/Inf/negative/bool GDD even with lineage IDs; client spectral input is always flagged unverified. The effective server NDVI, rather than client NDVI, determines the Kc label. | `test_crop_twin_compose_endpoint.py` |
| DT-07 | Phase-6 farm snapshot is clearly client preview: empty or unclassified fields have **no health score**, and ID binds **all** inputs, not just farm+day. | `shared/precision_agriculture/test_phase6_intelligence.py` |
| DT-08 | Water Twin resolves active-season crop and sowing date before legacy field metadata, and refuses to infer a single crop for mixed/invalid active crop lists. | `test_v26_water_twin_season_context.py` |
| DT-09 | Crop Propagation front-end passes field/season identity, keys its cache by both IDs, and does not treat a planned-only season as active in MapHub. | TypeScript/frontend gates |

### Scientific notes

* For an **instantaneous** screen of *net infiltrated* irrigation, `Dr_after = max(0, Dr_before - I_net)` in **mm**; the percentage of plant-available water remaining is `100 × (TAW - Dr_after) / TAW`, provided the inputs are present and valid. This does **not** simulate evapotranspiration, runoff, capillary rise, or deep percolation, and it is **not** a physical command.
* For a temporal simulation, retain the existing full `api/water_twin.py` daily budget and weather-service ET0. Do not reimplement FAO physics in a second decision engine.
* Crop phenology GDD comes only from `weather-service`. An unavailable GDD is not 0, even when the presentation model must continue to provide an explanatory preview.
* The Phase-6 farm snapshot is **not** an authoritative verification of farm health, whether or not its numerical preview score is defined.

## External research and code patterns (not copied)

- FAO-56, Chapter 8, root-zone water balance and `Dr`: https://www.fao.org/4/X0490E/x0490e0e.htm
- PCSE / WOFOST state/rate/parameter separation and agronomic events: https://github.com/ajwdewit/pcse
- AquaCrop-OSPy crop–soil–water simulation and validation: https://github.com/aquacropos/aquacrop
- farmOS operational assets, logs and observations: https://github.com/farmOS/farmOS
- OGC SensorThings API, observation event time, result time, quality: https://www.ogc.org/standards/sensorthings/
- OpenAgri supervised irrigation / LoRaWAN (GitLab): https://gitlab.pcss.pl/dsobczak/OpenAgri-SmartIrrigationController/-/tree/main
- Agriculture Island sensor/equipment workflows (Gitee): https://gitee.com/xupig/nongyedao-yuyue
- ZhiXie (GitCode) MQTT/offline control patterns: https://gitcode.com/d4v41/ZhiXie
- Literature review on multi-asset interoperability and field validation: https://doi.org/10.1016/j.atech.2026.102283
- farmOS community discussion on sensor/log linkage: https://farmos.discourse.group/t/consolidated-sensor-event/608

These references are design inputs, not endorsed software dependencies. Check
licenses and calibrate against Yemen/Al Jawf field evidence before field adoption.

## Not closed in this patch

1. Full AC-1 point-in-time snapshot and season-centric backfill for **every** crop twin path.
2. Persistent twin-simulation run identity and comparison against independently measured harvest.
3. Field-validated soil/salinity/crop parameter calibration, WOFOST/PCSE and AquaCrop ensembles.
4. End-to-end device telemetry, authorization, actuator acknowledgements and execution receipts.
5. Production deployment settings and real farm-machine/sensor runtime checks.

**Release boundary:** review-only PR. Test CI, temporal and tenant-isolation cases,
generated artifacts/release checksums, and run a controlled PG + UI/mobile end-to-end
before promotion or merge. No automatic actuator permissions are added.
