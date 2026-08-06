# كتالوج الحرّاس — ما يفرضه كلّ حارس وأين يحجب

> **مصنوعة مولَّدة.** لا تُحرَّر يدويّاً: `python scripts/ci/guard_catalogue.py`.
> مشتقّة من الـworkflows (أين يحجب) · `guard_mutation_registry.json` (ما يمسكه،
> بكلمات كاتبه) · وسطر التوثيق الأوّل في الحارس نفسه (ما يفرضه).

**كيف تقرأ هذا الجدول عند فشل بوّابة:** ابحث عن اسم السكربت في رسالة الفشل، ثمّ
اقرأ عمود «ما يمسكه» — فهو يصف العطل الذي وُجِد الحارس لأجله، لا القاعدة مجرّدة.
و«الاختبار الشاهد» هو ما يجب أن يحمرّ إن عُطِّل الحارس؛ شغّله لتفهم الخاصّيّة.

## ما يقوله هذا الجرد قبل أيّ تفصيل

- حرّاس تحجب في CI: **220**
- منها **مُثبَتة بالتكذيب** (لها مواصفة طفرة نُفِّذت): **9**
- إجماليّ الطفرات المُسجَّلة: **43**

أي أنّ **211** حارساً يحجب الدمج ولم يُثبَت قطّ أنّه
يفشل حين يوجد العطل. هذا ليس اتّهاماً لها بل **قياس لِما نعرفه عنها**: اختبار
الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة، وهي خاصّيّة يُحقّقها حارسٌ لا يفعل
شيئاً. ومواصفة الطفرة هي الفرق بين «يمرّ» و«يمسك».

---

## الحرّاس المُثبَتة بالتكذيب (9)

لكلٍّ منها عطلٌ يُزرَع في مصدرها فعليّاً (`guard_mutation_guard --run`) واختبارٌ
**مُسمّى** يجب أن يحمرّ عندها. حمرةٌ باختبار آخر ليست دليلاً.

### `brain_append_only_guard.py`

**يفرض:** An append-only journal may not shrink — and a merge must preserve **both** parents.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_append_only_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- فحصُ والدٍ واحد ⇒ عمى الدمج نفسه الذي أنجى `cb6598fe`: الملفّ محفوظ عند والد ومفقود عند الآخر، فالفحص مقابل أحدهما يمرّ — يُسقِط `test_both_parents_are_examined_not_just_one`
- جعلُ التقلّص إرشاديّاً ⇒ يعود ١٬٣٨٣٬٣٦٨ بايت إلى صفر بلا حجب، وهي الواقعة الأصليّة. والاختبار المُسمّى **اصطناعيّ عمداً**: اختبار الواقعة الحقيقيّة (test_the_guard_fails_on_the_truncation_that_created_it) يحتاج التاريخ الكامل ويُتخطّى في استنساخ CI الضحل — وطفرةٌ تُسمّي اختباراً مُتخطّى ليست تكذيباً بل صمتاً. — يُسقِط `test_a_merge_that_takes_the_empty_side_is_caught`
- إسقاطُ فحص الغياب ⇒ شجرةٌ بلا سجلّات تُنتِج صفر أزواج وتطبع ok — «لا شيء للمقارنة» يُقرأ نجاحاً، وهو صنف الفجوة نفسه داخل علاجها — يُسقِط `test_a_missing_journal_at_head_blocks_even_with_nothing_to_compare`
- تصليبُ القائمة ⇒ فهرس ثانٍ ينحرف عن `resolve_merge_conflicts`، وهو صنف «قائمتان تصفان الشيء نفسه» — يُسقِط `test_the_file_list_comes_from_the_existing_classifier`

### `brain_duplicate_gap_identity_guard.py`

**يفرض:** يمسك الفشل الصامت الذي يتركه دمج `union` — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_duplicate_gap_identity_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- التكرار بدل التلاصق ⇒ السلاسل التاريخيّة المقصودة تُرفَع إنذاراً (١٠ من ١١ على الشجرة) — يُسقِط `test_a_deliberate_history_chain_passes`

### `brain_state_transition_guard.py`

**يفرض:** Prevent sahool-brain-only edits from claiming executable/certification closure.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_transition_guard_vocabulary.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إعادة النمط القديم `\b(CLOSED|…)\b` — خاطئ في الاتّجاهين: يطابق داخل fail-closed ولا يطابق CLOSED_IN_CODE — يُسقِط `test_the_underscore_vocabulary_was_the_false_negative`
- نزع اشتراط كود تنفيذيّ خارج الدماغ ⇒ ادّعاء إغلاق دماغيّ صرف يمرّ — يُسقِط `test_brain_only_diff_with_a_real_claim_is_still_rejected`
- نزع اشتراط القيمة الصفريّة من الاستثناء ⇒ `runtime_verified: 1` يصير اقتباساً معفىً — إصلاحُ إيجابيّة كاذبة يصنع سلبيّة كاذبة أخطر — يُسقِط `test_a_positive_valued_claim_is_still_rejected`
- إعادة المطابقة الخام بلا مرساة دلاليّة ⇒ اقتباس `production_certified=0/81` نفياً يُقرأ ادّعاءً — يُسقِط `test_a_zero_valued_citation_is_not_a_closure_claim`

