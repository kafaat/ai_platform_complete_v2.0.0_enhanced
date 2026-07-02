# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-07-02 · رأس الفرع المخصّص `claude/code-review-34hO3` = `9b72229` (SEC+ERP+zipR+نقل-الميزات أخضر على الفرع؛ **ff-merge إلى main معلّق بموافقة المستخدم** — مصنّف auto-mode حجب دفع main) · [`log.md`](log.md) مدخل (ن-5).
> 🚚 **نقل ميزات إلى v9 (أرشيف المستخدم — تحقّق-قبل-تنفيذ):** video-processor/agriai-engine/tts-service (كود موجود، غائب عن v9) نُشِرت في v9.yml + مسارات nginx (`/tts` 503→proxy · `/api/video` و`/api/agriai` شبكة خاصّة · CSP بلاطات MapHub) + بوّابة `v9_feature_transfer_gate`. services=48→51.
> 🔁 **ERP bridge + بوّابة عقد UI (مقارنة أرشيفَي المستخدم — نُفِّذ الصحيح zipB):** إعادة تسمية odoo-bridge→erp-bridge (aliases legacy على الجسر **وحده** لا كلّ خدمة كما في zipA المرفوض) + `service-feature-ui-contract-gate` (PASS 26/26). درس CI: `ruff format --check` أحمر عند سطر طويل يحتاج مسحاً متّصلاً ⇒ `# fmt: skip`.
> 🔒 **دفعة «البقايا القابلة للتنفيذ» (أرشيف superset — دلتا فقط فوق الأحدث):** C4 rag/ingest tenant لكلّ chunk (يُغلق تأجيلاً) · C5 قراءات KG تتطلّب X-Tenant-Id · C3 `current_field_state` يتطلّب X-Agent-Token (403) · C2 AI يمرّر tenant لـKG · H1 SAM2 URL افتراضيّ · H2 منفذ edge 8100 · H3 agent_stores يفشل مغلقاً في الإنتاج مع Redis · port-8126 erp + C1 تصحيح upstreams nginx · ٣ بوّابات ساكنة جديدة. 62 اختبار + ٤ بوّابات + production gate خضراء.
> 🔒 **دفعة أمان SEC-1..7 كاملة (البنود الثمانية من مراجعة أرشيف المستخدم — كلّها مُتحقَّقة بالكود):** compose (fixed.yml dev-env يقتل footgun prod+bypass · light.yml خدمات→127.0.0.1 + حارسان) · Dockerfile non-root (6 + حارس) · **هويّة البوّابة الموثوقة** (X-Tenant-Id مصدر الحقيقة · body-override→403 · KG/rag-ingest writes service-token) · **SEC-3.1 مُنفَّذ:** user/role للموافقات (auth يُصدِر X-User-Id/X-User-Role · nginx يحقنهما للمسار · `require_authenticated_user` 403 missing_user · الموافِق المُسجَّل = الهويّة الموثّقة لا الـbody) · **SEC-5:** أرضيّة تغطية 20→40 (المُقاس 48.12٪) · **SEC-6:** حارس تثبيت التبعيّات + خطّة قفل مرحليّة · **SEC-7:** هجرات/RLS إلزاميّة أصلاً على main + smoke حيّ جاهز-للتفعيل (قرار مشغّل).
> 🛡 **تصلّب v133–v140 (٣ دفعات، تحقّق-قبل-بناء):** kill switch · fields.geometry validity+version · workflow lease (sync+async) · irrigation_runs · schedule-conflict · offline terminal state · field_geometry_history append-only (v139) · outbox per-attempt log (v140). كلّها اختبارات تكامل مرّت بالاسم على Postgres. **درس CI:** الدوالّ النقيّة لا تُوضَع في وحدة تستورد fastapi؛ والفاحص الساكن يطلب `FORCE`+`current_setting` حرفيّاً (لا helper).
> 🛡 **دفعة السلامة الأساسيّة (v133/v134/v135):** مفتاح إيقاف تشغيل fail-closed · `ST_IsValid` على `fields.geometry` + `geometry_version` · قفل الكاتب-الأوحد للـworkflow. ٩ اختبارات تكامل بالاسم على Postgres.
> 🛡 **دفعة السلامة الثانويّة (v136/v138 + حارسان):** **v136** سجلّ تشغيل الصمّامات irrigation_runs · **schedule-conflict** رفض 409 لتداخل الجداول (app-level) · **AsyncStore lease** (يكمل v135) · **v138** حالات `processing`/`failed` لـoffline_pending_ops (لا ops سامّة أبديّة). ٩ اختبارات تكامل بالاسم على Postgres. **درس:** الدوالّ النقيّة يجب ألّا تُوضَع في وحدة تستورد fastapi (فشل unit tier بلا fastapi) — استُخرِجت إلى `irrigation_logic.py`.
> 🛰 **v62.3 Evidence Runtime (٤ شقوق):** A عقد أدلّة NDVI + بوّابة اكتمال fail-closed · B كاتب/قارئ أعمدة جودة raster (v131) · C توصيل الشبكة pack→evidence→VRA · v52 مظروف سياسة AI. + VALIDATE-prep (تقرير مخالفات + حارس + runbook؛ **بلا SQL**). **Superset merge: no-op مُثبَت** (main يحتوي cert، `a9f7314` سلف خطّيّ).
> 🔎 **v29.6.1 (مراقبة/حُرّاس انحدار MFA — غير حاجب):** IP في تدقيق step-up · منع مفتاح تجزئة ثابت في الإنتاج · ٣ حُرّاس ساكنة (`_acquire` admin · recovery بلا self-read · audit append-only).
> 🔐 **تصلّب MFA إنتاجيّ مكتمل ومُثبَت على Postgres حقيقيّ** (v29.5+v29.6): تشفير السرّ + recovery + قفل DB + تدقيق append-only + RLS مُضيَّق. **P0 مُغلَق:** `test_mfa_migrations_applied_on_real_postgres` مرّ فعليّاً في CI (لا تخطٍّ صامت) — أثبت v128/v129 + RLS المُضيَّق + trigger append-only على DB حيّ.
> 🐳 **إصلاح إقلاع auth** (`abf1731`): `Dockerfile` لم ينسخ `mfa_crypto.py` ⇒ `ModuleNotFoundError` ⇒ unhealthy. أُصلِح + **حارس معمَّم** يمسح استيرادات main.py الشقيقة (otp/mfa_crypto…).
> 🤖 **حوكمة الوكيل مكتملة** (v58.2a/b/c): مخازن دائمة + تحقّق وسائط + تعقيم نتائج + ميزانية/dedupe + كلّ mutating يتطلّب موافقة.
> 🛰 **أدلّة الحقل** (v49.5) + **شقّ v57.5-DB مكتمل**: soil-lab analytes (v130) · imagery quality (v131) · field_state provenance (v132).
> ✅ **`main@f9dc4c8` أخضر بالكامل:** ci.yml 11/11 (Integration يطبّق v127–v132 على Postgres حقيقيّ) + **Sahool Production Gates #209**.
>
> ⚠️ **درس تشغيليّ (لا يتكرّر):** بعد أيّ دمج يغيّر ملفّات، جدِّد بصمات الإصدار وشغّل بوّابة الإنتاج قبل اعتبار main نظيفاً —
> **Sahool Production Gates سير عمل منفصل يعمل على main فقط ولا يظهر في فحص الفرع**:
> `python3 scripts/release/build_release_bundle.py --root .` + `bash scripts/production_validation_gate.sh`.
> (بقيت البوّابة حمراء من `0b5a13b` حتى أصلحها `f9dc4c8` — كنتُ أراقب ci.yml وحده.)

