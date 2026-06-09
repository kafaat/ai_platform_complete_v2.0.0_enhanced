# المراجعة السابعة — التشديد التشغيلي (Hardening)

المراجعة السابعة دقيقة ومتوازنة: أكّدت أنّ الطبقات موجودة (صحّحت المراجعة
السادسة)، لكن بعضها thin، والناقص هو hardening لا إعادة بناء. اتّفق معها.

## ما نُفّذ: idempotency للمزامنة (أهمّ اكتشاف حقيقي)

### المشكلة المؤكّدة (بالفحص الفعلي)
edge-inference/sync_service.py كان file-queue + retry بلا dedup:
- sync_result ينجح server-side ثمّ تنقطع الشبكة قبل وصول الردّ →
  يُعيد queue → يُرسَل **مرّتين** → حدث مكرّر.

### الإصلاح
- queue_result يولّد idempotency_key ثابت (sha256 محتوى + uuid، 32 حرف)
- يُرسَل مع كلّ محاولة (immediate + queued)
- مسار الفشل (_queue_with_key) يحفظ بنفس المفتاح → retry لا يكرّر
- عناصر متطابقة المحتوى → مفاتيح مميّزة (لا dedup زائف)

### ⚠️ ما يتبقّى عليك (server-side)
الخادم /v1/edge/sync (غير مبني بعد) **يجب أن يكشف التكرار** على
idempotency_key (INSERT ... ON CONFLICT DO NOTHING أو فحص مسبق). العميل
الآن يوفّر المفتاح؛ بناء معالج الخادم قرار تصميم لم أبنِه تخمينيّاً.

## تدقيق بقيّة ادّعاءات المراجعة 7 (كلّها صحيحة ومتوازنة)
| الادّعاء | حكمي |
|----------|------|
| Lifecycle موجود لكن lightweight | ✅ صحيح — state machine بسيط لا kernel |
| Lineage = audit assembler لا provenance engine | ✅ صحيح |
| sync أضعف من المتوقّع | ✅ صحيح — عالجتُ الأهمّ (idempotency) |
| guardrails قويّة لكن بلا transactional locking | ⚠️ صحيح — موافقات متزامنة قد تتسابق |
| GIS: geometry valid لكن raster reproducibility ناقص | ⚠️ صحيح جزئيّاً |
| اختبارات الفشل ناقصة | ✅ صحيح — chaos/corruption غير مغطّاة |

## ما لم أنفّذه (وأكون صادقاً عن السبب)
- **transactional locking للموافقات**: يحتاج تصميم قفل DB (SELECT FOR UPDATE)
  + اختبار تزامن حقيقي — تغيير في guardrails يستحقّ جلسة مركّزة، لا تعديل
  عابر. قرارك إن أردته.
- **raster reproducibility (tile lineage/version pinning)**: ميزة GIS كبيرة
  تحتاج تصميم — ليست hardening عابراً.
- **chaos/corruption tests الشاملة**: أضفتُ idempotency test؛ مجموعة chaos
  كاملة (Redis outage، NATS partition، DB فشل جزئي) تحتاج محاكاة بنية تحتيّة.

## التحقّق
- 350/350 · sync_service يُترجم + مُختبَر (3 فحوص idempotency)

## ملاحظة صدق
- نفّذتُ أعلى بند قيمةً وأوضحه حدوداً (idempotency للعميل). البقيّة
  (locking، raster lineage، chaos الشامل) تحتاج تصميماً مركّزاً أو بنية —
  لم أبنِها تخمينيّاً تفادياً للكود غير المُختبَر الذي يخاطر بكسر العامل.
- المبدأ: تشديد محدود مُتحقَّق منه > طبقة ضخمة غير مُجرَّبة.
