# Offline-First Architecture في سهول

> **الفلسفة المعمارية:** offline as default, online as enhancement.

> **الفرق الفلسفي الجوهري عن الأنظمة الغربية:** Cropwise/FieldView/John Deere يفترضون 24/7 cloud streaming. سهول يفترض sync حين يتوفّر الاتصال، الإنترنت متقطّع، الكهرباء أحياناً.

---

## المبدأ الأساسي

```
سهول لا يحتاج connectivity ليعمل.
الـconnectivity تُغني، لا تُحدّد.
```

هذا ليس "ميزة" يجب بناؤها — هذا **خاصّيّة بنيوية** للنواة:
- كل الكود في `core/` هو **pure Python** (لا I/O)
- 4 connectors فقط هم الـboundary بين النواة والشبكة
- 776 اختبار يمرّ **بدون أيّ network access**

---

## التحقّق الآلي

```bash
# اختبار: هل أيّ ملفّ في النواة يستورد network libraries؟
$ grep -rln "^import requests\|^import urllib\|^import httpx" core/
(فارغ)
```

```bash
# اختبار: هل النواة تكتب لـDB مباشرة؟
$ grep -rln "sqlite3\|psycopg\|asyncpg" core/
(فارغ — outside connectors/)
```

```
نتيجة: النواة pure-Python كاملاً. 
       offline-first ليس claim — هو fact بنيوي.
```

---

## الطبقات الثلاث للـoffline support

### الطبقة ١: النواة pure-Python (بنيوية)

```
✅ 13 محرّك زراعي     → لا I/O
✅ canonical_schemas    → dataclasses فقط
✅ recommendation_engine → لا I/O
✅ skills_registry      → in-memory dict
✅ ECP                  → لا network
✅ source_of_truth      → arbitration بحت
✅ farm_memory          → composition بحت
✅ time_series          → calculations بحتة
✅ feedback_closure     → readiness checks بحتة
✅ identity             → UUID generation محلّي
```

**كل قرار زراعي في سهول قابل للتنفيذ بدون شبكة.**

### الطبقة ٢: Offline Queue (الجديد)

`core/offline_first.py` — البنية الصريحة للعمليات المعلّقة:

```python
from core.offline_first import OfflineQueue, OperationKind, record_operation_offline, sync_cycle

queue = OfflineQueue()

# المزارع يسجّل مشاهدة بدون connectivity:
op = record_operation_offline(
    queue,
    tenant_id="tnt_001",
    user_id="u_agronomist",
    kind=OperationKind.OBSERVATION_CREATE,
    payload={
        "field_id": "fld_03",
        "observable_id": "ndvi",
        "value": 0.55,
        "measured_at": "2026-05-29T08:00:00",
    },
)
# → PendingOperation مع op_id فريد، status=QUEUED
```

**ضمانات الـqueue:**
- **Tenant isolation**: كل tenant عنده queue منفصل (تأكيد آلي)
- **FIFO order**: العمليات تُسلَّم بترتيب الإنشاء
- **Max per tenant**: حدّ افتراضي 1000 (يمنع memory leak)
- **Status tracking**: QUEUED → SYNCING → SYNCED/FAILED/CONFLICTED/SUPERSEDED
- **Retention للـaudit**: clear_synced(older_than_hours=24)

### الطبقة ٣: Sync Cycle عند عودة الاتصال

```python
# Client يكتشف الاتصال موجود:
def my_sync_handler(op):
    """يُستدعى لكل عملية. يرفع exception للفشل، يُرجع False للرفض."""
    response = requests.post(API_URL, json=op.payload)
    if response.status_code == 409:
        raise ValueError("CONFLICT: server has newer version")
    return response.ok


result = sync_cycle(queue, "tnt_001", sync_handler=my_sync_handler)
# → SyncResult:
#     synced_count: 5
#     failed_count: 1     (سيُعاد لاحقاً)
#     conflicted_count: 1  (يحتاج مراجعة بشرية)
#     superseded_count: 2  (مُلغاة لأنّ عمليات لاحقة أحدث)
```

**أهمّ ضمانة:** فشل sync **لا يُسقط** العملية. تبقى في الـqueue للمحاولة لاحقاً.

---

## Conflict Resolution Strategy

عند sync، ثلاث حالات تتطلّب معالجة:

### 1. Supersession (آلي، شفّاف)

```
مزارع offline:
  09:00 → activity_complete(act_X, status="completed")
  14:00 → activity_complete(act_X, status="completed_with_notes")

عند sync:
  apply_supersession() يكشف نفس act_X مرّتين
  09:00 → SUPERSEDED ("حلّت محلّها 14:00")
  14:00 → تُسلَّم للسيرفر
```

