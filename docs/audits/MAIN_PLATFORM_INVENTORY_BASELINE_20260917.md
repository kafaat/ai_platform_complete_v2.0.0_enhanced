# Main Platform Inventory Baseline — 2026-09-17

**Source commit:** `d3734df17c635250139587f35af8dcb24358a6f2` (`main` at inventory start)

## Purpose

This is an **inventory baseline, not a certification and not a verdict**. It precedes diagnostic, operational, analytical, integration, and live tests. Its job is to define what exists, what is declared, how components are expected to connect, and which edges remain unresolved.

The generated platform catalogue remains a source, not unquestioned truth. `wired` and `tested` are static-derived attributes; configured/activated state requires runtime evidence.

## Component surface

`component_inventory.generated.csv` contains 36 component records at the source commit. The principal domains are:

- execution: actuator-service
- simulation/experimental: agriai-engine
- agents: ai_agronomist, supervisor-agent
- identity: auth
- decision governance: decision-service, guardrails-engine, model-registry-adapter
- edge: edge-inference
- ERP projection: erp-bridge
- fields: field-management-service, field-segmentation
- user interfaces: frontend, mobile
- GIS publication: gis-workflow-service
- indicators: indicators-service
- knowledge/RAG: knowledge-graph, local-ai-rag, rag-retrieval, qdrant-seed
- agents/MCP: mcp_servers
- notifications/channels: notification-agent, telegram-bot
- remote sensing: raster-service, raster-tiler-service, remote-sensing-workspace-bff
- platform core: sahool-platform and its worker deployment units
- segmentation inference: sam2-inference
- ground ingest: scout-ingest-service
- soil: soil-service
- media: tts-service, video-processor
- vegetation interpretation: vegetation-analysis-service
- weather: weather-service, weather-polygon-worker, weather-signal-engine

## Declared data ownership surface

The catalogue reports table ownership counts that must be reconciled against migrations, readers, writers, RLS and runtime use. Notable declared counts include:

- sahool-platform: 196
- decision-service: 42
- field-management-service: 32
- soil-service: 32
- agriai-engine: 21
- erp-bridge: 15
- raster-service: 13
- scout-ingest-service: 11
- weather-service: 8
- actuator-service: 7
- mcp_servers: 6

These are hypotheses to verify, not proof of correct ownership.

## Static state requiring investigation

The generated inventory itself exposes asymmetric states that later tests must explain rather than normalize away:

- `agriai-engine`: `wired=False`, `tested=True`.
- `raster-tiler-service`: `wired=True`, `tested=False`.
- `sam2-inference`: `wired=True`, `tested=False`.
- `weather-polygon-worker`: `wired=True`, `tested=False`.
- `weather-signal-engine`: `wired=True`, `tested=False`.
- frontend/mobile/notification-agent/telegram-bot/qdrant-seed have blank fields in parts of the static wired/tested surface; blank is not automatically `false`.

## Inventory graph contract

Before writing the diagnostic scanners, the inventory is modeled as edges:

`component -> deployment unit -> capability/route -> producer -> consumer -> table -> event subject -> worker -> external provider -> UI/mobile caller -> test evidence -> runtime evidence`

Each edge has one of three evidence states only:

- `resolved`: supported by a concrete source artifact/call site.
- `declared`: present in a registry/catalogue but not yet independently resolved.
- `unresolved`: insufficient evidence; no negative conclusion is inferred.

No `unresolved` edge is automatically classified as orphan/dead/no-consumer.

## Reconciliation dimensions

The inventory pass must reconcile independently:

1. Components: catalogue vs repository directories vs compose deployment units.
2. Routes/capabilities: generated catalogue/OpenAPI/router declarations vs real callers.
3. Database: declared ownership vs migrations vs writers/readers vs RLS policy surface.
4. Events: subject registry vs publish sites vs subscribe sites vs worker deployment.
5. Runtime topology: compose services/networks/ports vs gateway/BFF/upstream references.
6. AI: runtime pipelines/models/tools/RAG/guardrails vs production entrypoints and container COPY boundaries.
7. External integrations: weather, satellite/STAC/CDSE, ERP, notification channels, object/vector stores and any fallback providers.
8. User surfaces: frontend/mobile routes and API clients vs backend capabilities.
9. Operations: workers, schedulers, queues, retries, DLQs, idempotency and approval boundaries.
10. Evidence: tests, generated guards and runtime evidence ledgers mapped back to the exact component/edge they actually prove.