## عمل هذه الجلسة (على `main`، سلسلة دفعات خضراء)

التفاصيل + الأسباب + الـSHAs في [`log.md`](log.md) مدخل (ز) و[`decisions/ledger.md`](decisions/ledger.md):

| الدفعة | SHA | الجوهر |
|---|---|---|
| v58.2a | `eb3cf89` | مخازن موافقة/تدقيق قابلة للاستبدال + `/approvals/resume` |
| v58.2b | `151851a` | تحقّق وسائط صارم + تعقيم نتائج + «mutating ⇒ approval» |
| v49.5 | `abe0c51` | ذاكرة AI tenant-scoped + redaction + ترحيل v127 (RLS WITH CHECK) |
| bandit B613 | `5202907` | إعادة بناء regex الـbidi من code points (Security Scan أخضر) |
| v58.2c | `0b5a13b` | ميزانية أدوات + dedupe + إيقاف عند البوّابة |
| 422 backfill | `2e353af` | إسقاط `truecolor` من `indices` (عقد raster IndicatorKind) |
| v29.5 | `8810321` | تشفير MFA + recovery + قفل + تدقيق (ترحيل v128) |
| JWT_SECRET نبات | `62989c6` | تمرير `JWT_SECRET` لخدمة vegetation في compose |
| v29.6 | `4a3f1a4` | إصلاحات مراجعة MFA: RLS مُضيَّق + step-up محكوم + ذرّيّة + append-only (ترحيل v129) |
| v57.5 CI | `cb4ea31` | اختبارات تكامل MFA/v57.5 كانت تتخطّى بصمت ⇒ استخدام `TEST_DATABASE_URL` (إثبات P0) |
| auth-boot | `abf1731` | نسخ `mfa_crypto.py` في صورة auth + حارس وحدات شقيقة معمَّم |
| v29.6.1 | `f75e363`/`b5ee3ce` | IP في تدقيق step-up + نظافة مفتاح تجزئة الإنتاج + ٣ حُرّاس انحدار MFA ساكنة |
| v62.3-A | `ea6829e` | عقد أدلّة NDVI + بوّابة اكتمال fail-closed (valid_pixel/coverage/cloud/stale/geom) |
| v62.3-B | `aa0f830` | تعبئة/قراءة أعمدة جودة raster (v131) + `cloud_cover` للـpack |
| v62.3-C | `a99f4f4` | توصيل الشبكة+الجودة raster→pack→`ndvi_grid_evidence`→بوّابة VRA |
| v52 | `90b0803` | مظروف سياسة AI: platform يقرأ `tenant_ai_policies` (v124) ويبني المظروف؛ ai_agronomist يرفض بلا مظروف (fail-closed) |
| v133 | `6ad1872` | VALIDATE-prep: تقرير مخالفات + حارس (unit+integration) + runbook (بلا VALIDATE أعمى) |

