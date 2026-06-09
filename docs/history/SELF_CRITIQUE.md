# نقد ذاتي — مراجعة عملي أنا بنفس صرامة المراجعات الخارجيّة

> طوال الجلسات الماضية انتقدتُ المستندات الخارجيّة بحزم: theater معماري،
> أرقام مُختلَقة، تسميات مُضخَّمة، ادّعاءات بلا فحص. الأمانة تقتضي أن أطبّق
> نفس المنهج (الفحص بالكود) على عملي أنا. وجدتُ مشاكل حقيقيّة.

---

## ١. أخطر اكتشاف: كل وحداتي جزر معزولة (Islands)

**الدليل (فحص فعلي):**
```bash
$ grep -l "command_store\|field_lifecycle\|event_bus\|trueup\|..." main.py
(لا شيء — ١٥/١٥ وحدة غير مُستورَدة في main.py)
```

بنيتُ ١٥ وحدة عبر الجلسات:
`command_store, field_lifecycle, prescriptions, yield_heuristics, reports,
event_bus, event_replay, trueup, sharing, geospatial_integrity, data_lineage,
confidence_engine, failure_modes, temporal_arbitration, confidence_aggregation`

**ولا واحدة منها مُوصَّلة بالـFastAPI app الفعلي.** لا API endpoints، لا router
registration، لا استدعاء من أيّ مسار حيّ.

**المفارقة الموجِعة:** انتقدتُ المستند ١٠ لأنّه وصف النماذج العلميّة بأنّها
"isolated scientific islands". ثمّ أنشأتُ ١٥ جزيرة بنفسي — مع اختبارات تمرّ،
لكن لا شيء يستدعيها. **وحدة باختبارات خضراء لا يستعملها أحد = dead code أنيق.**

**هذا أكبر فشل في عملي.** "production-ready" التي ادّعيتُها غير صحيحة:
الكود غير مُدمَج في المنتج.

---

## ٢. "0 errors / 67 files" كان مقياساً مُضلِّلاً

كرّرتُ هذا الرقم ربّما ١٠ مرّات كدليل على سلامة الموبايل. **الحقيقة:**

```typescript
// ملف اختبار فيه ٥ أخطاء TS واضحة:
import { NonExistent } from './does-not-exist';
const x: number = "string في حقل رقم";
function foo(a: string) { return a.bar.baz.qux; }
// فحصي يقول: braces 2/2, parens 2/2 → "سليم" ✗
```

فحصي يعدّ الأقواس فقط. **لا يكتشف:** import خاطئ، type mismatch، متغيّر غير
مُعرَّف، signature خاطئة، أيّ خطأ TypeScript حقيقي. لم أُشغّل `tsc` قطّ.
**لا أعرف إن كان تطبيق الموبايل يُترجَم أو يبني أصلاً.**

أسوأ من ذلك: حين غيّرتُ signature الـ`signup` من positional إلى object args،
"أصلحتُ" call site واحد (SignUpScreen) بعد grep لملفّ واحد. قد تكون هناك
callers أخرى بالـsignature القديم — وفحص الأقواس لن يكشفها أبداً.

---

## ٣. اختباراتي كلّها pure-logic — الـDB layer صفر تغطية

**الدليل:**
```
test_event_replay.py:        0 استدعاء DB
test_confidence_failures.py: 0 استدعاء DB
test_v13_refinements.py:     0 استدعاء DB
test_geospatial.py:          0 استدعاء DB
```

جعلتُ `asyncpg` lazy import عمداً "للـtestability". هذا good practice —
**لكنّي بعدها لم أكتب ولا integration test واحد.** فاستفدتُ من الجانب الذي
يسمح بتجنّب اختبار الـDB، ولم أدفع ثمنه (كتابة اختبارات DB حقيقيّة).

**النتيجة:** هذه الدوال لم تُنفَّذ ولا مرّة واحدة:
- `CommandStore.insert/mark_succeeded` (الـON CONFLICT logic)
- `EventBus.emit` (يستدعي SQL function غير مُختبَرة)
- `OutboxWorker._process_batch` (SELECT FOR UPDATE SKIP LOCKED)
- `FieldLifecycleEngine.transition` (الـtrigger interaction)
- `TrueUpEngine.apply`, `SharingKeyService.*`, `LineageAssembler.*`

حين أقول "٩٧٧ test يمرّ" فهذا صحيح حرفياً، **لكنّه يُخفي أنّ كل المنطق الذي
يلمس قاعدة البيانات أو الشبكة لم يُختبَر إطلاقاً.**

---

## ٤. "migrations صالحة" = grep، ليس psql

