# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-07-01 · رأس `main` = الفرع المخصّص `claude/code-review-34hO3` = `f9dc4c8` · [`log.md`](log.md) مدخل (ز).
> 🔐 **تصلّب MFA إنتاجيّ مكتمل** (v29.5+v29.6): تشفير السرّ عند الراحة + recovery codes + قفل DB + تدقيق append-only + RLS مُضيَّق — مسار توافق لا يكسر المستخدمين القائمين.
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

## أعلى الفجوات الآن

(السجلّ الكامل + المصادر في [`gaps/registry.md`](gaps/registry.md))

| ID | العنوان | الحالة |
|---|---|---|
| MFA-HARDEN | تصلّب MFA الإنتاجيّ (تشفير/recovery/قفل/تدقيق/RLS) | **fixed** (v128+v129؛ Integration أخضر) |
| AGENT-GOV | حوكمة أدوات الوكيل (مخازن/تحقّق/تعقيم/ميزانية) | **fixed** (v58.2a/b/c) |
| AIMEM-TENANT | سياق ذاكرة AI عابر-المستأجر بلا فلتر صريح | **fixed** (v49.5) |
| VEG-JWT | خدمة النبات بلا `JWT_SECRET` في compose ⇒ 503 «تحليل الآن» | **fixed** (`62989c6`؛ يلزم `--build`/إعادة تشغيل) |
| BACKFILL-422 | «تجهيز سنتين» يرسل `truecolor` كمؤشّر ⇒ 422 | **fixed** (`2e353af`) |
| SPATIAL-401 | «المؤشرات المكانية» تُخرج للدخول (raster `/indicator-grid` 401) | **open** (يحتاج status+body من Network) |
| AUTO-SEG | «تحديد الحدود تلقائي» 503 (SAM2 غير منشور) | **by-design** (تشغيليّ: `SEGMENTATION_BACKEND=sam2`) |
| v57.5-DB | soil_lab analyte (v50) · imagery quality (v54) · field_state recompute (v53) · tenant AI policy DB (v52) | **open** (يحتاج Postgres، عبر CI) |
| v62.3 | Evidence productionization (raster→ndvi_grid · imagery quality contract) | **open** (اقتُرِح بعد v62.2) |

## ماذا بعد؟

- **عاجل (المشغّل):** إعادة بناء/تشغيل خدمة النبات لتطبيق `JWT_SECRET`:
  `docker compose -f docker-compose.v9.yml up -d --build sahool-vegetation-analysis`. + ضبط `MFA_SECRET_ENCRYPTION_KEY` في `.env` لتفعيل مسار MFA الإنتاجيّ.
- **SPATIAL-401:** أرسل status+body لطلب `/v1/fields/{id}/indicator-grid` من Network (أو سجلّ raster) لأشخّصه — لا اختلاق إصلاح.
- **تصلّب الأساس (v57.5-DB):** أعلى أثراً v54 imagery quality ثمّ v50 soil_lab (لـVRA)؛ **أعيد التحقّق** أنّ كلّ بند لم يُغلَق downstream قبل التنفيذ.
- **انضباط:** هذا المدخل يغلق دَين تحديث الدماغ لهذه الجلسة.
