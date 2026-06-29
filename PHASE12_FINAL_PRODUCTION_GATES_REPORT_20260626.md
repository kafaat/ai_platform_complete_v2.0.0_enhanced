# Phase 12 Final Production Gates — RLS, Secrets, Runtime Preflight

## الهدف

إغلاق الفجوة المتبقية بين الكود الجاهز والتشغيل الإنتاجي عبر بوابة Preflight تمنع أخطاء العزل والأسرار قبل بدء الحاويات.

## المضاف

- `scripts/security/rls_runtime_gate.py`
  - يفحص `.env` و`.env.example` و`docker-compose.v9.yml`.
  - يمنع runtime `DATABASE_URL` من استخدام `postgres` أو `sahool_user`.
  - يفرض `sahool_app` كدور التطبيق.
  - يفرض `sahool_jobs` كدور الخلفية فقط.
  - يمنع `JOBS_DATABASE_URL` خارج الخدمات الخلفية المصرح بها.
  - يمنع `SAHOOL_ALLOW_RLS_BYPASS_ROLE` في compose.

- `scripts/production_validation_gate.sh`
  - يشغّل `security_audit.sh`.
  - يشغّل RLS runtime role gate.
  - يتحقق من صياغة compose.
  - يتحقق من ترتيب وعدم تكرار Manifest migrations.
  - يشغّل Python compile sweep.

- `tests/security/test_phase12_final_production_gates.py`
  - يغطي عقود بوابات الإنتاج الجديدة.

- تحديث `RUNBOOK.md`
  - إضافة خطوات preflight النهائية وتسلسل التشغيل الآمن.

## قرار أمان

تم الإبقاء على `BYPASSRLS` فقط في قناة jobs المعتمدة (`sahool_jobs`) وليس في runtime app role. هذا يحافظ على RLS للتطبيق، مع السماح لمسارات outbox/background العابرة للمستأجرين بالعمل ضمن قناة محدودة ومختبرة.

## ما لم يتم تشغيله هنا

لم يتم تشغيل Docker runtime الحي في هذه البيئة. البوابة المضافة مصممة لتعمل قبل Docker على جهاز التشغيل أو CI.