## Known main observation relevant to the AI graph

At this baseline commit, `AI-RUNTIME-WIRING-01` is recorded before implementation: `RecommendationRuntimePipeline` has no non-test consumer and the platform image does not copy the `services/ai_agronomist` implementation. The next inventory pass must therefore distinguish source-level availability from image/runtime reachability.

The same commit records that `config/guardrail_feature_flags.py` is not copied into any image while consumers import it behind fallback behavior. This belongs in the deployment/runtime-boundary inventory, not in a generic source-code existence count.

## Required inventory artifacts before diagnostic probes

The intended normalized inventory set is:

- `components.json`
- `deployment_units.json`
- `capabilities.json`
- `routes.json`
- `database_ownership.json`
- `event_topology.json`
- `workers_schedulers.json`
- `external_integrations.json`
- `frontend_consumers.json`
- `mobile_consumers.json`
- `ai_runtime_graph.json`
- `observability_surface.json`
- `test_evidence_map.json`
- `integration_edges.json`
- `unresolved_edges.json`
- `inventory_manifest.json`

These artifacts are descriptive. They do not contain release verdicts or blocking thresholds.

## Sequencing rule

Do not implement `hardcoded_value_scanner`, `silent_fallback_scanner`, `contract_drift_scanner`, or live certification tests until this inventory graph has been populated sufficiently to tell a scanner which architectural role a source location or edge represents. The scanners should consume inventory context rather than rediscovering architecture independently.

---

## إعادةُ قياسٍ — 2026-09-19 (لا استبدالَ للقطة أعلاه)

**اللقطةُ فوق مثبَّتةٌ بـ`d3734df1` بنصّها، فلا تُعاد كتابتُها.** وثيقةٌ تُعلن مصدرَها ثمّ
تُحدَّث أرقامُها في مكانها تصير تقول عن SHA ما لم يُقَس عنده — وهو صنفُ «أخضرُ قِيس في
عالمٍ غير الذي يُقرأ فيه» في ثوبٍ وثائقيّ. فالقياسُ الجديد يُضاف **بجانبها**.

**المقيس على** `f0126469f355` (ضمُّ `main@ecf91cbf8c46` إلى هذا الفرع):

| السطح | لقطة 09-17 | الآن | الفارق |
|---|---:|---:|---|
| سجلّات المكوّنات | 36 | **36** | — |
| ملكيّةُ الجداول · `sahool-platform` | 196 | **196** | — |
| ملكيّةُ الجداول · `decision-service` | 42 | **42** | — |
| ملكيّةُ الجداول · `soil-service` | 32 | **33** | **+1** |
| ملكيّةُ الجداول · `field-management-service` | 32 | **32** | — |
| ملكيّةُ الجداول · `agriai-engine` | 21 | **21** | — |

**والزيادةُ الوحيدةُ مفسَّرةٌ بمصدرها:** `soil_reconciliation_deferrals` — سجلُّ التأجيل
الذي أدخلته #1033 لإغلاق `RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01`.
وإجماليُّ الجداول المُعلَنة **391**.

**وحدودٌ مقيسةٌ في هذا الفرع نفسِه، تُقال لأنّها تُغيّر كيف تُقرأ اللقطتان:**