### `claim_base_guard.py`

**يفرض:** كلّ ادّعاء يحمل أساسه — CLAIMS-WITHOUT-A-MEASURED-BASE-01.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_claim_base_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- مطابقة المفتاح بالبادئة بدل التامّة ⇒ `baseline_route_count` يُقبَل أساساً — يُسقِط `test_a_count_is_not_a_base`
- نزع سقف الدَّين ⇒ قائمة «تتقلّص ولا تنمو» تنمو — يُسقِط `test_debt_growth_is_blocked_by_the_ceiling`
- نزع الإنفاذ العكسيّ ⇒ مدخل اكتسب ختماً يبقى ديناً بائتاً — يُسقِط `test_debt_that_gained_a_base_must_leave_the_list`
- قبول ختم القياس مكان تاريخ الحكم — يُسقِط `test_a_measured_stamp_does_not_satisfy_a_decision`
- قبول تاريخ الحكم مكان ختم القياس — يُسقِط `test_a_decision_stamp_does_not_satisfy_a_measurement`
- نزع حجب المصنوعة غير المصنَّفة ⇒ ملفّ جديد يدخل بلا صنف — يُسقِط `test_unclassified_artifact_is_blocked`
- نزع حجب مدخل الدَّين البائت — يُسقِط `test_stale_debt_entry_is_blocked`
- SHA مجهول يُبلَّغ «صفر التزام» بدل «غير قابل للحلّ» — يُسقِط `test_an_unknown_sha_reports_unresolvable_not_zero`

### `container_command_path_guard.py`

**يفرض:** مسارٌ يُنفّذه compose يجب أن تضعه صورةُ الخدمة فعلاً — «مُسجَّل» ليس «يعمل».

**يحجب في:** `ci.yml` → `compose-validate`

**الاختبار الشاهد:** `tests_v9/test_container_command_path_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- ادّعاء الوجود بلا فحص وجود ⇒ كلّ مسار «تضعه الصورة» والعطل الأصليّ يمرّ — يُسقِط `test_the_old_location_is_still_unreachable_from_that_image`
- تعطيل الفحص كلّيّاً ⇒ الحارس يخضرّ على شجرة معطوبة — يُسقِط `test_a_missing_path_is_reported_with_the_service_that_executes_it`
- صفر أزواج مفحوصة ⇒ «أخضر لأنّه لم ينظر» — الصفر الصامت نفسه — يُسقِط `test_it_actually_examines_something`
- إسقاط نسخ ملفّ→ملفّ ⇒ ثلاث خدمات سليمة تُتَّهم (الإيجابيّة الكاذبة المقيسة) — يُسقِط `test_copy_semantics_are_applied_not_approximated`

### `guard_mutation_guard.py`

**يفرض:** لا حارس بلا عطلٍ مزروع يُثبِت أنّه يُطلِق — GUARDS-WITHOUT-A-PLANTED-DEFECT-01.

**يحجب في:** `ci.yml` → `lint` · `ci.yml` → `unit-tests`

**الاختبار الشاهد:** `tests_v9/test_guard_mutation_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع حجب الحارس الجديد بلا مواصفة ⇒ الآليّة كلّها تصير اختياريّة — يُسقِط `test_a_new_guard_without_a_mutation_spec_is_blocked`
- قبول مواصفة بائتة سلسلتها لم تعد في المصدر — يُسقِط `test_a_stale_mutation_string_is_blocked`
- قبول سلسلة متكرّرة ⇒ الزرع غير محدَّد الموضع — يُسقِط `test_an_ambiguous_mutation_string_is_blocked`
- قبول «سقط شيء ما» بدل الاختبار المُسمّى ⇒ طفرة تكسر الاستيراد تُحسَب نجاحاً — يُسقِط `test_red_by_the_wrong_test_is_not_proof`
- نزع سقف الدَّين — يُسقِط `test_debt_growth_is_blocked_by_the_ceiling`
- نزع حجب المدخل البائت لحارس غير موجود — يُسقِط `test_an_entry_for_a_missing_guard_is_blocked`
- اعتبار الحارس المزروع فيه العطل ناجحاً إن خرج بصفر — يُسقِط `test_a_green_suite_under_a_planted_defect_is_a_failure`
- قبول `expect` بادئةً عامّة لا اسم اختبار موجود ⇒ الشرط يعود إلى «سقط شيء ما» — يُسقِط `test_a_bare_prefix_is_not_an_expected_test`
- اعتبار انهيار المُشغِّل دليلاً ⇒ بيئة بلا pytest تُبلَّغ «حمرّ بغير الاختبار المُتوقَّع» — يُسقِط `test_a_runner_that_never_ran_is_not_evidence`
- نزع تسمية الاختبارات الساقطة فعلاً ⇒ فرع «حمرّ بغير المتوقَّع» يعود غير قابل للتشخيص من سجلّه — يُسقِط `test_the_wrong_test_branch_names_what_actually_failed`
- عودةُ ذاكرة الـbytecode ⇒ طفرتان متساويتا الطول تتبادلان الأثر (السبب الجذريّ المُثبَت للرقيعة) — يُسقِط `test_the_runner_blocks_bytecode_caching`
- إسقاط برهان الاستعادة ⇒ تسرّبٌ بين طفرتين يظهر «عشوائيّةً» لا عطلاً — يُسقِط `test_a_restore_that_did_not_restore_is_reported`

