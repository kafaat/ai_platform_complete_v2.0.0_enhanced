# دليل الطبقات المعمارية — متى تستخدم أيّها

> **الغرض:** المراجعة الشاملة كشفت تداخلاً ظاهرياً بين أربع وحدات تنسيق. هذا التوثيق يحلّ التداخل بإعلان المسؤولية الصريحة لكلّ واحدة.

---

## الطبقات الأربع — صورة سريعة

```
┌─────────────────────────────────────────────────────────────────┐
│  HTTP Request (FastAPI/Flask/uvicorn)                           │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  api_adapter.py  (266 سطر)                                       │
│  • ApiRequest/ApiResponse (محايد عن الإطار)                     │
│  • Rate limiting (AI Workaholic guard)                          │
│  • HTTP semantics (200/4xx/5xx)                                 │
│  • Health endpoints (/healthz, /readyz)                         │
└────────────────────────────────────┬────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  internal_orchestrator.py  (196 سطر)  ←── أو ──→  recommendation_bridge.py
│  • orchestrate_recommendation        │     • safe_delivery
│  • للاستدعاءات الداخلية              │     • للطبقات الخارجية
│  • يشمل V1 engine internally          │     • Contract enforcement
└────────────────────────────────────┬───┴────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────┐
│  recommendation_engine.py  (V1، 241 سطر، لا تعديل)               │
│  • generate_recommendation                                       │
│  • FarmerView + BackendDetail                                    │
└──────────────────────────────────────────────────────────────────┘

                    ╔══════════════════════════════════╗
                    ║  execution_control_plane.py       ║
                    ║  (345 سطر، cross-cutting)         ║
                    ║  • Entry point registration       ║
                    ║  • @governed decorator            ║
                    ║  • STRICT mode enforcement        ║
                    ║  • Audit + metrics                ║
                    ╚══════════════════════════════════╝
                    يحرس كل الطبقات أعلاه (orthogonal)
```

---

## متى تستخدم أيّاً — قرار صريح

### `api_adapter.handle_recommendation_request`

**استخدمه إن:**
- تكتب route لـHTTP framework (FastAPI/Flask/Starlette)
- تتعامل مع payload JSON
- تحتاج HTTP semantics (status codes، rate limiting)

**لا تستخدمه إن:**
- داخل النواة (أنت بالفعل في النواة، لا تحتاج HTTP layer)
- في background worker (HTTP overhead بلا قيمة)

### `recommendation_bridge.safe_delivery`

**استخدمه إن:**
- تبني integration خارجي (worker، CLI، scheduled job)
- لا تحتاج HTTP layer
- تريد كل ضمانات الـContract Pipeline (cross_ref + provenance + auth)

**لا تستخدمه إن:**
- داخل النواة (استخدم orchestrate_recommendation)
- مع HTTP (استخدم api_adapter — الذي يستدعي orchestrate داخلياً)

### `internal_orchestrator.orchestrate_recommendation`

**استخدمه إن:**
- داخل النواة (وحدة تستدعي وحدة)
- تريد ضمانات Contract Pipeline + توصيلاً مباشراً مع V1 engine

**لا تستخدمه إن:**
- في طبقة خارجية (استخدم safe_delivery أو api_adapter)
- لو كنت bridge نفسه (تجنّب recursion)

### `recommendation_engine.generate_recommendation` (V1)

**استخدمه إن:**
- ❌ **لا تستخدمه مباشرة في كود إنتاجي جديد**
- ✅ يبقى للتوافق الخلفي مع اختبارات قائمة
- ✅ ECP يكشف الاستدعاءات المباشرة (في WARNING/STRICT mode)

**لماذا الإغلاق:** هذا هو الـengine الفعلي. الاستدعاء المباشر يتخطّى cross_reference + provenance + auth + ECP audit. **هذا exactly ما حذّرت منه المراجعة الاستراتيجية**.

### `execution_control_plane.governed` (decorator)

**استخدمه إن:**
- تكتب entry point جديد (داخلي أو خارجي)
- تريد تسجيل + قياس آلي
- تريد فحص bypass attempts