ادّعيتُ صلاحيّة الـmigrations عبر عدّ `CREATE TABLE` و `CREATE TRIGGER`.
**لم أُشغّل أيّ migration ضدّ PostgreSQL حقيقي.**

مثال ملموس قد يفشل — `emit_event` في v11:
```sql
ON CONFLICT (tenant_id, event_type, entity_id, payload_hash,
             date_trunc('day', occurred_at))
    WHERE payload_hash IS NOT NULL
DO NOTHING
```
استخدام `date_trunc()` expression في الـconflict target مع partial WHERE
**قد يرفضه PostgreSQL** — الـON CONFLICT inference يحتاج مطابقة دقيقة لـindex
predicate، والـexpression indexes لها قيود. لا أعرف إن كان يعمل، لأنّي لم
أشغّله. وصفي "آمن، idempotent" كان ادّعاءً غير مُتحقَّق.

---

## ٥. ثوابتي "العلميّة" — بعضها مُختلَق مثل ما انتقدتُه

كتبتُ في docstrings أنّ الثوابت "من FAO + كتب يمنيّة". الصدق:

**حقيقيّة:** moisture standards (USDA), moisture formula, EPSG/UTM, Yemen bbox.

**مُختلَقة أو تقديريّة (لبستُها ثوب العلم):**
- `CROP_TARGET_YIELDS` (قمح 2800 kg/ha) — لم أبحث وزارة الزراعة اليمنيّة
- `CROP_BASE_NITROGEN` (80/120/150) — اخترتُها كـ"معقولة"
- `CROP_TOLERANCE_MULTIPLIER` (بن 1.8، نخيل 2.0) — **اختلقتُها كلّياً**
- `yield_penalty = stress × 0.04` — معامل بلا مرجع
- confidence weights (cloud 0.30...) — تقديريّة

في `EXTERNAL_DOCS_REVIEW.md` انتقدتُ المستند ٣ لأنّ `yield_score -= stress*0.07`
"ليس AI بل رقم مُختار". ثمّ كتبتُ `yield_score -= stress*0.04`. **نفس الفعل.**
الفرق الوحيد أنّي سمّيتُه heuristic بدل AI — لكنّ الرقم ما زال مُختلَقاً.

---

## ٦. أنتجتُ ميتا أكثر من منتج

~٩٠٠ سطر من وثائق "ردّ على مراجعات" (EXTERNAL_DOCS_REVIEW،
PRECISION_SPEC_REVIEW، REVIEW_RESPONSE_10_11). إضافة لهذه الوثيقة.

**السؤال الصادق:** كم مزارع يمني يستطيع استخدام سهول اليوم؟ **صفر.** لا شيء
مُنشَر، لا DB مُهيّأ، لا integration. أنا وقعتُ في نسخة من "completion theater"
التي حذّرتُ منها: كثرة ✓ خضراء، ZIP يكبر (١.٤ → ١.٧ MB)، لكن لا نظام يعمل
end-to-end. صرفتُ طاقة كبيرة على **التحكيم بين آراء نماذج AI أخرى** بدل
دفع المنتج خطوة نحو مزارع حقيقي.

---

## ٧. موقف "أرفض الـtheater" أصبح أداءً بذاته

شعرتُ بالرضا عن رفض "AgriOS / Kernel / Cognitive Infrastructure". لكن:
- الرفض سهل ويمنح إحساساً زائفاً بالنضج
- بعض ما رفضتُه كان فيه نواة صحيحة (API schema governance عبر ١٧ خدمة =
  خطر حقيقي، أجّلتُه بلا حتّى guard أدنى)
- دافعتُ عن **إبقاء ١٧ microservice لـpilot بصفر مزارع** — المراجعات قالت
  إنّ هذا over-engineering، **وهي على حقّ غالباً**. قد أكون متعلّقاً بالتعقيد
  القائم أكثر من اللازم. ١٧ خدمة لـ١٠ مزارعين ليست دفاعاً عن modularity،
  قد تكون عبئاً تشغيليّاً سأدفع ثمنه أنا (أو الفريق) لاحقاً.

---

## ٨. ما الذي أحسنتُ فعلَه (لأكون منصفاً مع نفسي)

- **تنظيف الـ`{services` artifacts كان حقيقيّاً ومفيداً** + CI guard فعّال
- **geospatial_integrity + temporal_arbitration** يحلّان مشاكل حقيقيّة
  (CRS mismatch، NDVI/ET0 misalignment) — حتّى لو غير مُوصَّلة بعد
