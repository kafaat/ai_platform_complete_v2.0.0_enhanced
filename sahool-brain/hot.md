# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-07-04 · `main` = `develop` = `claude/code-review-34hO3` = رأس ن-30 (سُدّدت P0 كاملة: القرار العميق + دورة التوصية + مساعدات الريّ — العقد 320 core/146 إعفاء) بعد ن-29 (٣ لوحات دَين UI + fail-closed لقناع CDSE + تجميع شهريّ لشريط التواريخ؛ العقد 299 core/167 إعفاء) بعد ن-28 (لا بتر لتواريخ الصور — الأحدث يبقى؛ العقد 285 core بعد ترقية 183 إعفاءً وهميّاً) بعد ن-27 (دلتا أرشيف المستخدم: قناع البلاطات يُعاد إسقاطه صراحةً — لا أشرطة داكنة؛ بوّابة التغطية خطوة CI صريحة) بعد ن-26 (إصلاح تخطّي حفظ raster_assets: field_id نصّيّ fld_* لا UUID — العمود VARCHAR(50)) بعد ن-25 (أرشيف المستخدم: بوّابة عكسيّة لعقد التغطية — 60 core + 364 إعفاء صريحاً، لا مسار مواجِه فالت؛ إصلاح جذر الجوّال mobile/sahool_app/lib) بعد ن-24 (FieldView صار الجذر «/» وكلّ الشاشات ظاهرة؛ dashboard ⇒ /dashboard) بعد ن-23 (فشل STAC التامّ ⇒ 503 صادق لا 500 خام؛ DNS حاوية المستخدم معطّل — تشخيص مشغّل) بعد ن-22 (إصلاح جذر فشل كلّ مهامّ backfill: `_safe_raster_source` كان يرفض مسارات الأنابيب الداخليّة الخام ⇒ قبول تحت `UPLOAD_DIR` فقط + VRT يُكتب داخله + سجلّ الفشل يحمل status/detail). [`log.md`](log.md) مدخل (ن-21، ن-20، ن-19). ٣ دفعات وكلاء + جسر الحوكمة + كونسول الموافقات (+نقطة GET /approvals/pending الخلفيّة) — السجلّ **صفر partial** (covered:16)، العقد **102 endpoint** (كان 24 صباح اليوم)، vitest **758**. +التقويم اليمنيّ (منزلة/حميريّ/أمثال، display_only) و«ماذا أزرع؟» (دورة+ملاءمة شهر) — العقد 47 endpoint.
> 📊 **عقد تغطية backend⇄frontend (ن-14):** بوّابة `endpoint_ui_coverage_gate` + مصفوفة 652 مساراً مُصنَّفة بالجمهور + **43 endpoint ملزَماً** بحارس unit — و٥ واجهات جديدة من مسارات كانت يتيمة: بطاقة المحصول (crop-cards) · اقتصاد عميق (economic-state/break-even) · تتبّع الحصاد (harvest-lots v65) · مراجعة الحدود (score/graph) · كونسول `/admin/runtime` (owner/manager). أيّ endpoint جوهريّ يفقد قارئه ⇒ CI أحمر.
> 🎯 **FieldView صار «متعاوناً يحقّق هدفاً» لا «أداة تعرض بيانات» (٢٥ التزاماً، أساس→حوكمة→P0–P4→إلهام→محرّك الأهداف):** الطبقة المتوّجة **Field Objective Engine** (`777582b`): حلقة **هدف→فحص→تفسير→إجراء→مراجعة** بـ٦ أهداف جاهزة، `buildObjectivePlan` **يمنع التوصية `canAct` حتّى اكتمال الدليل** (يُحسَب من الاستعلامات الحيّة)، ودورة حياة توصية صريحة (مسوّدة→…→مراجعة→جودة، الأثر `unknown` حتّى مراجعة حقيقيّة). قبلها: تقرير صحّة الحقل (P0) · عرض الفلاح ٤ مقاييس (P1) · ورشة VRA (P2) · مقارنات طبقات (P3) · طبقة الأعمال (P4) · بطاقات إلهام (John Deere/CropX/OneSoil/Taranis/Cropin/Farmonaut) · وضع فلاح/خبير · سجلّ تتبّع Markdown. **درس:** `ruff format --check` يمسح `services/` كلّها في CI؛ ومؤلّفو الأرشيفات يشغّلون `py_compile` فقط (خطأ enum الـruntime `FIELD_IMAGERY_BACKFILL_REQUESTED` ضبطه حارس المنصّة لا `-m unit`). ٥٨٣ اختبار vitest أخضر · tsc نظيف.
> 🗺️ **دمج أرشيفات المستخدم (تحقّق-قبل-دمج، عزل الدلتا بالأساس لا بالرأس):** خرائط احترافيّة (MapTiler مُقيَّد بالمفتاح + `toMapLibreRasterUrl`) · **سلسلة أدلّة تقطيع كاملة:** SAM2 metadata → field-seg passthrough (3-tuple) → الواجهة تحفظ boundaryMetadata → **`field_geometry_save_guard`** (يرفض حدوداً رديئة قبل مصدر الحقيقة؛ metadata للتدقيق يُعقّمها الخادم، لا يمنح ثقة) · أدوات صقل عميل (Douglas-Peucker 1/3/5م، مساعِدة فقط) + بوّابة e2e حيّة. 2515 اختبار وحدة · MapLibre Phase-3 موجود. **درس:** أرشيف على أساس ثابت + main متقدّم ⇒ قارن بالأساس/الأرشيف السابق لعزل زيادة المستخدم، واحفظ إضافاتك (علامات unit).
> 🌾 **جلسة استلهام/تحسين (بحث GitHub/Gitee + تحقّق-قبل-تنفيذ):** (١) **ثقة SAM2** end-to-end (الاستدلال يُخرِج IoU · field-seg يمرّرها · الواجهة جاهزة لعرضها «ثقة ٪»). (٢) **جدار العمليّات 大屏:** إصلاح انجراف عقد `OperationsSummary` (الواجهة أعلنت حقولاً لا يُخرِجها الخادم ⇒ الأرقام مُهدَرة) + `KpiStrip` بأرقام كبيرة صادقة. (٣) **soil-service:** SoilGrids (ISRIC CC-BY) + قوام USDA (NRCS) + ملاءمة محصول Liebig (محاصيل يمنيّة). (٤) **فكّاك Modbus-RTU** (RS485 رخيص، kundian-iot) — CRC-16 مُتحقَّق + `/soil/decode/modbus`. **درس pip-audit:** تبعيّة جديدة على المسار الحرِج تُكتَب `>=` لا `==` (البوّابة تُثبّت كلّ الخدمات معاً) — أحمَر CI 3 دفعات قبل `httpx>=0.27.0`. **درس عزل:** أسماء الوحدات العامّة تتصادم عبر الخدمات ⇒ تحميل `importlib` بأسماء فريدة. **تحقّق-قبل-تنفيذ أثبت مُنجَزاً:** EVI/SAVI/NDWI · device-twin · GB28181 · التتبّع · CSV export.
> 🛠️ **ميزات ٣ خدمات (٣ وكلاء متوازين، نواة حتميّة + خلفيّة ثقيلة اختياريّة import-guarded):** video-processor (StreamRegistry · ZLMediaKitClient · snapshot/record · أحداث NATS/MQTT) · tts (مزوّدون Edge/Piper/XTTS-GPU · مطبّع عربيّ · /tts/status) · agriai (evidence bundle · replay حتميّ · WOFOST adapter · profit planner). 2442 اختبار وحدة · تغطية 48.77٪. **درس:** `docker compose up` يعيد استخدام صورة مُخزَّنة — إقلاع auth «mfa_crypto مفقود» يُحلّ بـ`up --build` لا بتعديل كود (الـDockerfile سليم).
> 🖥️ **تمكين GPU (RTX 5090/Blackwell) لـv9:** تراكب منفصل `docker-compose.v9.gpu.yml` (لا يمسّ CPU) — حجوزات GPU + SAM2 (يُغلق AUTO-SEG تشغيليّاً) + zlmediakit + video readyz probe + edge CUDA modes + SAM2 Dockerfile قابل للتجاوز + بوّابة `v9_gpu_contract_gate` + ٣ e2e حيّة + **runbook Windows/WSL2 مُعايَر على عتاد المستخدم** (RTX 5090 Laptop 24GB/Driver 592/CUDA 13.1/WDDM).
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
