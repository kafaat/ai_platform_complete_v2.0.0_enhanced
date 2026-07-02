# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

---

## 2026-07-02 (ك) — دفعة السلامة v29.5-op/v39.5/v19.5 (تحقّق-قبل-بناء متعدّد الوكلاء)

**رأس `main` بعد الجلسة:** `b2a332c`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

بطلب «ابدأ بالدفعة التالية» — بدل بناء أنظمة net-new عمياء، أُطلِقت **٣ وكلاء استكشاف (قراءة فقط)** فتبيّن أنّ معظم كلّ نظام مُغلَق downstream:
- **v29.5-op:** idempotency (v67) + execution_ledger (v68) موجودان؛ device→platform auth ناقص. **الفجوة الحقيقيّة: مفتاح إيقاف التشغيل.**
- **v39.5:** optimistic lock (row_version+409) + offline conflict (409) + v27 trigger على `field_boundaries` موجودة. **الفجوة: `fields.geometry` (متجر الرسم الفعليّ) بلا فحص صلاحية DB.**
- **v19.5:** outbox + processed_events + offline_pending_ops + عقد NATS موجودة. **الفجوة الوحيدة: قفل الكاتب-الأوحد للـworkflow.**

ثمّ **٣ وكلاء بناء متوازين** (worktree، أرقام v133/v134/v135)، ودُمِجت تتابعيّاً بإعادة تحقّق مِنّي (cherry-pick + حلّ تعارضات MANIFEST/run_migrations التافهة):
- **v133** (`e8e4bbe`): `migrations/v133_actuation_killswitch.sql` (RLS+FORCE نمط v98) + `shared/actuation_killswitch.py` (match نقيّ + `is_actuation_halted` fail-closed) موصول عند ٣ نقاط إطلاق: actuator `evaluate_rules` + `/command` (423) + `decision_dispatch` (not_executed). 7 unit + 5 integration.
- **v134** (`94cdda7`): `migrations/v134_fields_geometry_integrity.sql` — trigger `BEFORE INSERT/UPDATE` يفرض `ST_IsValid(ST_GeomFromGeoJSON)` (ERRCODE 23514) على `fields.geometry` + يزيد `geometry_version` inline (مميّز عن row_version وv132). FieldDetail يُخرِج النسخة. v27 لم يُمَسّ. (القرار: تدقيق الهندسة بقي best-effort — الضمان الآن في trigger القاعدة غير القابل للابتلاع؛ الفحص `ST_IsValid` فقط، وحارس الـAPI يبقى يفرض polygon/area.)
- **v135** (`338217c`): `migrations/v135_workflow_state_lease.sql` (`lease_owner`/`lease_expires_at` + partial index) + `PostgresWorkflowStore.claim` بـ`FOR UPDATE SKIP LOCKED` (نمط OutboxWorker) — كاتب أوحد، رفض قابل للالتقاط، استرداد lease منتهٍ. (القرار: `AsyncPostgresWorkflowStore` لم يُغطَّ بعد — متابعة؛ سباق الإنشاء-فقط لا الاستئناف.)

**إثبات (بالاسم، سجلّ CI run 28576997610 job Integration على Postgres حقيقيّ):** ٥ اختبارات killswitch + `test_fields_geometry_db_validity_and_inline_version` + ٣ اختبارات lease + `test_postgres_store_durable_resume` — كلّها PASSED (`54 passed, 99 skipped`، صفر فشل). تطبيق v133/v134/v135 ظهر في سجلّ الترحيلات.

**انضباط:** تعارضات MANIFEST/run_migrations (كلّها append بعد v132) حُلَّت لتسلسل v133→v134→v135 (manifest 142) · فشل CI أوّليّ في format فقط (وكيلان تركا ملفّين غير مُنسَّقين) أُصلِح (`b2a332c`) · **worktrees نُظِّفت** (بقايا جلسات سابقة أعادت عدّ compile الحقيقيّ 1598).

---

## 2026-07-02 (ي) — دفعة متعدّدة الوكلاء: v62.3 (A/B/C) + v52 + v133 + إغلاق Superset

**رأس `main` بعد الجلسة:** `53a3ed4`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء (Integration يُشغّل اختبارات الشقوق الجديدة على Postgres حقيقيّ) ثمّ ff-merge.

بطلب المستخدم «نفّذ الكل بأكثر من وكيل» أُطلِقت **٥ وكلاء متوازين** (worktree معزول لكلٍّ)، ثمّ دُمِج كلّ شقّ تتابعيّاً بإعادة تحقّق كاملة مِنّي (cherry-pick على dev + ruff + pytest + بوّابة) — **لا ثقة بنتيجة وكيل دون إعادة تحقّق**:

- **v62.3-A** (`ea6829e`): `services/ai_agronomist/evidence_contract.py` — `build_ndvi_grid_evidence` (عقد موحّد grid/quality/provenance، لا اختلاق) + `evaluate_machine_readiness` (بوّابة fail-closed: valid_pixel<0.7 أو coverage<0.75 أو مناطق هندسية ⇒ ليست جاهزة؛ cloud>0.35/قِدَم>14ي إنذار). موصولة ببوّابة VRA. ٦ اختبارات.
- **v62.3-B** (`aa0f830`): `raster-service/quality_metrics.py` + كاتب `db_persist`/`_persist_raster_asset` (يعبّئ أعمدة v131) + قارئ `fetch_latest_asset` (+`cloud_cover`). 17 unit + 1 integration (**مرّ على Postgres:** `test_raster_quality_columns_populated_v62_3b::test_quality_columns_round_trip_and_check`).
- **v62.3-C** (`a99f4f4`): `field_ai_context._optional_ndvi_grid` يجلب الشبكة+الجودة من raster (fail-safe) → `imagery_timeline.ndvi_grid/ndvi_grid_quality`؛ `runtime_evidence.pack_ndvi_grid_evidence` يبني العقد؛ `ai_agronomist/main.py` يحقن `ndvi_grid_evidence` لبوّابة VRA. 7 اختبارات. **الوكيل صحّح قاعدته بنفسه** (تفرّع من b87df54 القديم ⇒ أعاد على ea6829e).
- **v52** (`90b0803`): جدول `tenant_ai_policies` **موجود أصلاً** (v124). `sahool-platform/core/ai_policy_envelope.py` يبني المظروف (افتراضيّ الأكثر تقييداً)؛ `ai_agronomist/policy_envelope.py` يرفض بلا مظروف + يمنع external في local_only + يفرض allowed_tools. 13 اختبار. **derived بصدق:** allowed_tools/data_classes/max_bytes بلا أعمدة داعمة (يلزم ترحيل لقوائم قابلة للضبط).
- **v133** (`6ad1872`): `scripts/migrations/report_not_valid_constraint_violations.py` + حارس `test_not_valid_constraint_no_new_violations_guard` (unit + integration؛ **مرّ:** `test_zero_violations_on_migrated_db`) + `docs/runbooks/validate_not_valid_constraints.md`. **لا VALIDATE أعمى** — الفعليّ للمشغّل بعد تقرير+تنظيف.
- **Superset merge = no-op** (وكيل قراءة-فقط + تحقّقتُ بنفسي): `origin/certification/final-readiness-evidence` (`a9f7314`) **سلف خطّيّ** لـmain (0 commit متقدّم، merge-base=cert tip). التوحيد نُفِّذ سابقاً. لا عمل.

**تعارض C↔v52** على `ai_agronomist/main.py`+`field_ai_context.py` دمجه git تلقائيّاً (مناطق مختلفة) وتحقّقتُ دلاليّاً (754 اختبار انحدار أخضر).

**تنظيف:** أُزيلت worktrees الوكلاء (كانت تضخّم مسح compile إلى 18468؛ البصمات نظيفة git-tracked فقط).

**مصفوفة تحقّق (٩ مجالات):** 1–6 (RLS/tenant/MapHub/offline/AI-approval/VRA) مُتحقَّقة عبر ci.yml 11/11 + unit؛ 7–9 (k6/chaos كامل/observability حيّ) أجزاؤها الثابتة خضراء لكنّ الحيّ **يحتاج الستاك المُشغَّل** — لم أدّعِ تشغيله.

---

## 2026-07-01 (ط) — v29.6.1: مراقبة وحُرّاس انحدار MFA (غير حاجب)

**رأس `main` بعد الجلسة:** `b5ee3ce`. الفرع المخصّص مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

بعد بحث المستخدم (OWASP/NIST/PostgreSQL RLS/asyncpg) تأكّد أنّ الإغلاق الاحترافيّ = حُرّاس/عقود لا ترحيلات عشوائيّة. نُفِّذ v29.6.1 (تحسينات اختياريّة، لا إعادة فتح لتصلّب MFA):
- **`f75e363`:** (١) `routers/users.py` يحسب IP مرّة ويمرّره إلى `_verify_caller_mfa(ip=…)` ⇒ أحداث `mfa_stepup_*` تحمل بصمة IP (HMAC) لا NULL. (٢) `_ip_hash` لا يستعمل الحرفيّ الثابت في الإنتاج (`MFA_AUDIT_HASH_KEY`→`JWT_SECRET`؛ لا مفتاح ⇒ NULL لا تجزئة قابلة للتزوير) + إنذار إقلاع غير حاجب. (٣) حارس AST `test_auth_acquire_admin_context_guard` يؤكّد أنّ `_acquire` و`_init_auth_conn` يضبطان `app.current_role='admin'` (يمنع انحدار RLS الصامت بعد RESET ALL).
- **`b5ee3ce`:** حارسان ساكنان على SQL v129 (`test_mfa_migration_contract_guard`): recovery خدمة-فقط بلا `current_user_id`/`current_tenant` · trigger `trg_append_only_mfa_audit_events` (BEFORE UPDATE OR DELETE + `sahool_block_mutation`). يعملان في طبقة unit (بلا DB) فيلتقطان الانحدار أبكر من اختبار التكامل الذي يبقى يثبت السلوك على Postgres حيّ.
- **قرار مفتاح التدقيق:** المنع غير الكاسر (JWT_SECRET fallback قويّ + إنذار) لا بوّابة إقلاع صارمة — لتفادي إسقاط النشرات التي لم تضبط المفتاح المُخصَّص. أيّده المستخدم صراحةً.

