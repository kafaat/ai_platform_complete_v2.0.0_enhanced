# مواصفة SCOUT-INGEST-01 (B1) — جسر الإدخال الميدانيّ الخارجيّ (مُقسَّمة)

**الحالة:** B1.0 مُنجَز (العقد المحايد) · B1.1–B1.4 للمراجعة قبل التنفيذ · **الأولوية:** P0 منتجيّ (أكبر فجوة منتج، مؤكَّدة غائبة في الدراسة المقارنة).

## المبدأ الحاكم
**الوصول ≠ الثقة.** إدخال خارجيّ (سوق ريفيّ، بلا اتصال) يدخل خلف عقد محايد، يُحفظ خامّاً، ولا يبلغ القرار قبل «التحقّق السباعي».
**فجوة تركيب لا تأسيس:** اللبنات موجودة داخليّاً — نركّبها خلف مدخل ingress خارجيّ.

## اللبنات القائمة المُعاد استخدامها (مؤكَّدة file:line)
- مظروف/idempotency: نمط `shared/contracts/remote_sensing/events/envelope_v1.py:23` (`EventEnvelopeV1`).
- تطبيع/رفض: `services/sahool-platform/api/crop_stress_ingestion.py:34` (`normalize_stress_product` — allow-list + رفض provenance ناقص).
- طابور + dead-letter: `services/soil-service/projection_jobs.py` (enqueue coalesce · claim SKIP LOCKED + lease · complete/fail→dead_letter · MAX_ATTEMPTS).
- كتّاب domain: `scouting_pins` (`fields.py:3803-3815` `_persist_scouting_pin`) · `observations` (`observations.py:47` `record_operation_offline`).

## الشرائح
### ✅ B1.0 — العقد المحايد (مُنجَز، نقيّ، بلا migration/ingress)
`shared/contracts/ingest/external_submission_v1.py` — `ExternalSubmissionEnvelopeV1` محايد المزوّد:
provider/server/form_id/instance_id/content_hash/tenant_id/submitted_at/received_at/**raw_ref**/**mapping_version**/idempotency_key/payload/**trust_status=untrusted**.
مفتاح dedup **بنيويّ** (`derive_dedup_key` = sha256(provider|server|form|instance|content_hash)؛ مظروف بمفتاح مزوّر يُرفَض). `SEVEN_CHECKS` مُعلَنة (تُفرَض في B1.1).
حارس `tests_v9/test_external_submission_contract_v1.py` (8 اختبارات: untrusted افتراضيّ · dedup مشتقّ · مفتاح مزوّر مرفوض · aware-UTC · extra-forbid · trust≠trusted · سبعة فحوص فريدة). يحاذي العنقود 4 (`sosa:Observation`، أقوى محاذاة ADR-0034).

### ⏳ B1.1 — التحقّق السباعي + quarantine (منطق صرف، للمراجعة)
`validate_external_submission(envelope, ctx) -> AcceptOrQuarantine` — يُشغّل الفحوص السبعة (tenant_known · provider_allowlisted · form_mapping_registered · provenance_complete · field_resolves_in_tenant · values_within_domain_bounds · not_duplicate). فشل أيٍّ ⇒ **quarantine بسبب مُصنَّف، الخامّ محفوظ، لا إسقاط**. نمط الرفض من `normalize_stress_product`. حارس + برهان سلبيّ. بلا endpoint.

### ⏳ B1.2 — المدخل + التخزين (migration + ODK Central أوّلاً)
migration: `external_submissions` (خامّ محفوظ) + `external_submission_quarantine` + فهرس فريد على مفتاح dedup (RLS FORCE + WITH CHECK، نمط الجداول المستأجَرة). محوّل ODK Central → المظروف (mapping مُصدَّر بنسخة). نقطة ingress بتوكن خدمة (لا JWT مستخدم)، idempotent على dedup. خلف راية تفعيل.

### ⏳ B1.3 — عامل الإسقاط (نمط projection_jobs)
عامل claim→project: **المقبولة فقط** (اجتازت السبعة) تُسقَط إلى domain عبر كتّاب `scouting_pins`/`observations` القائمين → complete/dead_letter. «لا دخول للقرار قبل التحقّق السباعي» مفروضاً. اختبار تكامليّ (`-m integration`).

### ⏳ B1.4 — Kobo (مزوّد ثانٍ)
نفس المظروف، تعيين ثانٍ منخفض الكلفة.

## قواعد عدم الانحراف
حارس + برهان سلبيّ + regen + CI أخضر SHA واحد لكلّ شريحة · كلّ شريحة خلف راية حتى التحقّق التكامليّ · raw محفوظ · mapping مُصدَّر · dedup بنيويّ · لا إسقاط قبل السبعة · مفردات المظروف من ADR-0034 (العنقود 4 أوّلاً).