## أعلى الفجوات الآن

(السجلّ الكامل + المصادر في [`gaps/registry.md`](gaps/registry.md))

| ID | العنوان | الحالة |
|---|---|---|
| MFA-HARDEN | تصلّب MFA الإنتاجيّ (تشفير/recovery/قفل/تدقيق/RLS) | **fixed + P0 مُثبَت** (v128+v129؛ `test_mfa_migrations_applied_on_real_postgres` مرّ في CI على Postgres حيّ) |
| AUTH-BOOT | صورة auth لم تنسخ `mfa_crypto.py` ⇒ ModuleNotFoundError ⇒ unhealthy | **fixed** (`abf1731` + حارس معمَّم) |
| AGENT-GOV | حوكمة أدوات الوكيل (مخازن/تحقّق/تعقيم/ميزانية) | **fixed** (v58.2a/b/c) |
| AIMEM-TENANT | سياق ذاكرة AI عابر-المستأجر بلا فلتر صريح | **fixed** (v49.5) |
| VEG-JWT | خدمة النبات بلا `JWT_SECRET` في compose ⇒ 503 «تحليل الآن» | **fixed** (`62989c6`؛ يلزم `--build`/إعادة تشغيل) |
| BACKFILL-422 | «تجهيز سنتين» يرسل `truecolor` كمؤشّر ⇒ 422 | **fixed** (`2e353af`) |
| SPATIAL-401 | «المؤشرات المكانية» تُخرج للدخول (raster `/indicator-grid` 401) | **open** (يحتاج status+body من Network) |
| AUTO-SEG | «تحديد الحدود تلقائي» 503 (SAM2 غير منشور) | **by-design** (تشغيليّ: `SEGMENTATION_BACKEND=sam2`) |
| v57.5-DB | soil_lab analyte (v50) · imagery quality (v54) · field_state recompute (v53) · tenant AI policy DB (v52) | **fixed** (v130/v131/v132 + v52 مظروف السياسة على v124) |
| v62.3 | Evidence productionization (raster→ndvi_grid · imagery quality contract) | **fixed** (A عقد+بوّابة · B كاتب/قارئ v131 · C توصيل الشبكة؛ integration أخضر) |
| v52 | سياسة AI للمستأجِر | **fixed** (`90b0803`؛ platform سلطة، ai_agronomist مستهلِك؛ derived: tools/data_classes/max_bytes بلا أعمدة — موثَّق) |
| SUPERSET | توحيد main↔certification | **no-op** (main يحتوي cert؛ `a9f7314` سلف خطّيّ، 0 commit متقدّم) |
| VALIDATE-NV | قيود NOT VALID (v127/v130/v132) | **prep** (`6ad1872`: تقرير+حارس+runbook؛ VALIDATE الفعليّ للمشغّل بعد تنظيف) |

## ماذا بعد؟

- **عاجل (المشغّل):** إعادة بناء/تشغيل خدمة النبات لتطبيق `JWT_SECRET`:
  `docker compose -f docker-compose.v9.yml up -d --build sahool-vegetation-analysis`. + ضبط `MFA_SECRET_ENCRYPTION_KEY` في `.env` لتفعيل مسار MFA الإنتاجيّ.
- **SPATIAL-401:** أرسل status+body لطلب `/v1/fields/{id}/indicator-grid` من Network (أو سجلّ raster) لأشخّصه — لا اختلاق إصلاح.
- **تصلّب الأساس (v57.5-DB):** أعلى أثراً v54 imagery quality ثمّ v50 soil_lab (لـVRA)؛ **أعيد التحقّق** أنّ كلّ بند لم يُغلَق downstream قبل التنفيذ.
- **انضباط:** هذا المدخل يغلق دَين تحديث الدماغ لهذه الجلسة.