**الخارطة المتّفَق عليها بعد v29.6.1 (بترتيب البحث):** SPATIAL-401 (evidence-first، محجوب على Network) · v62.3 عقد أدلّة · v52 policy envelope (platform سلطة، ai_agronomist مستهلِك) · VALIDATE بعد تقارير مخالفات · superset merge يبدأ بجرد (Phase 0) · v29.5-op/v39.5/v19.5 حسب ما يُفعَّل إنتاجيّاً.

---

## 2026-07-01 (ح) — إثبات P0 لـMFA على Postgres حقيقيّ + إصلاح إقلاع auth (mfa_crypto)

**رأس `main` بعد الجلسة:** `46e86eb`. الفرع المخصّص `claude/code-review-34hO3` مطابق. ci.yml 11/11 خضراء ثمّ ff-merge.

### الاختبارات كانت تتخطّى بصمت في CI (تصحيح ادّعاء سابق)
- **`cb4ea31`**: أثبت المستخدم أنّ اختبار تكامل MFA كان **SKIPPED** في CI. السبب: اختباراتي قرأت `DATABASE_URL` بافتراضيّ وهميّ، بينما وظيفة *Integration* تضبط `TEST_DATABASE_URL` (localhost:5433) **وبلا fastapi**. أصلحتُ الأربعة (`test_mfa_hardening_integration_v29_5` + soil-lab/imagery/field_state v57.5) لاستخدام `TEST_DATABASE_URL` + `statement_cache_size=0`. اختبار MFA أُعيدت كتابته: `test_mfa_migrations_applied_on_real_postgres` (asyncpg نقيّ — **يعمل في CI**) + `test_mfa_end_to_end_via_app` (TestClient، `importorskip('fastapi')` — تخطٍّ شفّاف لا صامت).
- **إثبات P0 (لقطة سجلّ CI، run 28553630120 job 84656203554):**
  `test_mfa_migrations_applied_on_real_postgres PASSED [61%]` · `test_v131_applied_on_real_postgres PASSED` ·
  `test_v130_applied_on_real_postgres PASSED` · `= 43 passed, 99 skipped =`. الاختبار الحاسم يثبت على Postgres حيّ: أعمدة/جداول v128 + RLS المُضيَّق v129 (recovery خدمة-فقط بلا self-read · audit يبقي هروب admin) + trigger append-only (probe سلوكيّ داخل tx مُلغى). **بذلك MFA مغلق إنتاجيّاً** (شرط المستخدم: «إذا مرّ هذا الاختبار…»).

### عطل إقلاع auth الحقيقيّ (نفس صنف router_registry/otp)
- **`abf1731`**: بعد `up -d --build` فشلت الحاوية: `ModuleNotFoundError: No module named 'mfa_crypto'` عند `main.py:163`. السبب: `services/auth/Dockerfile` ينسخ ملفّات مفردة ولم ينسخ `mfa_crypto.py` (وحدة v29.5). الإصلاح: `COPY services/auth/mfa_crypto.py`. + **حارس معمَّم** `test_dockerfile_ships_local_sibling_modules` في [`tests_v9/test_decomposed_service_dockerfile_guard.py`](../tests_v9/test_decomposed_service_dockerfile_guard.py): يمسح استيرادات `main.py` المستوى-الأعلى، يحدّد الوحدات الشقيقة الفعليّة (`.py` مجاور)، ويؤكّد نسخها — يلتقط otp.py + mfa_crypto.py اليوم والتالي تلقائيّاً.
- **`46e86eb`**: `ruff format` للحارس (سطر واحد، بلا منطق) + تجديد بصمات الإصدار.

### تشغيليّ (على المشغّل)
- تطبيق الإصلاح: `docker compose -f docker-compose.v9.yml up -d --build sahool-auth` + ضبط `MFA_SECRET_ENCRYPTION_KEY` في `.env`.

---

## 2026-07-01 (ز) — حوكمة الوكيل v58.2 + أدلّة v49.5 + تصلّب MFA v29.5/v29.6 + إصلاحات runtime

**رأس `main` بعد الجلسة:** `4a3f1a4`. الفرع المخصّص `claude/code-review-34hO3` مطابق. كلّ دفعة CI 11/11 خضراء ثمّ ff-merge إلى main.

### حوكمة الوكيل (v58.2 — تقوية أساس v55/v56/v57)
- **v58.2a** (`eb3cf89`): مخازن موافقة/تدقيق قابلة للاستبدال، جاهزة للاستمرار — `services/ai_agronomist/agent_stores.py` (InMemory افتراضيّ · Redis خلف `SAHOOL_AGENT_STORE_BACKEND=redis`، سقوط آمن للذاكرة) + نقطة `/approvals/resume` (تُعيد مغلّف تنفيذ لا تنفّذ داخل الـruntime).
- **v58.2b** (`151851a`): تحقّق وسائط صارم + تعقيم نتائج (ضد تسميم tool-result) — `services/ai_agronomist/tool_governance.py`؛ + ثابت وقت-البناء «كلّ mutating ⇒ requires_approval» في [`shared/ai/tool_registry.py`](../shared/ai/tool_registry.py) وقلب الأدوات الثلاث المتوسّطة؛ + إرشاد schema لأدوات v58 الأساسيّة.
- **v58.2c** (`0b5a13b`): حماية إساءة الحلقة — ميزانية أدوات إجماليّة عبر الجولات + dedupe بـ`tool+input_hash` + إيقاف عند بوّابة الموافقة ([`services/ai_agronomist/tool_loop.py`](../services/ai_agronomist/tool_loop.py) + `ai_generation.py`).

### أدلّة/ذاكرة الحقل (v49.5 — دمج انتقائيّ من حزمة، رفض العودة)
- **v49.5** (`abe0c51`): `services/sahool-platform/api/routers/field_ai_context.py` — `_optional_events` صار tenant-scoped صراحةً (دفاع مضاعف مع RLS) + redaction قبل السياق + ميزانية حجم/عناصر + freshness/provenance. + ترحيل `migrations/v127_evidence_context_hardening.sql` (recommendation_outcomes: RLS WITH CHECK + غلّة غير سالبة). رُقِّم v49_5→**v127** (حارس التكرار) + سُجِّل في MANIFEST/run_migrations. رُفِضت عودة الحزمة إلى ما قبل v58.2a/b (متطابقة بايتيّاً مع السلف `75ba7f9`).

### تصلّب MFA الإنتاجيّ (v29.5 ثمّ v29.6 بعد مراجعة أمنيّة)
- **v29.5** (`8810321`): `services/auth/mfa_crypto.py` (Fernet، مفتاح `MFA_SECRET_ENCRYPTION_KEY` بلا default) + ترحيل `migrations/v128_mfa_hardening.sql` (encrypted_mfa_secret + قفل DB + mfa_recovery_codes hash-only + mfa_audit_events). مسار توافق: مشفّر مُفضَّل → نصّ قديم → ترحيل عند نجاح الدخول (لا يكسر مستخدماً قائماً). `cryptography>=44` (pip-audit نظيف).
- **v29.6** (`4a3f1a4`): إصلاحات مراجعة المستخدم — ترحيل `migrations/v129_mfa_hardening_followup.sql`: تضييق هروب RLS إلى `app.current_role='admin'` (لا `tenant IS NULL` مجرّد) بعد **إثبات** أنّ auth pool يضبطه على كلّ اتّصال ([`services/auth/main.py`](../services/auth/main.py) `_init_auth_conn`:278 + `_acquire`:218) · `mfa_recovery_codes` خدمة-فقط بلا self-read · `mfa_audit_events` append-only (`sahool_block_mutation`). كود: step-up محكوم (`_verify_caller_mfa` بقفل+تدقيق) · التقاط `MfaSecretUndecryptable` (لا 500) · عدّاد فشل ذرّيّ (SQL CASE) · rotation في transaction · HMAC للـIP · key_missing→503 مميّز · جودة مفتاح الإنتاج.

### إصلاحات runtime (من لقطات المستخدم)
- **422 backfill** (`2e353af`): [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx) — «تجهيز سنتين» كان يرسل `'truecolor'` ضمن `indices`، لكنّ `IndicatorKind` في raster لا يحوي truecolor ⇒ 422 pydantic. الإصلاح: ترشيح للمجموعة المدعومة (ndvi/ndmi/…). + حارس ساكن.
- **bandit B613** (`5202907`): `tool_governance.py` احتوى محارف bidi حرفيّة في regex ⇒ CI Security Scan HIGH. أُعيد بناء النمط من code points (لا محارف خام).
- **JWT_SECRET للنبات** (`62989c6`): `docker-compose.v9.yml`/`fixed.yml` لم يمرّرا `JWT_SECRET` لخدمة `sahool-vegetation-analysis` وحدها ⇒ 503 «JWT_SECRET غير مضبوط» على «تحليل الآن» (`services/vegetation-analysis-service/main.py:161`). أُضيف `JWT_SECRET` + `JWT_PUBLIC_KEY` (كبقيّة الخدمات).

### مفتوح (موثَّق)
- **SPATIAL-401:** «المؤشرات المكانية» تُخرج للدخول (raster `/indicator-grid` 401) — يحتاج status+body من Network للتشخيص (لم يُخترَع إصلاح).
- **AUTO-SEG:** «تحديد الحدود تلقائي» 503 مقصود (SAM2 غير منشور؛ `docker-compose.fixed.yml:1076-1084`).
- **v57.5-DB (مفتوح فعلاً):** soil_lab analyte schema (v50) · imagery quality metadata (v54) · field_state recompute contract (v53) · tenant AI policy DB-backed (v52) — تحتاج Postgres، يُتحقَّق عبر CI.

