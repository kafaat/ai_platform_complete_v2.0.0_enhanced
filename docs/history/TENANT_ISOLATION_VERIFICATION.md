# التحقّق من عزل المستأجرين (RLS) — فحص بنيويّ شامل

## سلسلة العزل (٣ حلقات)

### ١. ضبط السياق (الكتابة) — متّسق ✓
كلّ الكود يضبط app.current_tenant:
- platform: tenant_connection() (SET LOCAL في معاملة)
- auth, shared/helpers, mcp_servers/*, market_server (12 موضع)
لا تضارب بعد إصلاح P0-1.

### ٢. السياسات (القراءة) — موحّدة ✓
17 موضع current_setting كلّها app.current_tenant (صفر app.tenant_id بعد
إصلاح v10/v11/v12).

### ٣. التطبيق على الجداول — اكتُشفت فجوتان وأُصلحتا

#### 🔴 فجوة ١: FORCE مفقود (الأخطر)
- سياسات v10/v11/v12 (commands, field_lifecycle, events,
  trueup_calibrations, sharing_keys) كانت بـENABLE فقط بلا FORCE.
- **التطبيق يتّصل بـsahool_user = مالك الجداول**. في PostgreSQL، المالك
  **يتجاوز RLS العادي تلقائيّاً** ما لم يُفعَّل FORCE.
- النتيجة: العزل على هذه الجداول الخمسة **كان معطّلاً فعليّاً** رغم وجود
  السياسات!
- الإصلاح: أُضيف FORCE لها في v9_rls_tenant_isolation.sql (حلقة force_only).

#### 🟠 فجوة ٢: soil_readings بلا RLS
- الجدول فيه tenant_id (وفهرس عليه) ويخزّن قراءات مستشعرات حسّاسة، لكن لا
  سياسة RLS → مستأجر A يقرأ بيانات B.
- الإصلاح: أُضيف soil_readings لمصفوفة الجداول في v9_rls_tenant_isolation.

## خريطة التغطية النهائيّة (11 جدول)
| الجدول | سياسة | FORCE |
|--------|-------|-------|
| fields, field_lifecycle_transitions, field_tasks, agent_queries, market_sales_listings, soil_readings | دالّتي | ✓ (الدالّة تطبّق FORCE) |
| commands, field_lifecycle, events, trueup_calibrations, sharing_keys | v10/v11/v12 | ✓ (أُضيف الآن) |

## التحقّق
- 319/319 (+2 RLS) · SQL بنيويّاً سليم (DO/END/FOREACH متوازنة)
- اختبار: variable consistency + FORCE + soil_readings

## ملاحظة صدق (حدود حرجة)
- **لم أشغّل PostgreSQL** — هذا فحص بنيويّ. التحقّق الوظيفي الفعلي ضروري:
  اختبار حيّ يُنشئ مستأجرين A/B، يكتب صفوفاً لكلٍّ، يضبط app.current_tenant=A،
  ويؤكّد أنّ استعلام B يُرجع صفر صفوف. هذا لا يُغني عنه الفحص الساكن.
- اكتشاف FORCE المفقود **حرج** — لو صحّ على قاعدتك، فالعزل لم يكن يعمل على
  5 جداول. طبّق v9_rls_tenant_isolation.sql فوراً وتحقّق بـ:
    SELECT relname, relrowsecurity, relforcerowsecurity
    FROM pg_class WHERE relname IN ('commands','events','fields','soil_readings');
  (يجب relforcerowsecurity=true للكلّ)
- ترتيب التطبيق: init/v8 → v9_foundation → v10/v11/v12 → v9_rls_tenant_isolation
  (الأخير يضيف FORCE فوق سياساتها).
