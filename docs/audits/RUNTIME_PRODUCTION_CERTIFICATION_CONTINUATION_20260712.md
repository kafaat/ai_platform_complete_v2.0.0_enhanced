# Runtime Production Certification Continuation — 2026-07-12

## Scope
Water ledger → governed decision → execution request → actuator consumer → receipt/timeline.

## Findings fixed

1. **Actuator command contract mismatch (P0)**
   - The water bridge queued `operation/field_id/amount_mm`, while the actuator requires `device_id + command + payload`.
   - Fixed to emit `device_id=<target>`, `command=irrigate`, and a payload carrying amount, field/season lineage, risk, and a stable idempotency key.

2. **Receipt-loss recovery gap (P0)**
   - A successful MQTT/simulation publish followed by receipt API failure stranded the request in `delivering`; the queued feed excludes it and the old consumer generated a fresh random token.
   - Added authoritative recovery feed: `GET /v1/execution-requests/recovery?adapter_id=...`.
   - Added deterministic HMAC delivery token and deterministic receipt id.
   - The actuator polls recovery work before queued work and replays using the same claim identity. The command retains its stable idempotency key, yielding an at-least-once transport contract without duplicate physical work for conforming adapters/devices.

3. **Configuration hardening**
   - Added `ACTUATOR_DELIVERY_TOKEN_KEY` to compose and `.env.example`.
   - Missing both the dedicated key and decision-service token leaves dispatch fail-closed.

## Verification
- Focused bridge/recovery contract: `21 passed`.
- Expanded actuator + water + decision feed suite: `45 passed, 3 skipped`.
- Skips are real-PostgreSQL integration tests; Docker/PostgreSQL are unavailable in this execution environment.
- `py_compile` passed for all modified Python modules.

## Remaining operational-only gate
Run the supplied services under staging Compose with real PostgreSQL and simulation MQTT, then execute dual-consumer, restart, receipt-failure, and RLS scenarios. Real actuation remains prohibited until those gates pass.

---

## ملحق التكامل (أُضيف عند الإنزال)

- **قاعدة الحزمة بائتة مصدودة (النمط المتكرّر):** نسختها من `phase_runtime_workers.py` كانت
  ستعيد علّة `entity_id::uuid` التي أصلحتُها عند دمج الجسر (`events.entity_id` نصّيّ منذ v18) —
  أُخذت الدلتا الجوهريّة فقط وبقي ملفّي. كذلك بقيت ملفّاتي الأحدث (workflows بترقية Node 24،
  logging_config، allowlist العقود، actuator main.py).
- **إصلاح عقد أمر الجسر (P0) مُتبنّى** داخل جسري المدموج (device_id + command + payload +
  مفتاح idempotency ثابت) — كان الشكل القديم سيُرفض invalid_command عند كلّ تسليم.
- **feed الاسترداد مُتبنّى ومُثبَت على Postgres حقيقيّ** (الحزمة لا تختبر PG): مطالبة بلا
  إيصال تظهر للـadapter نفسه فقط وتختفي بعد الإيصال — اختبار جديد في
  `test_execution_request_feed.py`. تحقّقتُ أنّ `status='delivering'` مشروع (قيد 006 يوسّع CHECK).
- **توكن التسليم الحتميّ (HMAC) fail-closed مُتحقَّق:** غياب `ACTUATOR_DELIVERY_TOKEN_KEY`
  و`DECISION_SERVICE_TOKEN` معاً ⇒ لا مطالبة إطلاقاً. مطالبات ما-قبل-الترقية بتوكنات
  عشوائيّة تفقد قابليّة الاسترداد — مقبول (لا مطالبات حيّة قبل الإنتاج).
- بوّابة جاهزيّة الجهاز + عدم تطابق الهدف/الحمولة + إعادة فحص kill-switch على نطاق
  الحقل/الصمّام: مُتبنّاة كما سُلِّمت (27 اختبار مُشغّل تمرّ).