### صدق ومنهج
- كلّ دفعة: `pytest -m unit` أخضر (2186→2215) + ruff + manifest + CI 11/11 (Integration يطبّق كلّ ترحيل على Postgres+PostGIS حقيقيّ) ثمّ ff-merge.
- تكرّر درس «الفجوة مُغلَقة أصلاً»: عند مراجعة v9–v57 تبيّن أنّ معظم P0 (RLS WITH CHECK عبر v70 · حارس RLS القائم · ID TEXT v18 · حوكمة الأوامر v100+) مُنجَز downstream — تحقّقتُ قبل التنفيذ تفادياً لعمل مكرّر.

---

## 2026-06-29 (ر) — إصلاح Docker Compose الكامل + تحقّق CDSE end-to-end

**رأس الفرع:** `db08e63`. جلسة متواصلة من (ق) — سقط السياق فأُعيدت.

### إصلاحات Docker Compose (startup failures)
- **weather-polygon-worker/weather-signal-engine:** Dockerfile ينقصه `COPY core/thresholds.py` ⇒ `ModuleNotFoundError: core.thresholds` ← أُضيف.
- **raster-tiler-service:** `python:3.12-slim` ينقصها `libexpat1` (تتطلّبها rasterio/GDAL) ⇒ `ImportError: libexpat.so.1` ← أُضيف `apt-get install libexpat1`.
- **sahool-platform:** `SAHOOL_ENV=production` + غياب `JWT_PUBLIC_KEY` ⇒ `sys.exit(1)` من حارس RS256 ← ثُبّت `SAHOOL_ALLOW_HS256_IN_PROD=1` في `.env` + ثُرّر المتغيّر عبر compose.
- **nginx:** ثلاثة أخطاء: (1) `proxy_http_version` مكرّر في `/ws/` ← حُذف المكرّر. (2) `proxy_pass` له URI في `@spa_fallback` ← استُبدل بـ`rewrite+proxy_pass`. (3) healthcheck يحلّ `localhost→::1` (IPv6) لكن nginx `listen 80;` فقط ← أُضيف `listen [::]:80` + `listen [::]:443 ssl http2`. (4) `nginx/ssl/` فارغ ← أُنشئت شهادة self-signed (10 سنوات).

### CDSE Satellite Imagery (end-to-end)
- **root cause 1 — FieldIndicatorMap:** كانت دائماً تستدعي `/tilejson` (COG محلّيّ) حتّى في وضع CDSE ⇒ `available=false` لحقل بلا COG ← صارت تستدعي `/cdse-tilejson` حين `tileSegment='cdse-tiles'`.
- **root cause 2 — SatellitePage:** لم تُمرّر `tileSegment="cdse-tiles"` إلى `FieldIndicatorMap` ← أُضيفت لكلا الوضعَين (NDVI + truecolor).
- **root cause 3 — cdse-tilejson:** كانت روابط البلاطات بلا بادئة nginx (`/v1/` لا `/api/raster/v1/`) ← صُحِّحت. + أُضيف `reason/user_message` عند غياب الاعتماد.
- **root cause 4 — cdse_client:** يقرأ `CDSE_CLIENT_ID` فقط؛ compose يُعيّن `SH_CLIENT_ID` ← أُضيف ارتداد `SH_CLIENT_ID/SECRET` في `_cdse_credentials()`.
- **تعارض git pull:** حُلّ في `FieldIndicatorMap.tsx` + `cdse_tiles.py` ← commit `db08e63`.
- **nginx re-resolve:** بعد إعادة تشغيل auth، nginx احتفظ بـIP قديم ← `nginx -s reload` أعاد الحلّ.
- **تحقّق نهائيّ ✓:** `cdse-tilejson?index=ndvi` + `?index=truecolor` عبر nginx + JWT ⇒ `{"available":true, "tiles":["/api/raster/v1/fields/…/cdse-tiles/…"]}`.

### الحاويات غير الصحيّة المتبقّية (pre-existing, لا علاقة بـCDSE)
`actuator-dispatch-worker`, `model-registry-worker`, `phase-runtime-outbox-worker`, `plugin-runtime-worker` — تعمل وظيفيّاً (تسجّل `{"processed":0}`) لكن healthcheck يتوقّع `http://localhost:8000/readyz` وهم لا يُشغّلون خادم HTTP. مشكلة تعريف healthcheck، لا تعطّل وظيفيّ.

---

## 2026-06-29 (ق) — تتبّع جنائيّ: «المؤشّرات لا تُعرَض» في MapHub + فخّ اعتماد CDSE

**رأس الفرع المخصّص:** `a37ce64`. لقطة المستخدم: حقل مرسوم، الطبقة NDMI «نشطة»، لكن لا تراكب راستر.
تتبّع كامل (خدمة الراستر → الواجهة → البوّابة → المزوّد) كشف عيبَين حقيقيَّين + فخّ تهيئة:

- **🔑 الواجهة (السبب الجذريّ لـMapHub):** `HubMap.tsx`/`HubMapGL.tsx` كانا يبنيان رابط بلاطة المؤشّر على
  المسار المحلّيّ `/v1/fields/{id}/tiles/` (COG مُسبق-التوليد) ⇒ **404 لحقل بلا معالجة ⇒ شفّاف ⇒ لا مؤشّر**
  (فجوة MAPHUB-CDSE). حُوِّلا إلى `/cdse-tiles/` الحيّ + bbox + قصّ `poly` (قناع rasterio)، مع حفظ عقد
  التاريخ D. + `FieldIndicatorMap.tsx` كان يبوّب الطبقة على `/tilejson` المحلّيّ حتّى في وضع CDSE ⇒ يحجبها
  دائماً لحقل CDSE-فقط؛ صار يسأل `/cdse-tilejson` حين `tileSegment='cdse-tiles'`.
- **🔑 الخادم (سبب جذريّ حين يبدو CDSE مُهيّأً وهو ليس كذلك):** `cdse_client` يقرأ `CDSE_CLIENT_ID/SECRET`
  **فقط**، بينما compose يُعرّف أيضاً `SH_CLIENT_ID/SECRET` (تُلزِمها خدمة أخرى بـ`:?`) لنفس realm الـCDSE.
  مشغّل ضبط `SH_*` دون `CDSE_*` ⇒ بلاطات شفّافة صامتة. أُضيف ارتداد `SH_*` في `_cdse_credentials()`
  يستخدمه `is_configured()`+`_fetch_token()`. + `cdse-tilejson` يُرجِع `reason=cdse_not_configured`+رسالة
  للمشغّل (لا فشل صامت).
- **تحقّق المزوّد ✓:** `SH_BASE_URL`/`SH_TOKEN_URL` يشيران إلى Copernicus فعلاً
  (`sh.dataspace.copernicus.eu` · `identity.dataspace.copernicus.eu/.../CDSE`)؛ NDMI مؤشّر مدعوم؛ توجيه
  nginx `/api/raster/` سليم (يقرأ tenant من `tid`/`tenant_id`/ترويسة). **لا حجب من السكربت** — يُرجِع
  شفّافاً برشاقة عند: غياب الاعتماد · مؤشّر غير مدعوم · تعذّر CDSE.
- **⚠ تصحيح صدق:** ادّعائي السابق أنّ فروع CDSE الخمسة «مُستبدَلة 100%» **كان خاطئاً** لـHubMap تحديداً —
  فرع `cdse-maphub-ws-fixes` حمل إصلاح `indicatorTileUrl→cdse-tiles` الذي **لم يدخل main** في التوحيد
  (دخل backend الراستر + FieldIndicatorMap، لا HubMap/HubMapGL). لحسن الحظّ تعذّر حذف الفروع (403) فلم
  يُفقَد الإصلاح. **الدرس:** تحقّق ملفّ-بملفّ لا معلَم-عيّنة قبل وصف فرع «مُستبدَل»؛ معلم واحد حاضر لا يعني
  الكلّ. تحقّق: tsc نظيف · maphub vitest 29 · raster cdse 14 · `pytest -m unit` 1973 · SH-only⇒configured.

---

## 2026-06-29 (ص) — rate limit موزَّع بـRedis (#6) + تحقّق فروع CDSE العالقة (ج)

**رأس الفرع المخصّص:** `c2af2e6` (= `main` بعد الدمج المؤتمت).

- **#6 (rate limit → Redis، باختيار المستخدم «أ»):** `rate_limit_middleware` كان عدّاداً in-process لكلّ
  عامل ⇒ مع N عمّال الحدّ الفعليّ N×المضبوط. أُضيف عدّاد Redis مشترَك (`INCR`+`EXPIRE 60s` لكلّ مفتاح عميل)
  يُختار عند الإقلاع متى توفّر `REDIS_URL` حيّ؛ النداء المتزامن عبر `asyncio.to_thread` (لا يحجب الحلقة).
  **ليس fail-closed** (حاجز DoS لا بوّابة أمن): أيّ خطأ Redis/غياب `REDIS_URL` ⇒ تدهور رشيق إلى العدّاد
  in-process (محفوظ حرفيّاً). اختبارات: الموجودة مُثبَّتة على in-process (`_RATE_REDIS=None`) للحتميّة +
  اختبارا مسار Redis (حجب فوق الحدّ + `EXPIRE` مرّة + عزل المفاتيح) + fail-open. `pytest -m unit` 1973 ✓.
- **ج (حذف فروع CDSE العالقة):** فحصتُ ٥ فروع (`frontend-cdse-hide-date`/`fix-cdse-clip-to-field`/
  `claude/frontend-cdse-omit-latest-date`/`claude/cdse-maphub-ws-fixes`/`claude/brain-update-decompose-cdse`).
  **ليست ancestors لـmain** (لكلٍّ ١–٤ commits فريدة) لكنّ **محتواها مُستبدَل بالكامل في main** (تحقّقتُ من ٦
  معالم: `fetch_field_geometry`+RLS · `apply_polygon_mask` · عقد `poly=` · توجيه nginx للراستر · WebSocket
  الإشعارات · روابط CDSE في الواجهة — كلّها حاضرة، وبعضها أكمل عبر التوحيد). **الحذف حجبه المصنّف** (يتطلّب
  تسمية المستخدم الصريحة للفروع) — أُحيل القرار للمستخدم بأسماء الفروع + دليل الاستبدال. لا أحذف عملاً غير
  مدموج بقرار ذاتيّ.
