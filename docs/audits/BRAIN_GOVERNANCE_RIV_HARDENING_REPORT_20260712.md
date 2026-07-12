# Brain Governance + RIV Hardening Report — 2026-07-12

## Scope
Aligned Sahool Brain, Supervisor Agent, MCP satellite tooling, Raster ownership, Vegetation interpretation, and Decision authority.

## Closed gaps

1. Supervisor Agent no longer invokes `compute_ndvi` as a computation tool.
2. Added `read_indicator_observation`, reading authoritative Raster products.
3. `compute_ndvi` remains only as a deprecated MCP compatibility alias and delegates to Raster; it performs no band math.
4. Direct Sentinel provider fetch from the brain is default-off behind `BRAIN_DIRECT_SATELLITE_FETCH_ENABLED=false`.
5. Missing or simulated Raster truth fails closed with HTTP 424.
6. Added tenant context to the authoritative read path.
7. Renamed Supervisor tool contract from `ndvi.compute` to `ndvi.read_observation`.
8. Added `shared/contracts/intelligence_governance.json`.
9. Added CI gate `scripts/ci/intelligence_governance_gate.py`.
10. CI gate blocks direct Actuator/MQTT paths from AI Agronomist, AgriAI Engine, and Supervisor Agent.
11. Updated Sahool Brain ownership map, hot state, maintenance log, and decision ledger.

## Enforced ownership

- Observed spectral truth: `raster-service`
- Vegetation interpretation: `vegetation-analysis-service`
- Decision authority and physical-effect authorization: `decision-service`
- Brain role: orchestration, explanation, evidence assembly, and decision-candidate creation only

## Verification

- `intelligence_governance_gate_ok`
- Governance + ownership tests: 7 passed
- Supervisor routing and orchestration: 22 passed
- Final focused Brain/Governance suite: 25 passed
- MCP integration tests: 16 skipped because their optional runtime/dependencies were unavailable in this environment
- `py_compile`: passed for modified runtime and CI modules

## Remaining runtime certification

- Run MCP server against a live Raster service and PostgreSQL tenant ownership data.
- Verify `X-Tenant-Id` propagation through the deployed gateway/service mesh.
- Verify Raster grid response carries scene/date/quality lineage in the deployed runtime.
- Exercise Decision-Service submission from the AI brain in staging and prove no direct physical-effect path exists.
- Keep `BRAIN_DIRECT_SATELLITE_FETCH_ENABLED=false` in production; retire the compatibility alias after consumers migrate.

---

## ملحق التكامل (أُضيف عند الدمج على الشجرة المُهبَطة — 2026-07-12)

قاعدة الحزمة `3b20e07` (10 كوميتات خلف القمّة). قرارات الدمج:

- **مصدود:** نسخة الحزمة من `phase_runtime_workers.py` — ما تزال تحمل انحدار
  `entity_id::uuid` (العمود TEXT منذ v18) — التسليم الثالث بهذا الانحدار؛ ونسخ
  actuator/decision/الجسر المائيّ (مطابقة دلاليّاً للمُهبَط، فروق تنسيق فقط).
- **عيب مُسلَّم أُصلح (P1 واجهة):** مولِّد `generate_indicator_artifacts.py` أصدر
  واجهة `RegistryIndicator` مختزلة camelCase فكسر `useIndicatorRegistry`
  (range/source_class/availability/REGISTRY_VERSION). القرار: manifest الواجهة يبقى
  للمولِّد المُثبَت `generate_indicators_frontend_manifest.py`، والمولِّد الجديد يملك
  كتالوجَي JSON فقط؛ خطوتا CI معاً.
- **ثغرة صدق أُغلقت:** بعد إزالة التقدير المضمَّن من vegetation لم يعد فحص (f) يرى
  إعادة وسم منتج مشتقّ كـ`source=real` — أُضيف فحص (g): `real` يتطلّب نوع حساب قياسيّاً
  (raster_formula/soil_sensor/weather_observation).
- **اختبارات قديمة أُعيدت كتابتها على العقود الجديدة:** `test_agri_index_explorer`
  (أداة حدوديّة fail-closed) و`tests_v9/test_vegetation_raster_ndvi` (424 بدل الارتداد
  التقديريّ) — الحزمة غيّرت الكود دون اختباراته.
- **إضافات تشغيليّة:** `SAHOOL_AGENT_TOKEN` لعامل دفتر المياه (هويّة الجسر أمام
  decision-service)؛ استثناء `.claude/` في `riv_boundary_gate`.
- **تحقّق محلّيّ:** unit 2912 ✓ · منصّة 3715 ✓ · typecheck + 1124 اختبار واجهة ✓ ·
  بوّابات RIV/الحوكمة/السجلّ ✓ · الجرد وmanifest الإصدار مُجدَّدان.