### `platform_module_reachability_guard.py`

**يفرض:** Classify platform modules by the executable root that can actually reach them.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests_v9/test_platform_module_reachability_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع فهرسة الحزمة باسمها ⇒ كلّ سلسلة تمرّ بـ__init__ تبدو مقطوعة، فتُصنَّف وحدات موصولة فعلاً كسلاسل طرفيّة ميتة — الحارس يخترع العطل بدل أن يجده — يُسقِط `test_a_module_behind_a_package_is_reachable_not_terminal`
- ترك الاستيراد النسبيّ بلا حلّ ⇒ from .canonical_water import … لا يُنتِج حافّة، فتبدو canonical_water/canonical_boundary ميتتين وهما مستهلَكتان — يُسقِط `test_relative_imports_resolve_against_the_importing_package`
- جعل كلّ وحدة قابلة للوصول ابتداءً ⇒ التصنيف يفقد قدرته على قول (ميت)، وهو الغرض الوحيد للحارس — يُسقِط `test_a_module_nothing_executes_is_terminal`
- المُشغِّل المُنفَّذ بمسار يُعَدّ قناةً لا جذراً ⇒ نقطة الدخول نفسها تُصنَّف «ميتة» بينما compose يشغّلها — يُسقِط `test_a_path_launched_worker_inside_the_platform_is_a_root_itself`
- ‏/app يُقرأ جذرَ المستودع لا جذرَ الخدمة — الافتراض الذي أنتج CONTAINER-COMMAND-PATH-NOT-IN-IMAGE-01 — يُسقِط `test_the_container_path_maps_to_the_service_root_not_the_repository_root`

### `probe_leak_guard.py`

**يفرض:** يُسمّي مِسبار اختبار تسرّب إلى الشجرة، بدل تركه يُشخَّص خطأً — `TEST-PROBE-LEAKS-INTO-THE-TREE-01`.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_probe_leak_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع استثناء المواضع الشرعيّة ⇒ الحارس يُطلِق على الاختبار الذي يُعرّف المِسبار وعلى الدماغ الذي يشرح الحادثة — يُسقِط `test_the_guard_does_not_fire_on_the_places_that_legitimately_name_the_probe`

### `schema_validation_guard.py`

**يفرض:** One validator for every ``*.schema.json`` in the repository.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_schema_validation_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبولُ مخطَّط بلا $schema ⇒ يعود أحد عشر ملفّاً لا يُعرَف بأيّ مواصفة تُقرأ، وهو العطل الأصليّ الذي بُنِيت البوّابة له — يُسقِط `test_a_missing_meta_schema_is_caught`
- قبولُ $ref خارجيّ ⇒ يصير الخضوع رهن الشبكة وترتيب الملفّات لا صحّة العقد — يُسقِط `test_an_external_ref_is_caught`
- تخطّي التحقّق من صحّة المخطَّط نفسه ⇒ الحارس يُبلِغ خضرةً عن سؤال لم يطرحه — يُسقِط `test_a_schema_invalid_for_its_declared_draft_is_caught`

---

## حرّاس تحجب ولم تُثبَت بالتكذيب (211)

تعمل، وتُسقِط بناءً حين تُخالَف — لكنّ أحداً لم يقِس أنّها **تفشل حين يوجد**
**العطل**. عند إضافة مواصفة لأيٍّ منها ينتقل صفّها إلى القسم أعلاه تلقائيّاً.