- **درس:** «stale/superseded» ≠ «merged». الفرع قد يحمل commits فريدة ومحتواها مع ذلك مُعاد تطبيقه في main
  (التوحيد التوفيقيّ يُعيد الكتابة لا الـcherry-pick) — تحقّق من المحتوى لا النسب قبل وصفه «آمن للحذف».

---

## 2026-06-29 (ف) — تحصين JWT RS256: المنصّة + ٨ خدمات ترفض HS256 في الإنتاج

**رأس الفرع المخصّص `claude/code-review-34hO3`:** `ddd2434`. مراجعة جنائيّة للمستخدم لنسخة zip كشفت
فجوات؛ تحقّقتُ من كلٍّ بالكود الفعليّ (بعضها صحيح، بعضها غير قابل لإعادة الإنتاج).

- **🔑 #1 (حرج، مُصلَح `030c01a`):** `services/sahool-platform/api/main.py` كان يتحقّق HS256-فقط بلا مسار
  `JWT_PUBLIC_KEY` ⇒ **لا يستطيع التحقّق من توكنات auth الـRS256 في الإنتاج** (auth صُلّب لـRS256 سابقاً) ⇒
  كسر مصادقة عابر-خدمات. المنصّة تقبل `iss in {sahool-auth, sahool-platform}` فيجب أن تتحقّق ممّا يوقّعه auth.
  الإصلاح (محاكاة auth): `JWT_PUBLIC_KEY`/`JWT_VERIFY_KEY`/`JWT_VERIFY_ALGORITHM`؛ مسارا التحقّق
  (`get_current_user` + إبطال `auth_logout`) صارا RS256-واعيَين؛ حارس `_refuse_hs256_in_production` يرفض
  الإقلاع في الإنتاج بلا RS256 (مهرب `SAHOOL_ALLOW_HS256_IN_PROD=1`). `create_token` يبقى HS256 (مُصدِر dev،
  مُعطَّل في الإنتاج). اختبار: جدول الرفض + **دورة RS256 عابر-خدمات حقيقيّة** (توقيع خاصّ→تحقّق عامّ).
