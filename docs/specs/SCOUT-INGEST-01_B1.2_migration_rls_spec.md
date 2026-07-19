# مواصفة SCOUT-INGEST-01 · B1.2 — migration + عقد RLS + مدخل ingress + محوّل ODK

- **الحالة:** ✅ **B1.2a مُنفَّذ** (الهجرة v197 + resolver + الحُرّاس + برهان حيّ) · ⏳ **B1.2b** (المدخل + الاعتماد لكلّ مصدر + محوّل ODK) للتنفيذ التالي.
- **الهجرة:** v197 · **الراية:** `SCOUT_INGEST_ENABLED` (افتراضيّ off) حتى التحقّق التكامليّ.
- **يسبقه:** B1.0 (العقد المحايد، `1ac3411`) · B1.1 (التحقّق السباعي، `0712a9b`).

## 0 · النطاق والحدود
تخزين الإدخال الخارجيّ (خامّ محفوظ) + RLS + مدخل + محوّل ODK. **لا إسقاط domain** (ذاك B1.3).
تدفّق: `external submission → ODK adapter → EnvelopeV1 (B1.0) → validate السبعة (B1.1) → صفّ في external_submissions بحالته`.

## 1 · الهجرة v197 (جدول واحد + حالة) — قرار (أ) ✓ مُنفَّذ
جدول **واحد** `external_submissions` يحمل `trust_status` + `quarantine_reasons` (الخامّ في مكانه، الحالة سمة لا كيان).
- الأعمدة: raw محفوظ في `raw_payload` (jsonb) · `raw_ref` = **مقبض URN للنَّسَب** (يقرأه إسقاط B1.3 للاستشهاد بالخامّ؛ البايتات في raw_payload — ليس عموداً يتيماً) · `normalized_payload` (محاذاة العنقود 4، ADR-0034).
- `trust_status ∈ {untrusted, accepted, quarantined}` (CHECK) · `quarantine_reasons TEXT[]`.
- dedup فريد `UNIQUE (tenant_id, idempotency_key)` + فهرس جزئيّ على `accepted`.
- **RLS حرفيّ:** FORCE + `tenant_isolation` USING+WITH CHECK على `NULLIF(current_setting('app.current_tenant', true), '')` (نمط v155/v192).
- **immutability كسمة (قرار «لا DELETE»):** trigger `BEFORE DELETE` يرفع استثناء — لا اعتماد على غياب grant قابل للإلغاء.

## 2 · التزامن الإلزاميّ ✓ مُنفَّذ
`MANIFEST.txt` + `run_migrations.sql` (خطوة 203) + حارس `test_migration_runners_in_sync_20260705.py` أخضر + `db_ownership.yml` (owner=platform).
(`production_validation_gate.sh` مُشغَّل عند الدمج على main.)

## 3 · مِلكيّة القاعدة — قرار (ج) ✓
`external_submissions` owner=**platform** (المدخل فيها). ترحيل لخدمة ingest مستقلّة مؤجَّل بمحفِّز.