- **المولِّدُ غيرُ موصول.** لا سيرَ عملٍ ولا اختبارَ يذكر `build_main_inventory.py`
  (مقيسٌ بمسح الشجرة)، ومخرجُه تحت `artifacts/` وهو **مُتجاهَلٌ في `.gitignore``**.
  فلا شيءَ يُعيد إنتاج هذه الأرقام تلقائيّاً ولا يحفظها؛ إعادةُ القياس فعلٌ بشريّ.
- **الأسطحُ الفارغةُ مقصودةٌ لا ناقصة** (`database_ownership.json` · `event_topology.json`
  · `routes.json` وسبعةٌ غيرُها): المولِّدُ يُعلن في شيفرته أنّها «تُعلن ما يجب أن
  يحسمه المسحُ التالي بدل أن تدّعي أنّ علاقةً غيرَ مقيسة غيرُ موجودة». **لكنّ الملفَّ
  على القرص يقول `[]` ولا يقول ذلك** — فقارئُ المصنوعة وحدَها لا يفرّق بين «قِيس فلم
  يُوجَد» و«لم يُقَس». والأرقامُ أعلاه مأخوذةٌ من `db_ownership.yml` مباشرةً لا من تلك
  المصنوعة.
- **الحوافُّ غيرُ المحسومة 722 مقابل 0 محسومة** — والمولِّدُ يسمّيها كذلك صراحةً
  (`evidence_state: declared`) ويرفق بكلٍّ منها سؤالَها. فهذا وصفٌ لا حكم.

## إعادةُ قياسٍ ثالثة — 2026-09-20 (بجانب سابقتَيها، لا فوقهما)

**المقيس على** `00d5c09ad` — ضمُّ `main@98a61c5f2` (بعد #1036 و#1037 و#1038) إلى هذا
الفرع. ومُدخَلا الجرد (`component_inventory.generated.csv` · `platform_catalog.generated.json`)
**مطابقان بايتاً** لما على `main` عند ذلك الرأس (`ae29a587` · `fcdfe548`)، فالقياسُ
هنا قياسُ `main` لا قياسُ فرعٍ منحرفٍ عنه.

| السطح | لقطة 09-17 | إعادةُ 09-19 | الآن 09-20 |
|---|---:|---:|---:|
| سجلّات المكوّنات | 36 | 36 | **36** |
| القدرات | — | 828 | **828** |
| وحدات النشر | — | 48 | **48** |
| حوافّ معلَنة غيرُ محسومة | — | 722 | **722** |
| حوافّ محسومة | — | 0 | **0** |
| مجموعُ الجداول المُعلَنة | — | 391 | **391** |

**ولا شيءَ تحرّك، وهذا هو الخبر.** ثلاث شرائحَ دُمِجت بين القياسَين ولم تُغيّر جرداً
واحداً — لأنّ الثلاثَ مسّت الحوكمةَ والحرّاس لا سطحَ المكوّنات. وسكونُ الجرد أمام
تغيّرٍ حقيقيٍّ في مكانٍ آخر ليس عطلاً؛ العطلُ أن يسكنَ أمام تغيّرٍ **في مُدخَلِه** —
وذلك ما يفرضه الآن `test_a_changed_relation_shows_up_in_the_inventory`.

### ما تغيّر في المولّد نفسِه

- **الأسطحُ العشرةُ لم تعد `[]` عارية.** كلُّ واحدٍ منها صار كائناً يحمل
  `measurement_state: not_measured` و`rows: []` و`row_count: 0` و**سؤالاً يجب أن
  يُحسَم** ومرشّحاتِ مصدرٍ تُوجّه القياسَ التالي. والترويسةُ تُعلن `surfaces_not_measured:
  10 / 10`. **الفرقُ بنيويٌّ لا بلاغيّ:** `measured` + صفرُ صفوفٍ دعوى، و`not_measured`
  + صفرُ صفوفٍ امتناعٌ عن الدعوى — والقارئُ الآليُّ لا يقرأ التعليقات.
- **المولّدُ صار موصولاً.** `tests_v9/test_main_inventory_generator.py` (١٦ حالة،
  مُعلَّمة `unit`) و`.github/workflows/diagnostic-inventory.yml`: تُشغَّل الشواهد،
  ويُبنى الجردُ **مرّتين** ويُقارَن `diff -r` بايتاً، ويُرفَع المخرجُ مصنوعاً بمدّة
  حفظ ٣٠ يوماً. وتطبع الوظيفةُ عددَ الأسطح غيرِ المقيسة في سجلّها كي لا يُقرأ «مرّ»
  على أنّه «كلُّ شيءٍ مقيس».
- **التكذيبُ حيٌّ لا مفترَض:** إعادةُ `[]` العارية إلى المولّد تُسقِط **١٦/١٦** حالة؛
  واستعادتُه تُعيدها خضراء.

### ما لا يُدَّعى بعدُ

- **٧٢٢ حافّةً معلَنةً ما تزال غيرَ محسومة، و٠ محسومة.** لم يُرقَّ شيءٌ إلى `resolved`،
  ولم يُختلَق حسمٌ كي يخضرّ تقرير. والترقيةُ تحتاج موضعَ استدعاءٍ مصدريّاً أو أثراً
  تشغيليّاً، ويفرض ذلك `test_a_declared_edge_is_never_promoted_to_resolved_without_evidence`.
- **الأسطحُ العشرةُ ما تزال غيرَ مقيسة.** ما تغيّر أنّها **تقول ذلك عن نفسها** بدل أن
  تبدو فارغة. ولا يُرقّى سطحٌ إلى `measured` إلّا بمقياسٍ يُنتِج صفوفَه — فالترقيةُ
  بالقياس لا بالتحرير.