- **#7 (اتّساق، مُصلَح `ddd2434`):** ٨ خدمات تتحقّق JWT صارت ترفض HS256 في الإنتاج (حارس إقلاع موحَّد،
  `raise RuntimeError`، يُدرَج بعد `_ALLOWED_ISS` — مرساة موحَّدة في كلّها). actuator/guardrails/local-ai-rag/
  odoo/tts/video/supervisor كان لها مسار RS256 (تنقصها بوّابة الإنتاج فقط)؛ **vegetation-analysis-service**
  كان **HS256 مُصمَّت بلا مسار RS256 أصلاً** (نفس صنف #1) فأُضيف لها المسار الكامل + الحارس. حارس مصدريّ جديد
  `test_services_rs256_production_guard.py` (٨ خدمات) يمنع الانحدار.
- **تصحيحات صادقة للمراجعة:** **#3 (MANIFEST «Canonical source»)** و**#4 (.env placeholder test)** **غير قابلتَين
  لإعادة الإنتاج** على `main` الحاليّ — لا نصّ/اختبار بهذا الاسم؛ اختبارات الـmanifest/placeholder (26) خضراء.
  لقطة zip أقدم. **#2 (Phase 9–12)** سليم ✓. **#6 (rate limit in-process)** صحيح لكن **موثَّق في الكود**
  (`N2: حالة في الذاكرة`) — تغيير Redis مؤجَّل. **#5** تفكيك مستمرّ.
- **القرار التصميميّ:** حارس الإقلاع import-time (لا request-time) — أبسط (موضع واحد/خدمة لا لكلّ بوّابة تحقّق)
  وfail-closed عند الإقلاع؛ لا يُطلَق في CI (لا اختبار يستورد هذه الخدمات بـ`SAHOOL_ENV=production` — تُحُقِّق).
  استُعمل `os.getenv("JWT_PUBLIC_KEY")` مباشرةً (لا متغيّر الوحدة) فالكتلة **متطابقة** في الخدمات السبع.
- **درس:** المسح الذاتيّ كشف خدمة عاشرة (`vegetation`) فاتت المراجعة الجنائيّة — `grep jwt.decode` على كلّ
  الخدمات أوسع من قائمة المراجِع. تحقّق دائماً من الادّعاءات بالكود (بعضها بائت من نسخة أقدم).

---

## 2026-06-29 (ع) — تفكيك main.py للمنصّة (استخراج النماذج) + إصلاح حارس المصدر

**رأس الفرع المخصّص `claude/code-review-34hO3`:** `044e1ff` (CI `ci.yml` أخضر). `main` المحلّيّ `c8fc78b`
(مدموج فيه؛ الدفع المباشر لـmain محجوب بالمصنّف — التطوير يبقى على الفرع المخصّص).

- **استخراج نماذج Pydantic من `main.py` (P0):** نُقِل ٧٣ صنف `BaseModel` من
  [`services/sahool-platform/api/main.py`](../services/sahool-platform/api/main.py) (3282→2735 سطراً) إلى
  وحدة جديدة [`services/sahool-platform/api/api_models.py`](../services/sahool-platform/api/api_models.py)
  (664 سطراً، بترتيب المصدر/AST فالنماذج المتداخلة تسبق مستهلكيها)، ويُعاد استيرادها عبر
  `from api.api_models import (...)  # noqa: E402,F401`. أُبقيت ٤ معالِجات `@app` ووصل `register_routers`.
- **🔑 الإصلاح (هذه الجلسة):** حارس المصدر
  [`tests_v9/test_disease_field_state_feed.py`](../tests_v9/test_disease_field_state_feed.py)`::test_diagnose_request_has_optional_field_id`
  كان يمسح `main.py` فقط بـ`src.index("class DiagnoseRequest(")` ⇒ `ValueError: substring not found` بعد
  نقل النموذج إلى `api_models.py` (كسر CI run #2532 على `a806251`: 1 failed/1600 passed). الحلّ: مسح
  `main.py` **و** `api_models.py` (نفس نمط `_func_src` للمعالِجات المنقولة) دون إضعاف تأكيد
  `field_id: str | None = None`. تحقّق: ٦/٦ في الملفّ خضراء · `pytest -m unit` كامل = **1950 passed**
  (الـ٧ أخطاء الوحيدة = `nats.aio` غائب محلّيّاً، تنجح في CI).
- **تجديد بصمات الإصدار:** غيّر ملفّ الاختبار بصمته ⇒ أُعيد توليد `release/FILE_CHECKSUMS.sha256`
  (+manifest/SBOM) بـ`build_release_bundle.py` لإبقاء بوّابة Phase 14 خضراء.
- **التوقيع:** الالتزامان المدفوعان (`c8fc78b`+merge `044e1ff`) موقَّعان SSH (ترويسة `gpgsig`)؛ تحذير
  `%G?`=N محلّيّ فقط (غياب `allowedSignersFile`؛ ملفّ المفتاح العامّ 0 بايت) — GitHub يتحقّق خادميّاً.
- **درس:** أيّ نقل لرمز يمسحه حارس مصدر نصّيّ (`.index`/`.find`) يجب أن يوسّع نطاق المسح للوحدة الجديدة
  — شغّل **كامل** `tests_v9 -m unit` لا عيّنة المنصّة وحدها (التحقّق السابق فوّت هذا الحارس).
- **تفكيك دلاليّ إضافيّ (`d6d4b0d`، باختيار المستخدم «تفكيك دلاليّ إضافيّ»):** استُخرِج عنقود **السياق
  الزراعيّ للحقل** (٧ دوالّ + `_STAGE_DAY_BOUNDS`: `_field_weather_context`/`_field_season_context`/
  `_latest_soil_moisture`/`_historical_rain_3d_mm`/`_growth_stage`/`_resolve|_load_recommendation_policy`)
  من `main.py` إلى وحدة جديدة [`api/field_context.py`](../services/sahool-platform/api/field_context.py)
  (main.py 2735→**2523**). عنقود مشترَك بين موجِّهات (fields/recommendations/field_completeness) ⇒ وحدة
  مشترَكة لا router واحد. **بلا دورة استيراد:** كلّ دالّة DB تستقبل `conn` كمعامل (لا اقتران بمجمّع main)
  وكلّ استيراد ثقيل كسول داخل الدالّة. يُعاد التصدير من `api.main` (`# noqa: E402, F401`) فتبقى نقاط
  `from api.main import …` صحيحة. حارس جديد
  [`test_field_context_decomposition_guard.py`](../tests_v9/test_field_context_decomposition_guard.py)
  يثبّت: التعريف في field_context لا main + إعادة التصدير بنفس هويّة الكائن. تحقّق: 526 مساراً ثابتاً ·
  ruff نظيف · `pytest -m unit` 1950 ✓ · inspector router-wiring PASS.
- **سبب اختيار هذا العنقود (لا غيره):** محرّك التنبيهات (`_evaluate_field_alerts_persist`) **يبقى** في main
  عمداً (موثَّق في `alert_models.py`) لاقترانه بـ`tenant_connection`/مساعِدات main ⇒ نقله يخلق دورة. نماذج
  Pydantic النقيّة سبق نقلها. عنقود السياق هو الوحيد المتبقّي القابل للنقل النظيف (conn معامل + كسول).

---

## 2026-06-29 (س) — توحيد main + فرع الاعتماد Phase 1–22 + السبب الجذريّ لـauth

**رأس `main` بعد الجلسة:** `96003bf`. الفرع المخصّص `claude/code-review-34hO3` = `c0174e6` (مطابق لـmain).

اكتشف المستخدم أنّ `main` (عمل الجلسات) وفرع `certification/final-readiness-evidence` **افترقا**
من القاعدة `89d848e` — كلّ خطّ يحمل عملاً فريداً. القرار: **توحيدهما** في superset واحد.

- **التوحيد (54 commit فوق main السابق):** دمج `certification` (Phase 1–22 · ترحيلات v99–v123 ·
  `sahool-production-gates.yml` · وحدات runtime — 470 ملفّاً) مع عمل main (تفكيك · CDSE poly ·
  H5/C5/H2 · بوّابة الواجهة). 22 تعارضاً: الإضافيّ آليّاً؛ المتداخل بقاعدة cert المتقدّمة + اتّحاد.
- **Stage B (CDSE فوق cert):** أُعيد `apply_polygon_mask`+`fetch_field_geometry`(RLS) + تفعيل راوتر
  `cdse-tiles` + باني `fieldCdseTileUrl` (واجهة) + إعادة D في الموضعَين.
- **Stage C (تفكيك):** أُعيد تفكيك video/odoo/raster (cert المصلّبة) إلى `routers/` مع **حفظ تصليب
  cert** + استعادة الحُرّاس الثلاثة. كلّ الـ11 خدمة مُفكَّكة الآن.
- **🔑 السبب الجذريّ لـauth «unhealthy» (سجلّ المستخدم حسمه):** `main.py` يستورد
  `from router_registry import register_routers`، لكنّ Dockerfile auth (وvegetation) ينسخ ملفّات
  مفردة لا المجلّد ⇒ `ModuleNotFoundError: 'router_registry'` ⇒ uvicorn يفشل ⇒ الحاوية unhealthy.
  **ليست RLS/JWT** (فرضيّاتي السابقة كانت خاطئة — لم يكن لديّ السجلّ). أُصلِح: Dockerfile ينسخ
  `router_registry.py`+`routers/` + **حارس CI** `test_decomposed_service_dockerfile_guard` يمنع التكرار.
- **إصلاحات CI (بعد الدمج):** مفتاح `DATABASE_URL` مكرّر في `docker-compose.v9.yml` (أثر دمج) ·
  frontend TS (`tileSegment` props) · PyYAML في وظيفة المفتّش · ruff format · **تجديد بصمات الإصدار**
  (`build_release_bundle.py` — 85 ملفّاً تغيّر بصمتها بعد الدمج، فحص Phase 14 رصدها).
- **توحيد الفروع:** دُمج main في الفرع المخصّص `claude/code-review-34hO3` (شجرة مطابقة) + أُغلِق
  PR #579 (كان يتعارض في `cdse_tiles.py`؛ مُتجاوَز). 0 PR مفتوح · 0 تعارض.
- **درس:** الدمج التوحيديّ يغيّر بصمات كثيرة ⇒ جدّد حزمة الإصدار. والاختبارات تستورد main من مجلّد
  الخدمة فلا تكشف نقص Dockerfile — حارس Dockerfile الجديد يسدّ الفجوة.

---

## 2026-06-28 (ن) — بوّابة الواجهة + إغلاق متابعتَي D/C من مراجعة النسخة + تشخيص auth

**رأس `main` بعد الجلسة:** `63c2f03` (#577 آخر المدموجة). PRs مدموجة: **#574–#577** (٤).

- **#574 (`b180553`)** — تحديث العقل (تفكيك SVC-DECOMP-2: #570–#573).
- **#575 (`35a4565`) بوّابة الواجهة التطويريّة (frontend/nginx.conf، 3003):** إضافة ٥ كتل
  `location ^~` **قبل** catch-all `/api/` للخدمات التي تناديها `api.ts` بقواعد خاصّة
  (`vegetation`→`sahool-vegetation-analysis:8000/` · `indicators`/`weather`→`sahool-platform:8000/api/v1/…`
  · `agent`→`sahool-supervisor-agent:8000/agent/` + `= /api/agent/health`→`/health` · `guardrails`→
  `sahool-guardrails-engine:8000/`). بلا `auth_request` (نموذج تطوير؛ تمرير `Authorization`+`X-Tenant-Id`)؛
  الأهداف مطابقة لـ`nginx.v9.conf`. **الفجوة مُثبَتة:** بلاها تسقط لـ catch-all ⇒ 404 (دردشة/غطاء/مؤشّرات/طقس).
  حارس `test_frontend_nginx_service_proxy_guard.py`.
- **مراجعة المستخدم للنسخة `008c330`:** أكّدتُ كلّ ادّعاءاتها **صحيحة** بالكود (D/C/B + ملاحظات بيئيّة).
  أُغلِقت المتابعتان الصغيرتان القابلتان للتنفيذ هنا (B — journal دائم للوكيل — مؤجَّل كـPR مستقلّ):
  - **#576 (`2244145`) D — عقد TileJSON (واجهة):** `FieldIndicatorMap.tsx` كان يبني طلب TileJSON بـ
    `params:{index,date}` بلا شرط ⇒ تسريب `date=latest`/`date=`. صار مشروطاً
    (`date && date!=='latest' ? {index,date} : {index}`) — نفس حارس باني رابط البلاطة. backend يتحمّل ⇒
    تنظيف عقد لا كسر. حارس ساكن `test_frontend_tilejson_date_contract_guard.py` (٤).
  - **#577 (`63c2f03`) C — الموضوع اليتيم (NATS):** `sahool.weather.field.overlay.completed` يَنشُره
    `weather-polygon-worker:161` بلا مشترِك ⇒ WARN «حدث طريق مسدود» (غير حاجب). **توثيق** القرار:
    قسم `published_no_consumer` في عقد الأحداث (منتِج فعليّ + سبب) + `check_nats_subjects` يحترمه
    (WARN⇒PASS) دون إضعاف `CRITICAL`/H2. +٣ اختبارات (سلبيّ: إزالة الـwaiver تُعيد WARN).
- **تشخيص (لم يُغلَق — ينتظر سجلّ المشغّل):** `v21-sahool-auth-1` **unhealthy** يمنع إقلاع الحزمة.
  `/readyz` موصول صحيحاً (`routers/ops.py:31`+`register_routers`) ⇒ **ليست انحدار تفكيك #557**. السبب
  runtime/config: lifespan يرفع `RuntimeError` (fail-closed). الأرجح **دور قاعدة يتجاوز RLS** (DATABASE_URL
  كـsuperuser/مالك جداول ⇒ `assert_db_role_rls_safe` يرفض الإقلاع — `main.py:229`)؛ الإصلاح دور مقيّد
  `sahool_app` أو `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` للتطوير. بدائل: `JWT_SECRET`<32، أو فشل `_ensure_admin_user`.
- **صدق:** D/C تنظيف+توثيق لا تغيير سلوكيّ؛ تشخيص auth **لم يُحسَم** بلا السجلّ (تفادي إصلاح أعمى).

---

## 2026-06-28 (م) — تفكيك ٤ خدمات أصغر (soil/tts/actuator/guardrails، #570–#573)

**رأس `main` بعد الجلسة:** `d340e60` (#570 آخر المدموجة من الدفعة). PRs مدموجة: **#570–#573** (٤).

إكمال تفكيك بقيّة `main.py` المتجانسة (٦–٧ مسارات لكلٍّ — دون عتبة ≥٨ السابقة لكنّ المستخدم طلب
إكمالها). **٤ وكلاء متوازون (worktree)**، نفس نمط raster/auth (`router_registry` + `_include_flat`
+ حارس تفكيك)، **نقل بنيويّ صرف محفوظ السلوك، عدد المسارات ثابت**:
- **#571 (`7f642a2`) tts-service:** ٧ معالجات → وحدتان (11 ثابتة). حارس `test_tts_notification_service_auth` (مسح `Cache-Control` المنقول) ⇒ مساعِد مُجمِّع.
- **#572 (`bcb6c15`) actuator-service:** ٦ → ٣ وحدات (10، **حسّاس**: `/command` + تفويض جهاز مطابق بايتاً). حارسان أمنيّان (`test_security_review_fixes`/`test_roadmap_phase23`) أُعيد توجيههما بمساعِد مُجمِّع — يقبل `Depends(_verify_token)` أو `Depends(main._verify_token)` (نفس الفرض).
- **#573 (`b4c0be6`) guardrails-engine:** ٧ → وحدتان (11، **حوكمة `/validate` حسّاسة**). `_require_service_token` مطابق بايتاً؛ حُرّاس `test_ai_orchestration_safety` أُعيد توجيهها (بل قُوِّي تأكيد) بمساعِد مُجمِّع.
- **#570 (`d340e60`) soil-service:** ٦ → وحدتان (10). **CI كشف كسرين حقيقيّين فات الوكيل اكتشافهما** (لا يشيران لـmain.py بالحرف):
  1. `test_soil_field_tenant_authz` يمسح `main.py` عن `resolved_tenant` ويستدعي `main.ingest_reading` (انتقلا لـ`routers/readings.py`) ⇒ **إعادة تصدير** المعالجات من `main` (ربط اسم، لا تسجيل مسار ثانٍ) + مساعِد مُجمِّع `soil_route_source.py` + **إسقاط وحدات `routers/` في إعادة استيراد الـfixture** (وإلّا تُبقي مرجعاً لـmain متعفّن عبر الاختبارات).
  2. `test_tenant_query_audit` — استعلام `soil_readings` RAW انتقل لمسار جديد ⇒ تحديث مفتاح allowlist في `scripts/tenant_query_audit.py`.
  **بلا إضعاف أيّ تأكيد** (اختبارات IDOR/عبر-المستأجرين تمرّ — تحقّقتُ بـpytest-asyncio: 14/14).

- **درس CI متكرّر:** حُرّاس `tests_v9` التي تمسح/تحمّل مصدر خدمة تتأثّر بالتفكيك بطرق متعدّدة (مسح نصّ · `hasattr` على main · تحميل وحدة بالمسار · allowlist مُفتَّح بالمسار). الحلّ المُثبَت: مساعِد مصدر مُجمِّع + إعادة تصدير عند اللزوم + تنظيف sys.modules — لا إضعاف للحراسة. **الوكلاء يفوّتون أحياناً الحُرّاس غير المُشيرة لـmain.py بالحرف؛ CI يلتقطها فتُصلَح.**

- **صدق:** كلّ تفكيك مُتحقَّق (`import main` + ثبات العدد + الحارس + ruff)؛ الإصلاحات الأمنيّة موسّعة-النطاق لا مُضعَّفة.

---

## 2026-06-28 (ل) — إغلاق H5/C5/H2 كسياسات قرار + إصلاح القصّ الجذريّ (#564–#568)

**رأس `main` بعد الجلسة:** `008c330` (#568 مُدمج). PRs مدموجة: **#564–#568** (٥ PRs).

- **#564 (`d9d9694`) — MapHub/CDSE/WebSocket + السبب الجذريّ للقصّ:** اكتشاف المستخدم أنّ
  `fetch_field_geometry` كان يستعلم `fields` **بلا `set_config('app.current_tenant')`** ⇒ RLS يحجب
  الصفوف ⇒ `geometry=None` ⇒ لا قصّ (بلاطات bbox). أُصلِح (يحلّ المالك عبر `sahool_field_owner_tenant`
  SECURITY DEFINER ثمّ يضبط السياق). + عقد **`poly`** الموحَّد (واجهة+خادم) + **قناع rasterio بكسليّ
  دقيق** (`tile_render.apply_polygon_mask`) + مؤشّر ملوحة **SWIR** `(B11-B12)/(B11+B12)` (كان NDVI
  معكوساً) + نطاق ألوان مُصحَّح + نافذة «أحدث» ٦٠ يوماً + تشخيص سبب البلاطة الشفّافة. حارس عقد
  [`test_cdse_poly_contract.py`].
- **#565 (`ba29bba`)** — تحديث العقل لسلسلة #552–#564.
- **إغلاق الفجوات الثلاث كسياسات قابلة للضبط والاختبار (لا «كود فقط»، بحسب توجيه المستخدم):**
  - **#566 (`e6f98f5`) H5 — سياسة الريّ المشروطة بالملوحة:** `net` دائماً + Ks عند توفّر EC موثوق +
    غسل **مشروط** (ECw+صرف+كفاءة)؛ ٤ سياسات + `requires_expert_review`. غلاف فوق
    `irrigation_advice`/`fao56.leaching_requirement` (مصدر واحد). راوتر `POST /api/v1/irrigation-recommendation`
    (لا يكسر `/water-balance`). ٦ اختبارات قبول. **مصدر EC:** `soil_lab_tests` عبر `gather_field_freshness`.
  - **#567 (`273ee34`) C5 — سياسة دليل NDVI:** يوسم دور NDVI (`informational`/`supporting`/
    `decision_blocking`)؛ **الافتراضيّ `supporting`** (لا يحجب قراراً وحده)؛ الحجب فقط بمعايرة محليّة +
    سياق محصول كامل + جودة مشهد. حارس بنيويّ: `resolve_field_state` يأخذ عُمر NDVI لا قيمته. ١٤ اختباراً.
  - **#568 (`008c330`) H2 — عقد ناشري الأحداث + حارس عكسيّ:** `event_publish_contracts.yaml` يربط كلّ
    موضوع مُستهلَك بمنتِج (outbox) أو waiver؛ `check_nats_publisher_coverage` (مُسجَّل في CHECKS) يفشل على
    «مُستهلَك بلا منتِج/waiver» — يمسح `services/`+`agents/` وقائمة `SUBSCRIPTIONS` (AST). **أثبت قيمته:**
    كشف `sahool.weather.forecast.updated` الذي فات الفحص القديم (services فقط). لا تقليم اشتراك، لا اختلاق.
- **درس CI:** إضافة فحص إلى `CHECKS` كسر اختبار `test_sahool_inspector` المُصلَّب على `== 5` ⇒ غُيّر إلى
  `== len(CHECKS)` (يصمد). + درس سابق: نسيت إنشاء فرع H2 فالتزم على فرع C5 ⇒ نُقِل بـcherry-pick + reset.
- **صدق:** H5/C5 يبقيان `fixed` لا `verified` (يحتاجان معايرة ميدانيّة: عيّنات EC + عتبات NDVI لمحاصيل اليمن).
  السبب الجذريّ للقصّ (RLS) كان **اكتشاف المستخدم** — وُثِّق وأُصلِح في المصدر لا في عَرَض.

---

## 2026-06-28 (ك) — إكمال raster/CDSE (#552–#559) + إغلاق فجوات + تفكيك ٤ خدمات (#560–#563) + MapHub/WS (#564)

**رأس `main` بعد الجلسة:** `7a36511` (#563 مُدمج). PRs مدموجة هذه الجلسة: **#552–#563** (١٢ PR). **مفتوح:** #564 (قيد CI).

- **إكمال سلسلة raster (#552–#559):**
  - #552 (`a3b29ff`) واجهة: حذف `date=latest` المثبَّت من روابط بلاطات CDSE.
  - #553 (`df02c06`) nginx: وكيل `/api/raster/` لبوّابة الواجهة 3003 **بلا** `auth_request` (بوّابة تطوير خفيفة؛ تمرير `Authorization`/`X-Tenant-Id` صراحةً — لا تكرار منطق بوّابة الإنتاج).
  - #554 (`efea4c6`) وثيقة: جدول مقارنة `v9 ↔ fixed` مُتحقَّق بالملفّ.
  - #555 (`f2d5f0b`) تحديث العقل (لسلسلة #550/#551 + الاسترجاع).
  - #556 (`852fb5b`) **استرجاع مرآة `mirror.gcr.io`** في *Integration Tests* (يُصلح رفرفة Docker Hub — فجوة CI-MIRROR صارت `fixed`).
  - #557 (`f92c994`) **تفكيك `auth/main.py`** (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً، N=31 ثابت).
  - #558 (`522a47e`) **قصّ CDSE على المضلّع** لا الـbbox (إزالة الصحراء الحمراء): الواجهة تمرّر `geom=GeoJSON` ⇒ Sentinel Hub يقصّ على المضلّع (شفّاف خارجه). **علم تحقّق ميدانيّ.**
  - #559 (`1bef0cf`) **تطبيع تاريخ CDSE:** `date=""` الفارغ (ترسله الواجهة) كان يصير `date_from="-01-01T..."` فاسداً ⇒ يُعامَل كـ`latest`؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً. اختبار وحدة (٨). (مراجعة النسخة المرفقة: الملاحظة #2 صحيحة ونُفِّذت؛ #1 بصيغة آمنة؛ #3 — `X-Tenant-Id` من العميل لبوّابة التطوير — مقبول بلا تغيير.)

- **تفكيك ٤ خدمات متجانسة (#560–#563، ٤ وكلاء متوازين worktree):** نفس نمط raster/auth (`router_registry` + `_include_flat` + حارس تفكيك)، **نقل بنيويّ صرف محفوظ السلوك، عدد المسارات ثابت**:
  - #560 (`77123b3`) odoo-bridge: ١٠ معالجات → ٥ وحدات (14 مساراً ثابتة).
  - #561 (`d40f1a9`) video-processor: ٨ → وحدتان (12).
  - #562 (`0abe6de`) vegetation-analysis: ٨ → وحدتان (12؛ اختبارات الخدمة الحاليّة 19/19).
  - #563 (`7a36511`) supervisor-agent: ١٠ → وحدتان (14). **فشل CI حقيقيّ واحد:** حارس مصدر `tests_v9/test_ai_orchestration_safety.py` يمسح `main.py` لكود `/agent/query` الذي انتقل إلى `routers/agent.py` ⇒ أُصلِح بمساعِد [`supervisor_route_source.py`](../tests_v9/supervisor_route_source.py) المُجمِّع (main + routers، لا إضعاف أمنيّ).
  - **درس CI:** حُرّاس `tests_v9` ذات النوعين تتأثّر بالتفكيك — مسح المصدر (يُصلَح بمساعِد مُجمِّع) وتحميل الوحدة بالمسار (يحتاج مجلّد الخدمة على `sys.path` — `smoke_services.py` يفعله أصلاً؛ بعض الحُرّاس المعزولة لا، فتمرّ في CI لترتيب `sys.path` في السويت الكاملة).

- **MapHub/CDSE/WebSocket (#564، مفتوح):** مراجعة طلب المستخدم كشفت أنّ إصلاحات CDSE السابقة استهدفت `FieldIndicatorMap` لا `HubMap`. أُكمِلت:
  - `HubMap.tsx` → `cdse-tiles` (بدل `tiles` COG المفقود ⇒ 404) + bbox/geom/`tenant_id` + إزالة تعبئة المضلّع (`fill:false`).
  - `nginx.conf` → **`location ^~ /api/raster/`** (الجذر الحقيقيّ لـ404: regex `.png` كان يعترض البلاطات) + `X-Tenant-Id` من `$arg_tenant_id` (بلاطات `<img>` لا تحمل ترويسات) مع ارتداد للترويسة.
  - `agents/notification/agent.py` → توصيف `ws_notifications(websocket: WebSocket)` (وإلّا فشل المصافحة) + **`python-jose` المفقود** (الكود `from jose import` بلا تبعيّة ⇒ ModuleNotFoundError) + تثبيت `websockets<14`. pip-audit: لا ثغرات.
  - `routers/cdse_tiles.py` → **احتياط: جلب الهندسة من DB دائماً** حين لا تصل `geom` كي يبقى القصّ على المضلّع (MapHub لا يمرّر geom).

- **إغلاق فجوات قديمة:** `C5`/`H2`/`H5`/`C4-M1`/`SAM2`/`TERRAIN` → `deferred`/`by-design` (انظر [`gaps/registry.md`](gaps/registry.md)) — كلٌّ يحتاج بيئة/تحقّقاً ميدانيّاً/قراراً زراعيّاً خارج الإصلاح الآليّ الآمن.

- **قيد بيئيّ موثَّق:** حذف الفروع البعيدة يفشل (الوكيل بلا أداة حذف؛ الوسيط يرفض حذف المرجع) ⇒ الفروع العالقة (`frontend-cdse-hide-date`, `fix-cdse-clip-to-field`) تُحذَف من واجهة GitHub يدويّاً.

- **صدق:** كلّ تفكيك مُتحقَّق محليّاً (`import main` + ثبات العدد + الحارس + ruff)؛ مسار CDSE الحيّ (قصّ + قناع SCL) ما زال يحتاج تشغيل CDSE حقيقيّاً (يتعذّر محليّاً) — مُعلَن `fixed` لا `verified`.

---

## 2026-06-28 (ي) — تحصين/تفكيك raster + استرجاع بعد دفع مباشر على `main`

**رأس `main` بعد الجلسة:** `51d650c` (#551).

> ⚠ **تنبيه تشغيليّ (درس):** أُعيد ضبط `main` **بدفع مباشر من المالك** (لا عبر PRs:
> `a64d91c`→`5c40a56`) فمُحيت ٦ PRs كنتُ دمجتُها (#544–#549) — التزاماتها صارت يتيمة. **العمل لم
> يُفقَد** (الفروع باقية على origin)؛ أُعيد جوهره على `main` الحاليّ عبر **#550** (فرع واحد مدمج)
> مع **حفظ تامّ** لمساري CDSE الجديدين اللذين أضافهما المالك (`cdse-tiles`/`cdse-tilejson`).
> القاعدة: لا تبنِ على `main` أثناء دفع مباشر متزامن؛ وحّد الاسترجاع في فرع واحد سريع الدمج.

- **#550 (`2359cea`) — استرجاع تحصينات raster:**
  - **إصلاح جذر «الشرائط الداكنة»:** قناع داخليّ في كاتب COG (`dst.write_mask(isfinite·255)` +
    `DEFAULT_NODATA=-9999`، [`cog_writer.py`](../services/raster-service/cog_writer.py)) — إصلاح
    **المصدر**؛ يبقى `tile_render` بـ`dataset_mask` طبقة دفاع ثانية. (المصيّر وحده لا يكفي: بكسلات
    `finite=0.0` خارج dataMask كانت تُلوَّن معتمة.)
  - تعقيم تسريب `str(e)` للعميل ⇒ رموز عامّة + حارس ساكن
    ([`main.py:1329/1381`](../services/raster-service/main.py)).
  - `cloud_pct` فعليّ من SCL + قناع غيوم SCL بكسليّ في evalscript CDSE
    ([`cdse_client.py`](../services/raster-service/cdse_client.py)) — **علم تحقّق ميدانيّ:** يلزم تشغيل CDSE حقيقيّ.
  - سقالة `register_routers` ([`router_registry.py`](../services/raster-service/router_registry.py)).
- **#551 (`51d650c`) — تفكيك مسارات raster (محفوظ السلوك):** ٤٥ مسار `@app` → **١٠ وحدات `routers/`**
  (٤٩ مساراً ثابتة، CDSE محفوظة في [`routers/cdse_tiles.py`](../services/raster-service/routers/cdse_tiles.py));
  `main.py` ٣٠٠٥→١٦٢٥ سطراً. **اكتشاف:** `include_router` في Starlette 1.3.1 يلفّ الراوتر بكائن كسول
  (لا يُسطّح المسارات في `app.routes`) ⇒ `register_routers` يُلحِق `APIRoute` مباشرةً (مكافئ سلوكيّاً،
  مؤكَّد بـTestClient). حُرّاس `tests_v9` التي تمسح مصدر `main.py` حُدِّثت لتمسح `routers/` أيضاً
  (helper [`tests_v9/raster_route_source.py`](../tests_v9/raster_route_source.py)) — لا إضعاف للحراسة.
- **قيد المراجعة:** #552 (واجهة CDSE — حذف `date=latest` + إخفاء الفترة) · #553 (nginx `/api/raster/`
  لبوّابة الواجهة 3003) · #554 (وثيقة مقارنة `v9↔fixed`).
- **صدق:** ادّعاء IDOR من الفحص الساكن **رُفِض** — `_require_field_tenant`/`_require_layer_tenant_authorized`
  يرفعان 503 fail-closed أصلاً عند `OwnerLookupUnavailable` ⇒ لم نختلق إصلاحاً.

---

## 2026-06-23 (ط) — دفتر مياه يوميّ (v98) + تصدير Parquet + تحقيق H2 (بثلاثة وكلاء، #458)

**رأس `main`:** `89d848e` (#457 مُدمج). ثلاثة وكلاء متوازون في worktrees منفصلة الملفّات؛ دُمج
الكوديّان عبر cherry-pick نظيف (لا تضارب):
- **أ — دفتر المياه اليوميّ (Bundle B، فجوة IrriPro #1):** ترحيل `v98_water_ledger.sql` (جدول معزول
  بالمستأجِر + RLS/FORCE، PK مركّب `(field_id, ledger_date)`) + راوتر `api/routers/water_ledger.py`
  (POST upsert + GET بمدى، honest-503) + وحدة نقيّة `api/water_ledger_compute.py` + 18 اختباراً.
  **صدق:** كلّ القيم nullable — الناقص `NULL` لا تلفيق؛ `bool`/نصّ فارغ مرفوضان كعدد.
- **ب — تصدير Parquet لورشة SQL (Bundle B):** `frontend/src/services/duckdb.ts` (`exportQueryToParquet`
  عبر `COPY … (FORMAT PARQUET)` → `copyFileToBuffer`) + زرّ في `SQLEditor.tsx`. **صدق التسمية:**
  «Parquet» لا «GeoParquet» (جدول `fields` سمات بلا هندسة) + `TODO(GeoParquet)` موثَّق. vitest 332.
- **ج — تحقيق H2 (تقرير فقط، بلا كود):** مسح يدويّ كامل (الأداة `sahool_inspector` تفحص `services/`
  فقط فتفوّت مُشترِكي `agents/`). النتيجة: **٧** اشتراكات يتيمة لا ٨ (`satellite.*.computed`/
  `sahool.events.>` لهما ناشرون)، تصنيفها «ناشر مفقود متوقَّع» (قرار معماريّ ⇒ امتناع عن تغيير الكود
  بقاعدة اللبس). حُدِّث سجلّ الفجوات. **مخرَج صادق نافع: منع حذف عقود تكامل مقصودة.**

اتّساقاً مع الاستراتيجيّة: نُفِّذت B الجاهزة فقط؛ H2 بقي معماريّاً مفتوحاً (لا إصلاح آليّ غامض).
تحقّق: 26 اختباراً (دفتر+حارسان) · v98 يجتاز `validate_migrations` · ruff · vitest 332 · cherry-pick نظيف.

---

## 2026-06-23 (ح) — CDSE مزوّداً افتراضيّاً للصور + fallback تلقائيّ إلى Element84

**رأس `main`:** `1146021` (#456) — العمل على فرع `claude/code-review-34hO3` فوق #457.
أُضيف **Copernicus Data Space Ecosystem (CDSE)** كمزوّد صور **افتراضيّ أقوى** (Sentinel Hub
Process API): يحسب المؤشّر **خادميّاً** عبر `evalscript` على نطاقات Sentinel-2 L2A الكاملة
(فسيفساء أقلّ غيوماً) فيُرجِع GeoTIFF نطاق-واحد جاهزاً — مع **تحوّل تلقائيّ (fallback) إلى
Element84** عند تعذّر CDSE.

- **raster-service:** وحدة جديدة [`cdse_client.py`](../services/raster-service/cdse_client.py)
  (OAuth client_credentials + ذاكرة توكن + `build_evalscript` نقيّ لـ11 مؤشّراً + `bbox_dims`).
  نقطة `POST /v1/fields/{id}/process-cdse` (خدمة-لخدمة، `_require_service_token`) + مسار
  `precomputed_index` في [`main.py`](../services/raster-service/main.py) (يقرأ المؤشّر الجاهز
  → COG/persist/provenance، يعيد استخدام تسجيل الطبقات).
- **المنسّق:** [`imagery_automation.py`](../services/sahool-platform/api/imagery_automation.py)
  `_try_cdse` يُجرَّب أوّلاً في `trigger_field_imagery_processing`؛ غياب الاعتمادات/تعذّر ⇒
  `None` ⇒ يسقط بصمت إلى مسار Element84 القائم (best + process-from-stac). فالنقطة القائمة
  `/imagery/refresh` وأتمتة إنشاء الحقل تستفيدان تلقائيّاً (لا تغيير واجهة لازم).
- **صدق/أمان:** بلا `CDSE_CLIENT_ID/SECRET` (أو `CDSE_ENABLED=false`) ⇒ `is_configured()=False`
  ⇒ Element84 (السلوك القائم — لا كسر). **السرّ يُمرَّر بالمرجع `${CDSE_CLIENT_SECRET}`** في
  compose من `.env` غير المتتبَّع — لا قيمة حرفيّة في أيّ ملفّ. لا يُتحقَّق CDSE حيّاً في CI
  (لا اعتمادات/شبكة) — الدوالّ النقيّة فقط مُختبَرة؛ المسار الحيّ يؤكّده المشغّل.

تحقّق: 16 اختبار وحدة جديد ([`test_cdse_evalscript.py`](../tests_v9/test_cdse_evalscript.py)) ·
حارس تفويض الراستر أخضر (أُدرجت النقطة في `FIELD_SCOPED_SERVICE_ONLY`) · `pytest -m unit`
1686 ناجح (فشل MFA الـ5 سابقٌ لا صلة له، في `services/auth`) · ruff/format نظيف.

---

## 2026-06-23 (ز) — تنفيذ الاستراتيجيّة بوكيلين: تأكيد توحيد ET0 + Dual Kc (#457)

**رأس `main`:** `1146021` (#456). أوّل تنفيذ من [`decisions/strategy.md`](decisions/strategy.md) (Bundle A/B)، وكيلان متوازيان منفصلا الملفّات (cherry-pick نظيف):
- **توحيد ET0 (H4):** اكتشاف صادق — كان مُنجَزاً (#351/#356)؛ `core/engines/et0.py` يحسب Ra per FAO-56
  (لا ثابتاً) وكلّ المستدعين يُفوّضون. أُضيف **5 اختبارات انحدار** تُقفل الإصلاح + توثيق. لم يُعَد refactor
  (كان هدّاماً). متبقٍّ موثَّق: إعادتان عبر-خدمات (`weather_server`/`wofost`) — مؤجَّلتان (ربط عبر-خدمات).
- **Dual Kc (#457):** `compute_etc_dual` في `core/engines/fao56.py` (إضافيّ، المفرد افتراضيّ سليم) —
  `ETc=(Kcb·Ks+Ke)·ET0` (FAO-56 71-80) + 17 اختباراً. صدق: Kcb بإزاحة موثّقة؛ TEW/REW جداول؛
  الافتراضات تُعرَض وقت التشغيل (`DualKcResult.assumptions`).

اتّساقاً مع الاستراتيجيّة: نُفِّذت مهامّ A/B الجاهزة فقط؛ أُجّل C (R&D) وH5 (إقرار زراعيّ) والغامض.
تحقّق: 27 اختباراً (et0+dual) · ruff · حارس الراوترات · الفجوة H4 → ✅ مؤكَّدة.

---

## 2026-06-23 (و) — مراجعات إلهام (CultiWise/IrriPro، #455) + تصدير وصفة Shapefile (#456)

**رأس `main`:** `6e770b7` (#455). مراجعتا اتّجاه مُسنَدتان + أوّل اقتباس CultiWise منفَّذ:
- **#455:** صفحتا دماغ — [`precision-ag-direction.md`](decisions/precision-ag-direction.md) (CultiWise) +
  [`water-intelligence-direction.md`](decisions/water-intelligence-direction.md) (IrriPro/FAO-56). الكشف:
  SAHOOL يملك أصلاً معظم اللبنات (وصفات v95 · سجلّ قرار/نتيجة · FAO-56/ET0/هيدروليك/سيناريو/تفسير) —
  لا نُعيد البناء؛ الفجوات الحقيقيّة فقط (تصدير آلة · دفتر مياه يوميّ · توحيد ET0 H4 · Water Twin).
- **#456 (تصدير الوصفة Shapefile):** يملأ TODO موثَّقاً — `GET …/prescriptions/{id}/export?format=shapefile`
  → ZIP (.shp/.shx/.dbf/.prj) عبر `pyshp` (نقيّ-Python). وحدة نقيّة
  [`api/prescription_shapefile.py`](../services/sahool-platform/api/prescription_shapefile.py) (7 اختبارات) +
  راوتر + زرّ في PrescriptionBuilderPage. تبعيّة `pyshp==2.3.1` (pip-audit: 0 ثغرات). **ISOXML يبقى TODO
  موثَّقاً** (يحتاج نمذجة معدّات — لا ندّعي ما لا ننتجه). يحوّل المنصّة من «مراقبة» إلى «تنفيذ».

تحقّق: pip-audit نظيف · ruff · حارس الراوترات · 7 اختبارات وحدة · typecheck/build/vitest 332 · روابط الدماغ سليمة.

---

## 2026-06-23 (هـ) — AI GIS Assistant (NL→SQL، الفكرة 4 الأخيرة من GeoLibre، #454)

**رأس `main`:** `8781cce` (#453). مهمّة LLM-shaped — قُرئ مرجع claude-api؛ المفتاح خادميّ.
- صندوق «اسأل بالعربيّة» في ورشة SQL → `POST /api/v1/nl-sql` يستدعي Claude (`claude-opus-4-8`،
  قابل للضبط بـ`NL_SQL_MODEL`) → SELECT للقراءة فقط → يملأ المحرّر للمراجعة → DuckDB العميل.
- خادم: [`api/routers/nl_sql.py`](../services/sahool-platform/api/routers/nl_sql.py) +
  [`api/nl_sql_validate.py`](../services/sahool-platform/api/nl_sql_validate.py) (تحقّق نقيّ، 22 اختباراً).
  تبعيّة `anthropic` (pip-audit: 0 ثغرات). واجهة:
  [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) + `api.ts`.
- صدق/أمان: خصوصيّة (السؤال فقط) · SELECT مُتحقَّق + sandbox العميل + إنسان-في-الحلقة · مُغلَق
  بـ`FEATURE_NATURAL_LANGUAGE_GIS`+`ANTHROPIC_API_KEY` (honest-503). المشغّل يوفّر المفتاح.
- **خارطة GeoLibre الأربع مكتملة v1** ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

تحقّق: pip-audit نظيف · 22 اختبار وحدة + حارس الراوترات أخضر · typecheck/build/vitest 332.

---

## 2026-06-23 (د) — إكمال خارطة GeoLibre بـ٣ وكلاء متوازين (#453)

**رأس `main`:** `c3c7d28` (#452). ثلاثة وكلاء في worktrees منفصلة الملفّات (بلا تضارب عدا منطقة أزرار
SQLEditor — حُلّت بإبقاء CSV+JSON معاً)، دُمجت عبر cherry-pick:
- **و1 — ورشة SQL v2:** سجلّ استعلامات (localStorage) + أمثلة جاهزة + نسخ JSON
  ([`sqlHistory.ts`](../frontend/src/lib/sqlHistory.ts) + [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx)).
- **و2 — حفظ مساحة العمل v2:** التقاط/استعادة مركز+تكبير الخريطة عبر المحرّكين
  ([`HubMap.tsx`](../frontend/src/components/maphub/HubMap.tsx) · [`HubMapGL.tsx`](../frontend/src/components/maphub/HubMapGL.tsx) ·
  [`projectFile.ts`](../frontend/src/lib/projectFile.ts)) — بمنع حلقة moveend↔restore وحفظ auto-fit.
- **و3 — استوديو الهندسة المكانيّة:** قسم «أدوات الهندسة» + Turf buffer/simplify معاينةً
  ([`GisToolsPage.tsx`](../frontend/src/sections/GisToolsPage.tsx) + [`fieldGeometryOps.ts`](../frontend/src/lib/fieldGeometryOps.ts)).
  تبعيّتا `@turf/buffer`/`@turf/simplify` (0 ثغرات).

تحقّق دفعةً: typecheck نظيف · build (chunks منفصلة) · **vitest 332** · روابط الدماغ سليمة.

---

## 2026-06-23 (ج) — ورشة SQL في المتصفّح (DuckDB-WASM، إلهام GeoLibre الفكرة 2)

**رأس `main`:** `cd68a33` (#450، الاسترجاع التلقائيّ مدموج).

- **حفظ مساحة العمل (تكملة):** الاسترجاع التلقائيّ عبر localStorage (#450) — اكتملت الفكرة 1.
- **ورشة SQL (#451):** قسم جديد lazy «ورشة SQL (DuckDB)» تحت «البيانات والتحليل» — يحمّل حقول
  المستأجر إلى جدول `fields` في DuckDB-WASM (عميل-فقط، مستضاف ذاتيّاً) ويستعلمها بـSQL.
  ملفّات: [`frontend/src/services/duckdb.ts`](../frontend/src/services/duckdb.ts) ·
  [`frontend/src/hooks/useDuckDB.ts`](../frontend/src/hooks/useDuckDB.ts) ·
  [`frontend/src/components/sql/SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) ·
  [`frontend/src/sections/SQLWorkspacePage.tsx`](../frontend/src/sections/SQLWorkspacePage.tsx).
  تبعيّة `@duckdb/duckdb-wasm` (0 ثغرات، كسولة ~8MB gzip خارج الحزمة الرئيسة). النطاق v1: سمات
  الحقول فقط — spatial/المؤشّرات مؤجّلة ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

---

## 2026-06-23 (ب) — الدماغ على main + حفظ مساحة العمل (إلهام GeoLibre)

**رأس `main`:** `033fabe` (#448، الدماغ مدموج).

- **الدماغ (#448):** دُمج `sahool-brain/` على main — الوكيل القادم يقرأ hot/index بداية الجلسة.
- **حفظ مساحة العمل (GeoLibre، الفكرة 1):** ملفّ `.sahool-project.json` قابل للتسلسل (عميل-فقط) —
  تصدير/استيراد إعدادات «مركز الخرائط» (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات/الحقل
  المختار): [`frontend/src/lib/projectFile.ts`](../frontend/src/lib/projectFile.ts) + أزرار في
  [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx). v1 لا يحفظ مركز/تكبير
  الخريطة ولا الرسومات (مؤجّلة v2). انظر [`decisions/gis-direction.md`](decisions/gis-direction.md).

---

## 2026-06-23 — سلسلة الموبايل/الصور/QA + إنشاء الـbrain

**رأس `main` بعد الجلسة:** `0023f57` (#447).

- **auth (#437):** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في
  التسجيل/الدخول (يكمّله ترحيل `v97_user_self_with_check.sql`).
- **الصور (#438/#439):** تفعيل صور Sentinel-2 الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة)؛
  خادم SAM2 على GPU كـopt-in خلف `profile=gpu` (503 صادق بدونه).
- **dev-proxy (#440/#442):** توحيد وكيل تطوير Vite مع بوّابة nginx (v9) — يُصلح `npm run dev` +
  رؤية تشخيصيّة (offline/معالجة الصور).
- **QA الخرائط (#441):** سويت Playwright لبوّابة جودة MapLibre/WebGL (9 خطوات) + وظيفة CI.
- **الحقول الذرّيّة (#443):** دمج/انقسام الحقول عبر نقطتَي backend ذرّيّتين
  ([`fields.py`](../services/sahool-platform/api/routers/fields.py)) — سدّ خطر البيانات الثلاثيّة؛
  اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../tests_v9/test_fields_merge_split_atomic.py).
- **تكافؤ الموبايل (#444/#445/#446/#447):** مسار سلسلة NDVI (404)، مصدر المؤشّرات الصحيح + إدارة
  المزارع، ربط أقسام مساحة العمل بالخلفيّة، السمة الداكنة الرسميّة (`AppTheme.dark`).
- **الـbrain:** إنشاء `sahool-brain/` — هذا الـvault (README/index/hot/log/dashboard +
  architecture/schema/gaps/decisions/agronomy) + قسم «الدماغ المعرفيّ» في
  [`../CLAUDE.md`](../CLAUDE.md).