## 4 · المدخل (ingress) — قرار (ب) + الاعتماد لكلّ مصدر [B1.2b]
- نقطة داخليّة `POST /internal/ingest/submissions/odk` (نمط `service_token_auth.py` — لا `get_current_user`).
- **ربط المستأجِر (لا من المُرسِل):** يُشتقّ من **سجلّ تعيين** يربط `(provider, server, form_id) → tenant_id` (= فحص `form_mapping_registered`)، يملؤه **مالك المستأجِر** عند تسجيل خادم ODK.
- **الاعتماد لكلّ مصدر (تعديل ملزِم):** السجلّ يخزّن `scout_ingest_token_hash` لكلّ `(provider, server)`؛ المدخل يحلّ **التوكن → السجلّ → المستأجِر**. **لا `SAHOOL_AGENT_TOKEN` مشترك لهذا السطح** — إبطال مصدر مخترَق = تعطيل سطر في السجلّ، لا تدوير يكسر الجميع. لا توكن ⇒ 401 · توكن بلا تعيين ⇒ 403 · تعيين معطَّل ⇒ 403.
- **كاتب `accepted` (حسم قرار):** اجتياز الفحوص السبعة (B1.1) ⇒ يُدرَج `trust_status='accepted'` عند الإدراج (التحقّق هو بوّابة الثقة؛ B1.3 يقرأ المقبول فقط). `untrusted` يبقى للحالات غير المفحوصة (backfill مستقبليّ). فشل فحص ⇒ `quarantined` بأسبابه.
- idempotent: منطق `resolve_dedup` (B1.2a، أدناه) — لا `ON CONFLICT DO NOTHING` صامت.
- الكتابة تُعيّن `set_config('app.current_tenant', <resolved>, false)` (session-scoped) قبل الإدراج · خلف `SCOUT_INGEST_ENABLED`.

## 4.1 · حلّ dedup (تعديل ملزِم — يُلغي الابتلاع الصامت) ✓ مُنفَّذ (resolver نقيّ)
`shared/contracts/ingest/dedup_resolution.py::resolve_dedup` — منطق ثلاثيّ، لا `DO NOTHING` صامت:
- لا صفّ موجود ⇒ `insert_new`.
- موجود، **جسم مطابق** (نفس content_hash) ⇒ `idempotent_replay` (200 صادق، نفس الصفّ).
- موجود، **جسم مختلف** ⇒ `quarantine_divergent`: يُخزَّن بمفتاح **مشتقّ** (`key#dup-<hash12>`، أقوى من `#dup2` لأنّه لا يصطدم عند جسمين متباينين) + `trust_status='quarantined'` + سبب `duplicate_key_divergent_payload`. **الأصل لا يُمسّ.**

## 5 · محوّل ODK Central [B1.2b]
`services/.../ingest/odk_adapter.py`: ODK submission → `ExternalSubmissionEnvelopeV1`؛ `content_hash=sha256(raw)`؛ `mapping_version` مثبَّت؛ `raw_payload`=الخامّ. التعيين مُصدَّر بنسخة (ملفّ قابل للمراجعة).

## 6 · الحُرّاس والبراهين
**B1.2a (مُنفَّذ + مُصادَق حيّاً على PG16 أصليّ):**
1. حارس ساكن v197 (`test_v197_external_submissions_static.py`): FORCE + WITH CHECK + `app.current_tenant` + trigger DELETE + dedup فريد + تسجيل المُشغّلَين/الملكيّة.
2. الحارس السابع (`test_ingest_dedup_resolution.py`): «نفس مفتاح، جسم مختلف ⇒ quarantined بمفتاح مشتقّ، لا سقوط صامت».
3. **برهان حيّ** (`test_v197_external_submissions_rls_live.py`، `-m integration`، 3/3 على PG16): (أ) سياق فارغ ⇒ الإدراج مرفوض (RLS fail-closed) · (ب) dedup متباين ⇒ صفّ quarantined، الأصل accepted سليم · (ج) DELETE ⇒ استثناء append-only.

**B1.2b (تالٍ):** حارس session-GUC (`false`) على كتابة المدخل · حارس «المدخل بلا JWT مستخدم» · **برهان الاعتماد المنفصل** (توكن مصدر معطَّل ⇒ 403 لا يمسّ غيره) · تكامليّ للمسار الكامل (adapter→validate→store).

## 7 · بوّابات الالتزام
`pytest -m unit` · ruff · `build_release_bundle`+`validate` · `production_validation_gate.sh` (main) · regen inventory · تحديث الدماغ.

## 8 · ما ليس في B1.2
لا إسقاط إلى `scouting_pins`/`observations` (B1.3) · لا Kobo (B1.4) · لا واجهة. **تخزين + تحقّق + quarantine فقط، خلف راية.**