**لا تستخدمه على:**
- helpers داخلية لا تُعتبر "entry point"
- pure functions (لا state، لا side effect)

---

## السؤال الذي يحدث في كل review: "لماذا أربع طبقات؟"

### الحجج المتقابلة (نزيهة)

**ضدّ التعدّد:**
- 4 طبقات = 4 ملفّات = 4 mental models
- المطوّر الجديد يحتاج وقتاً لفهم متى يستخدم أيّاً
- ممكن دمج bridge + orchestrator نظرياً

**مع التعدّد:**
- كل طبقة لها مسؤولية واحدة واضحة
- التغيير المنفصل ممكن (تطوير api_adapter بدون لمس bridge)
- ECP cross-cutting يحتاج وحدته (متعامد)
- bridge vs orchestrator: داخلي vs خارجي تمييز مفيد للأمان

### القرار النزيه

**الحالي:** 4 طبقات منفصلة، توثيق صريح (هذا الملفّ).

**في إصدار major تالٍ:** يمكن دمج bridge + orchestrator في وحدة واحدة بـtwo entry points. لكنّ ذلك يكسر:
- اختبارات قائمة (>30 اختبار)
- توثيق سابق
- مراجع import في الواجهة

**كلفة الدمج > فائدته الآن**. توثيق التداخل = حلّ كافٍ.

---

## أمثلة عملية

### مثال 1: FastAPI route

```python
@app.post("/recommendation")
async def recommendation(payload: dict, user: User = Depends(jwt_auth)):
    req = ApiRequest(user=user_schema_from_jwt(user), payload=payload)
    resp = handle_recommendation_request(req,
                                          recommendation_history=load_log())
    return JSONResponse(content=resp.body, status_code=resp.status_code)
```

### مثال 2: Background worker (sync نهاية اليوم)

```python
def daily_yield_summary_worker():
    for field in fields_needing_review():
        delivery = safe_delivery(
            user=worker_user,
            tenant_id=field.tenant_id,
            farm_id=field.farm_id,
            field_id=field.field_id,
            crop=field.current_crop,
            base_recommendation={...},
            recommendation_history=...,
        )
        if delivery.delivered:
            save_to_db(delivery)
```

### مثال 3: استدعاء داخلي بين وحدات

```python
# داخل وحدة scheduling داخلية:
from core.internal_orchestrator import orchestrate_recommendation

def auto_recommend_for_critical_field(field):
    return orchestrate_recommendation(
        user=system_user,
        tenant_id=field.tenant_id,
        ...
    )
```

### مثال 4: حماية entry point جديد

```python
from core.execution_control_plane import governed, EntryPointType

@governed(EntryPointType.BACKGROUND_WORKER, require_governance=True)
def my_new_scheduled_task(...):
    # ECP يسجّل تلقائياً + يفرض في STRICT mode
    ...
```

---

## الإقرار النزيه

هذا التوثيق **يحلّ مشكلة فهم بشري، لا مشكلة كود**. لو كان للنواة مطوّر واحد فقط، التداخل غير مهمّ — هو يعرف. لكن مع نمو الفريق، التوثيق الصريح يصبح **بديلاً عن إعادة الهيكلة المؤلمة**.

تطبيق "التأجيل ≠ الإغلاق المعماري" مرّة أخرى: نُؤجّل الدمج، لكن نُوثّق التداخل. كلّفته هذه الوثيقة. فائدته: مطوّر جديد يصل لمستوى الفهم في 10 دقائق.

---

## ما يستحقّ المراجعة في إصدار major تالٍ

1. **Bridge + Orchestrator dedup**: واجهة واحدة بـtwo paths (external_safe + internal_orchestrate)
2. **API adapter → adapter package**: ربط مع FastAPI app فعلي
3. **ECP STRICT mode افتراضياً**: بعد 95%+ تغطية entry points
4. **@governed على generate_recommendation نفسه**: يكتشف أيّ استدعاء مباشر

كلّها مؤجَّلة بمبرّر، لكنّها مُعدّة هيكلياً.
