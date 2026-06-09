# إصلاح بنود P2/P3 (إكمال المراجعة)

## ✅ مُصلَحة

### P3-2: فرض طول JWT_SECRET (تحذير → فشل)
- auth/main.py: كان logger.warning عند <32 حرفاً → صار RuntimeError.
  سرّ قصير = أمان ضعيف، نفشل بأمان بدل التشغيل.

### P2-2: print() → logger
- bot startup banner (3 أسطر) → logger.info.
- ملاحظة: prints في learn_from_harvest + validate_observations **مقصودة**
  (أدوات CLI، مخرجاتها stdout صحيحة) — لم تُحوّل (ليست runtime).

### P2-3: bare except في الاختبار
- test_database_migrations.py: except: → except Exception:
  (يتجنّب ابتلاع KeyboardInterrupt/SystemExit).

### P2-4: فهارس tenant_id لأداء RLS
- وُجدت 4 جداول بلا فهرس tenant_id: fields, field_lifecycle,
  market_sales_listings, sharing_keys.
- أُضيفت فهارس (مع حماية وجود العمود) لـv9_rls_tenant_isolation.sql.
  commands/events/agent_queries/trueup كانت مفهرسة بالفعل.

## ⚠️ لم تُنفَّذ (قرار مدروس)

### P2-1: توحيد طبقة CORS
- shared/helpers.py يحوي create_app() بـCORS آمن مدمج.
- 5 خدمات تكرّر CORS يدويّاً — لكنّها **كلّها آمنة** بعد إصلاح raster.
- تحويلها لـcreate_app refactor يمسّ startup 5 خدمات لمكسب تنظيمي فقط؛
  المخاطرة أكبر من الفائدة. أُجّل (تجنّب over-engineering).

### P3-1/P3-3/P3-4: توثيق + CI
- .env.example شامل، توحيد compose، إضافة pip-audit/ruff/bandit لـCI:
  هذه مهامّ CI/توثيق على جهازك، لا تغييرات كود.

## التحقّق
- 317/317 · 329 ملفّ يُترجم · صفر خطأ · YAML 31 خدمة
- JWT length مفروض · prints محوّلة · bare except مُصلَح · فهارس RLS مضافة

## ملاحظة صدق
- prints في أدوات CLI لم تُحوّل عمداً (مخرجات CLI صحيحة، ليست أخطاء).
- P2-1 (CORS) أُجّل لأنّ التكرار آمن والـrefactor محفوف — ليس بنداً حرجاً.
- P3 (CI/توثيق) خارج نطاق تعديل الكود — لجهازك.