| الحارس | يفرض | يحجب في |
|---|---|---|
| `agronomic_context_gate.py` | AC-1 gate: the agronomic-context contract layer must stay canonical and fail-closed. | `structural-lint` |
| `agronomic_decision_lineage_gate.py` | AC-6 gate: direct agronomic lineage on decisions must stay present and fail-closed. | `structural-lint` · `contract` |
| `agronomic_learning_lineage_gate.py` | AC-9 gate: governed agronomic evidence must keep propagating into learning datasets. | `structural-lint` · `contract` |
| `agronomic_lineage_integrity_gate.py` | AC-6.1 gate: tenant-safe agronomic lineage and semantic evidence consistency. | `structural-lint` · `contract` |
| `agronomic_model_lifecycle_lineage_gate.py` | Cohort lineage gate: evaluation → promotion → activation must carry the cohorts intact. | `structural-lint` · `contract` |
| `agronomic_runtime_lineage_gate.py` | Runtime cohort lineage gate: monitoring/retraining stay bound to authoritative upstream. | `structural-lint` · `contract` |
| `agronomic_runtime_terminal_lineage_gate.py` | Terminal lineage gate: rollback/rollout/dispatch receipts + rollback-aware monitoring. | `structural-lint` · `contract` |
| `ai_agronomist_main_decomposition_guard.py` | Guard the ai-agronomist main.py decomposition boundary. | `guard` |
| `ai_container_contract_guard.py` | Guard AI-oriented containers for liveness/readiness and post-decomposition copy contracts. | `ai-container-contract` |
| `api_versioning_policy_guard.py` | Inventory and freeze unversioned business routes. | `capability-registry` |
| `arch_test_ci_coverage_guard.py` | كلّ اختبار في ``tests/architecture/`` يجب أن يُشغّله workflow — أو يُعفى بسببه. | `capability-registry` |
| `architecture_graph.py` | Build a conservative service architecture graph from repository evidence. | `capability-registry` |
| `assertion_presence_guard.py` | حارس «الخضرة الزائفة»: دالّة اختبار بلا تأكيد **وتُرجِع قيمة** لا يمكن أن تفشل. | `capability-registry` |
| `auth_main_decomposition_guard.py` | Guard the auth-service main.py decomposition boundary. | `guard` |
| `backfill_ui_sync_gate.py` | Static contract gate for historical imagery backfill UI/runtime synchronization. | `structural-lint` |
| `brain_commit_claim_guard.py` | يمنع رسالة التزام من ادّعاء تسجيل فجوة لم تُسجَّل. | `no-report-only-change` |
| `brain_deferral_registry_guard.py` | يمنع تسرّب التأجيلات من `hot.md` دون تسجيلها في `gaps/registry.md`. | `no-report-only-change` |
| `build_service_dependency_bundle.py` | Build a deterministic direct-dependency bundle for audit/review. | `dependency-conflict-inventory` |
| `calibration_dataset_boundary_gate.py` | — | `structural-lint` |
| `capability_core_consumption_guard.py` | Ratchet the platform capability cores against silently returning to orphaned. | `capability-registry` |
| `capability_evidence_maturity_engine.py` | Generate a fail-closed evidence matrix and evidence-derived maturity baseline. | `capability-registry` |
| `capability_linker.py` | Conservatively link SAHOOL capabilities to repository services, APIs, tests and consumers. | `capability-registry` |
| `capability_management_engine.py` | Generate the unified SAHOOL Capability Management Layer. | `capability-registry` |
| `capability_mapping_engine.py` | Build a deterministic repository-to-capability evidence map for SAHOOL. | `capability-registry` |
| `capability_parity_investment_engine.py` | Generate fail-closed capability parity and investment artifacts. | `capability-registry` |
| `capability_registry_guard.py` | Validate the canonical SAHOOL capability registry and generate governance outputs. | `capability-registry` |
| `capability_registry_v1.py` | — | `capability-registry` |
| `capability_release_history.py` | Generate deterministic capability history from committed static baselines. | `capability-registry` |
| `capability_roadmap_linker.py` | Validate and generate the curated roadmap-to-capability linkage. | `capability-registry` |
| `capability_runtime_evidence.py` | Extract conservative runtime observability evidence for SAHOOL capabilities. | `capability-registry` |
| `compose_env_contract_gate.py` | Fail-closed contract gate for docker-compose ↔ .env compatibility. | `structural-lint` |
| `compose_runtime_target_resolver.py` | Resolve runtime probe targets to internal Docker Compose service URLs. | `capability-registry` |
| `consumer_contract_gate.py` | WS-E — CI consumer-contract gate. | `structural-lint` |
| `container_fleet_contract_guard.py` | Container fleet contract guard. | `guard` |
| `container_image_pin_guard.py` | Reject mutable or unversioned container images in production Compose files. | `attest-source-release` · `supply-chain-static-scan` |
| `contract_capabilities_schema_guard.py` | Guard stable schemas for /contract and /capabilities endpoints. | `contract-capabilities-schema` |
| `crop_intelligence_boundary_gate.py` | Keep Crop Intelligence as an interpretation layer, not a weather calculator. | `structural-lint` |
| `database_contract_graph.py` | — | `capability-registry` |
| `decision_candidate_boundary_gate.py` | WX-10.6 — Keep the Crop→Decision candidate path a reviewable candidate, never execution. | `structural-lint` |
| `decision_lineage_graph.py` | Generate a deterministic static decision-lineage knowledge graph. | `capability-registry` |
| `decision_lineage_v183_guard.py` | Static ratchet for v183 DB-owned immutable content lineage (renumbered from P0-fix v182). | `structural-lint` |
| `decision_review_boundary_gate.py` | WX-10.7 — Keep the reviewer/decision path a state transition, never execution. | `structural-lint` |
| `decision_review_ownership_consistency_gate.py` | WX-10.7 — ownership/config consistency for the decision review transition. | `structural-lint` |
| `decision_sor_cutover_readiness_gate.py` | Static cutover-readiness gate for decision-service SoR promotion. | `field-workspace-closure` |
| `decision_sor_final_certification_gate.py` | Static gate for P0-5/P0-6 Decision SoR final certification controls. | `field-workspace-closure` |
| `decision_sor_review_cutover_gate.py` | WX-10.7 — SoR-promotion cutover-prep gate (DEPLOYED-DECISION-SOR-PROMOTION). | `structural-lint` |
| `decision_sor_shadow_promotion_gate.py` | Static gate for P0-3 decision-service shadow/promotion controls. | `field-workspace-closure` |
| `decision_sor_staging_probe_gate.py` | Static gate for P0-4 decision-service staging probe harness. | `field-workspace-closure` |
| `design_token_contrast_gate.py` | بوّابة تباين توكِنات التصميم (WCAG 2.1) — مُكيَّفة لساهول (مُلهَمة من قواعد impeccable). | `structural-lint` |
| `dispatch_authorization_boundary_gate.py` | WX-10.10 guard: authorization must not become dispatch or execution. | `structural-lint` |
| `docker_build_matrix_verifier.py` | Docker build matrix verifier for Sahool services. | `docker-build` |
| `duplicate_definition_guard.py` | Detect duplicate Python definitions in the same lexical scope. | `capability-registry` |
| `edge_inference_service_contract_gate.py` | CI guard for edge-inference service runtime/config contracts. | `field-workspace-closure` |
| `edge_model_contract_guard.py` | Guard the edge-inference model contract. | `edge-model-contract` · `model-provisioning-evidence` |
| `edge_production_readiness_guard.py` | Guard Edge production-readiness policy. | `edge-production-readiness` · `model-provisioning-evidence` |
| `endpoint_ui_coverage_gate.py` | SAHOOL endpoint-ui-coverage-gate. | `structural-lint` |
| `env_compose_drift_guard.py` | حارس انجراف env↔compose (السجل التشغيليّ #3) — صنف عضّ مرتين، فأُغلِق بحارس. | `structural-lint` |
| `event_contract_graph.py` | Generate a conservative static NATS/JetStream event contract graph. | `capability-registry` |
| `execution_delivery_receipt_boundary_gate.py` | — | `structural-lint` |
| `execution_dependency_audit.py` | Generate a conservative static execution/dead-code audit. | `capability-registry` |
| `execution_outcome_boundary_gate.py` | WX-10.12 guard: outcome verification must not perform learning updates. | `structural-lint` |
| `execution_request_boundary_gate.py` | — | `structural-lint` |
| `expected_control_flow_guard.py` | يفرض عقد الاستثناءات المتوقَّعة — EXPECTED-CONTROL-FLOW-EXCEPTION. | `structural-lint` |
| `fastapi_lifespan_guard.py` | Prevent reintroduction of deprecated FastAPI ``on_event`` hooks. | `structural-lint` |
| `field_workspace_production_closure_gate.py` | Field Workspace production closure gate. | `field-workspace-closure` |
| `fii_rls_write_policy_gate.py` | FII Safety Increment 1C: reject unsafe tenant-write RLS patterns. | `security-scan` |
| `functional_probe_runner.py` | Strict functional probe runner. Produces signed, runtime-bound evidence only. | `capability-registry` |
| `gateway_reachability_guard.py` | Build a deterministic Nginx/API-gateway reachability and security inventory. | `capability-registry` |
| `generate_indicator_artifacts.py` | — | `structural-lint` |
| `generate_indicators_frontend_manifest.py` | مولّد مانيفست الواجهة (build-time) لسجلّ المؤشّرات — WS-B.2 (manifest-only). | `structural-lint` |
| `generate_service_inventory.py` | Generate Sahool service and route inventory from source code. | `structural-lint` · `drift` |
| `github_actions_policy_guard.py` | Enforce immutable third-party Actions and reject privileged workflow patterns. | `supply-chain-static-scan` |
| `guard_catalogue.py` | What every guard enforces, what it catches, and where it runs — derived, never listed. | `structural-lint` |
| `health_readiness_schema_guard.py` | Guard canonical health/readiness response envelopes. | `health-readiness-schema` |
| `indicators_container_contract_guard.py` | Guard the indicators-service canonical-observation-adapter container boundary. | `indicators-container-contract` |
| `indicators_registry_gate.py` | Guard: config/indicators_registry.json is the single source of truth for indicators. | `structural-lint` |
| `integration_runtime_governance_closure.py` | Artifact-based closure gate for PATH-2 integration/runtime-evidence governance. | `capability-registry` |
| `intelligence_governance_gate.py` | — | `structural-lint` |
| `irrigation_as_applied_m2_11_guard.py` | Static ratchet for M2.11 canonical as-applied irrigation truth. | `structural-lint` |
| `irrigation_capability_graph_m2_8_guard.py` | Repository ratchet for M2.8 unified irrigation capability graph. | `structural-lint` |
| `irrigation_closed_loop_m5_guard.py` | Static ratchet for M5 irrigation closed-loop learning and certification. | `structural-lint` |
| `irrigation_closed_loop_runtime_guard.py` | Ratchet for durable measured irrigation reconciliation. | `structural-lint` |
| `irrigation_commissioning_m2_10_guard.py` | Static ratchet for M2.10 irrigation commissioning certification. | `structural-lint` |
| `irrigation_controller_edge_m2_9_guard.py` | Static ratchet for M2.9 controller/edge framework. | `structural-lint` |
| `irrigation_convergence_guard.py` | Fail CI when IRR work introduces a parallel irrigation system of record. | `contract` |
| `irrigation_energy_m2_7_guard.py` | Repository ratchet for M2.7 energy/microgrid capability. | `structural-lint` |
| `irrigation_engineering_m2_1_guard.py` | Static ratchet for the M2.1 irrigation engineering foundation. | `structural-lint` |
| `irrigation_hourly_mpc_m3_guard.py` | Static ratchet for M3 hourly energy-aware irrigation MPC. | `structural-lint` |
| `irrigation_hydraulic_m2_4_guard.py` | Repository ratchet for M2.4 hydraulic capability. | `structural-lint` |
| `irrigation_machine_m2_5_guard.py` | Repository ratchet for M2.5 irrigation machine capability. | `structural-lint` |
| `irrigation_rls_canonical_guard.py` | Guard: the V21 irrigation migrations (v168–v181) must use canonical, fail-closed RLS. | `structural-lint` |
| `irrigation_root_zone_m2_2_guard.py` | Static ratchet for M2.2 canonical root-zone hydraulics. | `structural-lint` |
| `irrigation_runtime_orchestrator_guard.py` | Ratchet for the server-owned irrigation runtime orchestrator. | `structural-lint` |
| `irrigation_sprinkler_m2_6_guard.py` | Repository ratchet for M2.6 sprinkler/runoff capability. | `structural-lint` |
| `irrigation_vri_m4_guard.py` | Static ratchet for M4 governed VRI prescriptions. | `structural-lint` |
| `irrigation_well_digital_twin_m2_3_guard.py` | Static ratchet for M2.3 water-source and well digital twin. | `structural-lint` |
| `irrx1_6_manual_volume_guard.py` | — | `structural-lint` |
| `irrx1_7_interactive_calculator_guard.py` | — | `structural-lint` |
| `irrx1_8_reservoir_booster_guard.py` | — | `structural-lint` |
| `irrx1_9_multi_system_calculator_guard.py` | — | `structural-lint` |
| `irrx1_authoritative_provenance_guard.py` | Static ratchet for IRR-X1.5 authoritative manual-execution provenance. | `structural-lint` |
| `irrx1_commissioning_runtime_guard.py` | — | `structural-lint` |
| `irrx1_farmer_manual_operations_ui_guard.py` | IRR-X1.4 guard: farmer manual operations UI and read path remain wired. | `structural-lint` |
| `irrx1_manual_execution_guard.py` | — | `structural-lint` |
| `irrx1_pcert_guard.py` | Static ratchet for IRR-PCERT wiring and DB-authoritative invariants. | `structural-lint` |
| `irrx1_vendor_neutral_guard.py` | — | `structural-lint` |
| `irrx1_verified_manual_ledger_guard.py` | — | `structural-lint` |
| `jwt_secret_configuration_guard.py` | Fail closed on tracked/release-bundled secrets and unsafe JWT configuration. | `structural-lint` |
| `ky_no_economic_coupling_guard.py` | حارس CI: يمنع اشتقاق أيّ إيراد/هامش اقتصاديّ من معامل Ky قبل نموذج اقتصاديّ صريح. | `structural-lint` |
| `learning_attribution_boundary_gate.py` | WX-10.13 ratchet: outcome attribution must not mutate models or restart execution. | `structural-lint` |
| `migration_graph_guard.py` | — | `capability-registry` |
| `minio_s3_contract_gate.py` | Fail closed on MinIO/S3 credential drift in docker-compose/.env templates. | `structural-lint` |
| `model_activation_approval_boundary_gate.py` | — | `structural-lint` |
| `model_activation_request_boundary_gate.py` | — | `structural-lint` |
| `model_evaluation_boundary_gate.py` | — | `structural-lint` |
| `model_promotion_decision_boundary_gate.py` | — | `structural-lint` |
| `model_registry_activation_boundary_gate.py` | — | `structural-lint` |
| `mpc_lineage_propagation_guard.py` | حارس CI: يضمن أنّ جسر MPC ينشر النَّسَب الكامل ويبقى توصية-فقط (لا تنفيذ تلقائيّ). | `structural-lint` |
| `nginx_compose_dns_gate.py` | Validate that nginx upstream hostnames are resolvable in the selected compose file. | `structural-lint` |
| `nginx_weather_edge_path_guard.py` | Static smoke guard for Nginx weather/edge exposure paths. | `nginx-weather-edge-paths` |
| `no_leakage_certification_gate.py` | Phase C gate: the no-leakage certification surface must stay intact. | `structural-lint` |
| `no_merge_conflict_markers_guard.py` | حارس CI: يمنع تسرّب علامات تعارض دمج git إلى أيّ ملفّ مُتتبَّع. | `structural-lint` |
| `no_report_only_change_guard.py` | Guard against report-only certification/progress changes in CI. | `no-report-only-change` |
| `p1_main_decomposition_guard.py` | Guard P1 main.py decomposition for platform, odoo-bridge, and vegetation. | `p1-main-decomposition` |
| `p2_main_decomposition_guard.py` | Guard P2 main.py decomposition for actuator, SAM2, and weather services. | `p2-main-decomposition` |
| `path3_runtime_activation.py` | Activate a compose stack and collect fail-closed runtime evidence for PATH-3. | `runtime-producer` |
| `path3_runtime_readiness_closure.py` | Close PATH-3 static runtime readiness without claiming live verification. | `capability-registry` |
| `physical_effect_boundary_guard.py` | P0-7 — الأثر الفيزيائيّ لا يُطلَق من الدماغ، ولا يُطلَق إلّا من موضع مُسمّى. | `structural-lint` |
| `pip_audit_resolution_guard.py` | Guard against pip-audit dry-run resolver conflicts on shared packages. | `guard` |
| `pip_mirror_contract_guard.py` | Guard the connected-CI pip index / mirror contract. | `pip-mirror-contract` |
| `platform_main_subinventory_guard.py` | Sub-inventory for services/sahool-platform/api/main.py. | `structural-lint` · `guard` |
| `platform_route_budget_guard.py` | Fail-closed SAHOOL platform domain-route budget guard. | `platform-route-budget` |
| `platform_route_governance_attestation.py` | Cross-attest platform route classification, budget, ownership, and map state. | `platform-route-budget` |
| `platform_route_ownership_guard.py` | Verify and materialize the complete sahool-platform route ownership surface. | `platform-route-budget` |
| `platform_route_placement_guard.py` | Enforce machine-readable source placement for governed platform routes. | `platform-route-budget` |
| `pr_capability_impact_gate.py` | Compute and enforce pull-request capability impact declarations. | `capability-registry` |
| `prepare_attested_runtime_images.py` | Validate an externally built image manifest and generate a pull-by-digest Compose override. | `runtime-producer` · `trusted-signer` |
| `production_certification_blockers_status.py` | Print the current status of the four production certification blockers. | `certification-verdict` · `full-branch-ci-evidence` |
| `production_certification_checklist_guard.py` | Production certification checklist inventory/guard. | `guard` |
| `production_evidence_pack_guard.py` | Production evidence pack guard. | `transitive-locks-evidence` · `evidence-pack` |
| `production_honesty_guard.py` | Production honesty guard. | `honesty` |
| `production_truth_readiness_gate.py` | Production truth/readiness gate: no synthetic serving paths; honest readiness. | `structural-lint` · `contract` |
| `provenance_receipt.py` | Create/validate the external provenance receipt required by the read-only bridge. | `verify-and-evaluate` |
| `raster_import_graph_gate.py` | Static import-graph gate for services/raster-service. | `structural-lint` |
| `raster_main_decomposition_gate.py` | Raster-service main.py decomposition contract gate. | `structural-lint` |
| `raster_pixel_qa_indicator_guard.py` | Guard: raster indicators must carry raw pixel QA/provenance. | `guard` |
| `raster_production_truth_guard.py` | Fail closed if synthetic indicator data can reach production serving paths. | `structural-lint` |
| `raster_topographic_qa_guard.py` | Guard: raster indicator QA must carry honest topographic QA provenance. | `raster-topographic-qa` |
| `raster_validated_product_guard.py` | Guard: raster indicators must expose ValidatedRasterProduct + cloud strategies. | `raster-validated-product` |
| `raw_data_processing_contract_guard.py` | Guard the raw raster data processing contract. | `raw-data-processing-contract` |
| `raw_weather_processing_contract_guard.py` | Guard the weather raw-data processing contract. | `raw-weather-processing-contract` |
| `release_attestation_guard.py` | Fail closed when the release artifact attestation workflow is weakened. | `attest-source-release` |
| `report_index_guard.py` | Generate/check REPORT_INDEX.md for release artifacts and historical reports. | `report-index` |
| `riv_boundary_gate.py` | — | `structural-lint` |
| `rls_policy_guard.py` | — | `capability-registry` |
| `route_conflict_guard.py` | Static FastAPI/Starlette route collision guard. | `capability-registry` |
| `route_mount_contract_guard.py` | Guard route-bearing FastAPI services after main.py decomposition. | `structural-lint` |
| `route_residual_classification_guard.py` | Classify route decorators that remain directly in main.py files. | `classify-main-route-residuals` |
| `router_reachability_guard.py` | Conservative static FastAPI router reachability inventory and drift guard. | `capability-registry` |
| `runtime_certification_gate.py` | Fail closed when runtime or production certification exceeds accepted evidence. | `capability-registry` |
| `runtime_container_deep_contract_guard.py` | Runtime container deep contract guard for non-AI high-risk services. | `guard` |
| `runtime_contract_gate.py` | Runtime-chain static contract gate. | `structural-lint` |
| `runtime_contract_generator.py` | Generate deterministic repository-derived runtime contracts for SAHOOL services. | `capability-registry` |
| `runtime_environment_preflight.py` | Assess whether this checkout can execute SAHOOL PATH-3 live runtime probes. | `capability-registry` |
| `runtime_evidence_ingestion.py` | Validate and normalize runtime evidence into a tamper-evident service ledger. | `capability-registry` |
| `runtime_identity_bridge.py` | Read-only runtime identity bridge with strict, attested, atomic evidence evaluation. | `capability-registry` · `verify-and-evaluate` |
| `runtime_readiness_contract_gate.py` | Static runtime-readiness contract gate. | `structural-lint` |
| `runtime_replay_guard.py` | Fail closed when an attested evidence bundle was already consumed. | `verify-and-evaluate` |
| `runtime_verification_apply.py` | Governed Step-4 runtime-verification promotion. | `verify-and-evaluate` · `apply-as-pull-request` |
| `runtime_verification_harness.py` | Generate and validate a fail-closed runtime verification plan. | `capability-registry` |
| `scene_provenance_ui_guard.py` | Static ratchet: scene provenance must remain visible and fail-honest in both imagery UIs. | `provenance-contract` |
| `service_dependency_conflict_guard.py` | Generate an auditable cross-service dependency conflict report. | `dependency-conflict-inventory` |
| `service_feature_ui_contract_gate.py` | SAHOOL service-feature-ui-contract-gate. | `structural-lint` |
| `service_port_gate.py` | Static service port contract checks for drift-prone services. | `structural-lint` |
| `soil_canonical_store_guard.py` | — | `structural-lint` |
| `soil_full_chain_guard.py` | — | `structural-lint` |
| `soil_lab_projection_guard.py` | Fail closed if durable lab workflow or canonical projection wiring regresses. | `structural-lint` |
| `soil_lab_supersession_lineage_guard.py` | — | `structural-lint` |
| `soil_p1_products_guard.py` | — | `structural-lint` |
| `soil_p2_products_guard.py` | — | `structural-lint` |
| `soil_p3_products_guard.py` | — | `structural-lint` |
| `soil_p4_closed_loop_guard.py` | — | `structural-lint` |
| `soil_p5_certification_guard.py` | — | `structural-lint` |
| `soil_p6_runtime_certification_guard.py` | — | `structural-lint` |
| `soil_profile_contract_guard.py` | Fail CI when governed consumers bypass the canonical soil profile contract. | `structural-lint` |
| `soil_projection_observability_guard.py` | — | `structural-lint` |
| `soil_projection_reconciliation_guard.py` | — | `structural-lint` |
| `soil_runtime_certification_guard.py` | Static ratchet ensuring real-Postgres soil certification remains wired. | `structural-lint` |
| `soil_supersession_current_pointer_guard.py` | — | `structural-lint` |
| `static_governance_closure.py` | Artifact-based closure gate for Path 1 static governance. | `capability-registry` · `apply-as-pull-request` |
| `test_marker_coverage_guard.py` | يمنع وُلود اختبار خامد: ملفّ في ``tests_v9`` بلا علامة لا يعمل في أيّ وظيفة CI. | `unit-tests` |
| `tests_tree_coverage_guard.py` | شجرة ``tests/`` تُشغَّل كاملةً ناقص أساس مُبرَّر — لا بقائمة سماح مكتوبة يدويّاً. | `repository-tests` |
| `unified_production_readiness_gate.py` | Run canonical static production gates and emit one machine-readable verdict. | `unified-readiness-evidence` |
| `v9_feature_transfer_gate.py` | Guard that v9 keeps the runtime features promoted from unified/light. | `structural-lint` |
| `v9_gpu_contract_gate.py` | Static contract gate for SAHOOL v9 RTX 5090/GPU enablement. | `structural-lint` |
| `validate_ci_gates.py` | Validate CI/CD quality-gate coverage for the Sahool release. | `supply-chain-static-scan` |
| `vegetation_agriai_completion_gate.py` | Structural guard for the Vegetation → AgriAI production contract. | `structural-lint` |
| `vegetation_agriai_full_closure_gate.py` | Full-plan closure gate for the Vegetation + AgriAI increment. | `structural-lint` |
| `vegetation_agriai_production_gate.py` | — | `structural-lint` · `contract` |
| `vegetation_container_contract_guard.py` | Guard vegetation-analysis-service container/runtime contract. | `guard` |
| `vegetation_runtime_truth_guard.py` | Fail closed when vegetation runtime regains synthetic field/provider ownership. | `structural-lint` |
| `verify_all_generated.py` | يشغّل **كلّ** خطوات ``--check`` المولَّدة بأمر واحد — وبالترتيب الذي تتطلّبه التبعيّات. | `capability-registry` |
| `waiver_expiry_guard.py` | WAIVER-EXPIRY-GUARD — fail CI once a governance waiver has expired. | `structural-lint` |
| `weather_engine_formula_guard.py` | Guard: vapour-pressure / ET0 formulas live only in the Weather Engine (WS-C.1b boundary). | `structural-lint` |
| `weather_hourly_etc_wx_i1_guard.py` | — | `structural-lint` |
| `weather_service_real_contract_gate.py` | Weather-service real-runtime contract gate. | `field-workspace-closure` |
| `wx11_closed_loop_completion_gate.py` | — | `structural-lint` |
| `wx12_runtime_certification_gate.py` | — | `structural-lint` · `structural` |
| `wx12_runtime_completion_gate.py` | — | `structural-lint` |
| `wx12_runtime_multitenancy_gate.py` | WX-12 multitenancy gate: worker→tenant partitioning must stay server-authorized. | `structural-lint` |
| `wx12_runtime_scheduler_gate.py` | WX-12.3 scheduler gate: monitoring/reconcile scheduling must be durable and actually wired. | `structural-lint` |

---

## مُواصَفة بطفرات ولا يستدعيها أيّ workflow (1)

أداة غير موصولة لا تحرس شيئاً (§٣.٢). وجودها هنا سؤالٌ لا اتّهام.

- `manifest_registry_guard.py`

---

**حدّ الصدق:** هذا يجرد ما تستدعيه الـworkflows بنمط `python scripts/ci/<x>.py`.
حارسٌ يُستدعى عبر `pytest` أو سكربت وسيط أو `bash` **لا يظهر هنا**، ولا يُدّعى غير
ذلك — وعدد البوّابات في §١ أكبر لهذا السبب. ولا يقيس هذا الجرد **جودة** الحارس ولا
تغطيته، بل وجوده وموضعه وهل أُثبِت بالتكذيب.