**القاعدة:** عمليّتان لاحقتان على نفس الكيان → الأقدم تُلغى.

### 2. Conflict (يحتاج مراجعة بشرية)

```
مزارع offline:
  10:00 → observation(fld_03, ndvi=0.55)
  
سيرفر (من قمر صناعي):
  10:30 → observation(fld_03, ndvi=0.62)

عند sync:
  CONFLICT detected (نفس observable في وقت قريب)
  → SyncStatus.CONFLICTED
  → requires_human_review في source_of_truth
```

**القاعدة:** لا اختيار آلي — `source_of_truth.arbitrate()` يعلن التضارب، المهندس يحكم.

### 3. Failure (transient، يُعاد لاحقاً)

```
شبكة سيّئة → ConnectionError
→ SyncStatus.FAILED
→ retry_count += 1
→ تبقى في الـqueue
```

**القاعدة:** فشل ≠ فقدان. كل عملية فاشلة قابلة لإعادة المحاولة.

---

## نمط التكامل في الـclient

```typescript
// Client code (مثال للواجهة):

const connectivity = await checkConnectivity();

if (connectivity.is_online) {
  try {
    await api.recordObservation(payload);   // مباشر
  } catch (networkErr) {
    // fallback لـoffline
    await offlineQueue.enqueue({kind: 'OBSERVATION_CREATE', payload});
  }
} else {
  // offline-first path
  await offlineQueue.enqueue({kind: 'OBSERVATION_CREATE', payload});
  showToast("✓ سُجّلت محلّياً — ستُزامَن عند الاتصال");
}

// عند عودة الاتصال:
window.addEventListener('online', async () => {
  const result = await syncQueue();
  if (result.conflicted_count > 0) {
    showAlert(`${result.conflicted_count} عمليّة تحتاج مراجعة`);
  }
});
```

---

## ضمانات صريحة (testable)

| الضمانة | كيف تُختبَر |
|---------|-----------|
| النواة تعمل بدون network | 776 اختبار يمرّ بدون internet |
| الـqueue يحفظ العمليات للـsync | `test_failures_kept_in_queue` |
| tenant isolation محفوظ في الـqueue | `test_separate_queues` |
| supersession آلي للعمليات المكرّرة | `test_two_completes_same_activity` |
| conflict منفصل عن failure | `test_conflict_detected_vs_failure` |
| max per tenant مفروض | `test_max_per_tenant_enforced` |
| لا network في offline_first نفسها | `test_pure_python_only` |

---

## ما تبقّى DEFER (مع المبرّر الصريح)

| البند | لماذا مُؤجَّل |
|------|-------------|
| Storage الفعلي (SQLite في الواجهة) | يحتاج runtime محدّد (Tauri/Electron/PWA) |
| Background sync workers | يحتاج Service Worker (في الـclient) |
| Bidirectional sync مع server | يحتاج API endpoints (لاحقاً) |
| Network state detection | platform-specific (browser API/iOS/Android) |
| Battery-aware throttling | mobile-only، خارج النواة |

**هذه wrappers خفيفة فوق `offline_first.py`** — لا تتطلّب تعديل النواة.

---

## النتيجة المنهجية

8 وثائق نقدية متلقّاة، كل واحدة كشفت فجوة. الأخيرة (AI Ag Template) كشفت أنّ سهول **offline-first بطبيعته لكنّ غير موثَّق**. الحلّ:
1. ✅ توثيق صريح في هذه الوثيقة
2. ✅ `core/offline_first.py` كـAPI صريح
3. ✅ 20 اختبار يحرس الضمانات

**هذا الفرق بين "حظّ معماري" و"قرار معماري"**: الأوّل قد ينكسر بإضافة `requests` في النواة. الثاني محرَّس آلياً ضدّ الكسر.

---

## النقطة الفلسفية الأعمق

في النموذج الغربي (Cropwise/FieldView):
```
online == default  →  offline == failure mode
```

في سهول:
```
offline == default  →  online == enhancement
```

هذا فرق **هندسي وفلسفي** معاً. ينعكس على:
- **التصميم**: queue قبل API، لا العكس
- **UX**: "سُجّلت محلّياً" رسالة عادية، لا خطأ
- **الثقة**: المزارع يعمل دون انتظار "السحابة"
- **الاستقلال**: النظام لا يتوقّف لو انقطع الإنترنت

**سهول لا يحتاج الإنترنت ليساعد المزارع اليمني. هذا اختيار معماري ناضج للسياق.**