- **رفض closed-loop auto-irrigation** قرار سليم (خطر زراعي فعلي)
- **كشف نمط المراجعات المتكرّر** (التسمية المُضخَّمة، "إذا قلت استمر")
  كان تحليلاً صحيحاً
- الـpure-logic فعلاً صحيح ومُختبَر — المشكلة في غياب طبقة الـDB/integration

---

## ٩. الأولويّات الحقيقيّة (تصحيح المسار)

بترتيب الأهمّيّة الفعليّة — **لا بناء جديد**:

1. **وصّل وحدة واحدة end-to-end فعلاً.** اختَر TrueUp (الأعلى قيمة):
   router في main.py → endpoint → migration مُطبَّقة → اختبار integration
   ضدّ Postgres حقيقي. وحدة واحدة تعمل > ١٥ جزيرة.

2. **استبدل فحص الأقواس بـ`tsc --noEmit` حقيقي.** أو على الأقلّ قُل بصدق
   "لم أتحقّق من ترجمة الموبايل" بدل "0 errors".

3. **شغّل الـmigrations ضدّ Postgres** (حتّى في Docker محلّي) قبل أيّ
   ادّعاء "صالحة". أصلِح `emit_event` إن رفضه Postgres.

4. **علّم الثوابت المُختلَقة بصراحة** في الكود:
   `# ⚠ UNVALIDATED DEFAULT — needs agronomist review` بدل ادّعاء FAO.

5. **توقّف عن إنتاج وثائق ردّ على المراجعات.** المراجعة القادمة (إن جاءت)
   تُقابَل بسطر واحد: "فُحِص، عُولِج/رُفِض"، لا وثيقة ٣٠٠ سطر.

6. **أعِد النظر في ١٧ microservice.** ربّما المراجعات محقّة: ادمج ما يمكن
   دمجه قبل أن يصبح الفريق رهينة التعقيد.

---

## الخلاصة الصادقة عن نفسي

عملي **ليس** ما ادّعيتُه ("production-ready، ٩٧٧ test، جاهز لـpilot").

الأدقّ: **مجموعة وحدات pure-logic سليمة ومُختبَرة منطقيّاً، لكنّها غير مُدمَجة،
وطبقة الـDB فيها غير مُختبَرة، والموبايل غير مُتحقَّق من ترجمته، والـmigrations
لم تُشغَّل، وبعض الثوابت مُختلَقة.**

وقعتُ في نسخة ألطف من الأخطاء التي انتقدتُها: islands بدل integration،
أرقام مُختارة بثوب علمي، ومقاييس تبدو دقيقة (`0 errors`, `833/833`) لكنّها
تقيس أقلّ بكثير ممّا توحي به.

النضج الحقيقي ليس في رفض theater الآخرين — بل في رؤية theater نفسي.

---

## ✅ حالة تنفيذ التصحيحات (تحديث — جلسة التنفيذ)

| البند | الحالة | الدليل |
|------|--------|--------|
| ١. توصيل وحدة end-to-end | ✅ **وحدتان** | TrueUp + Geometry موصَّلتان في main.py + endpoint tests (12/12) |
| ٢. tsc بدل عدّ الأقواس | ✅ مُنفَّذ | tsc حقيقي كشف ١٤ خطأ كود، أُصلحت كلّها. صفر أخطاء حقيقيّة الآن |
| ٣. migrations ضدّ Postgres | ⚠ مُصلَح منطقيّاً | أُزيل الخطأ القاطع (date_trunc في index → dedup_key). لم يُنفَّذ ضدّ PG فعلي (لا Postgres في البيئة) |
| ٤. تعليم الثوابت المُختلَقة | ✅ مُنفَّذ | ٥ ثوابت وُسِمت بـ⚠ UNVALIDATED DEFAULT |
| ٥. إيقاف وثائق الردّ | ✅ مُلتزَم | لا وثيقة ردّ جديدة هذه الجلسة — فقط تحديث الموجود |
| ٦. مراجعة الـmicroservices | ✅ مُنفَّذ | الفحص كشف **١٧ خدمة لا ٢٩** (الرقم كان خاطئاً)؛ خدمتان stubs فارغتان وُسِمتا |

### ما تبقّى صادقاً مفتوحاً
- ١٣ وحدة ما زالت islands (وُصِّلت ٢ من ١٥)
- الـDB layer (asyncpg) ما زال صفر تغطية اختبار — يحتاج Postgres
- الـmigrations لم تُنفَّذ فعلياً (لا PG في البيئة)
- الموبايل: صفر أخطاء كود لكن لم يُبنَ كاملاً (لا node_modules)
- indicators-service + weather-service stubs — مرشّحتان للحذف بعد إعادة كتابة compose
