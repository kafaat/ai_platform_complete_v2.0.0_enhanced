# إصلاح ثغرات المراجعة الخارجيّة (12 مسار)

## 🔴 RLS — كان جزئيّاً ومسرّباً، الآن مُغلق

### ثغرة fail-open (الأخطر)
- السياسات كانت: `... OR app.current_tenant IS NULL OR = ''` → أيّ اتّصال
  بلا GUC يرى **كلّ صفوف كلّ المستأجرين** (IDOR).
- الإصلاح: حُذفت فروع NULL/'' من v10/v11/v12 + الدالّة → **fail-closed**
  (لا GUC = صفر صفوف).

### نقاط القراءة الخام (كانت تتجاوز tenant_connection)
- LineageAssembler/EventBus/CommandStore/SharingKeyService كانت تكتسب pool
  خاماً (بلا GUC) → مع fail-closed كانت سترجع صفر، ومع fail-open كانت تسرّب.
- الإصلاح: الكلاسات تقبل conn اختياريّاً؛ 6 endpoints (lineage/events/
  commands/sharing×2) تمرّر conn من tenant_connection → RLS مُطبَّق فعليّاً.

## 🔴 supervisor body-trust (Lane 10)
- user_id/tenant_id كانا من جسم الطلب (قابل للتزوير) → حامل أيّ توكن ينتحل
  أيّ مستأجر. + JWT_SECRET فارغ كان يُقبل.
- الإصلاح: الهويّة من user["sub"]/["tenant_id"] (التوكن المُتحقَّق) +
  فشل-مغلق على سرّ <32 حرفاً.

## 🟠 بقيّة المسارات
- actuator /commands (قراءة): كان tenant_id="default" مكشوفاً → الآن
  Depends(_verify_token) + tenant من التوكن.
- odoo webhook: != → hmac.compare_digest (ضدّ هجوم التوقيت).
- Lane 9 (كتابة بلا مصادقة): raster /imagery/search + /process، agriai
  /recommend، edge (3) → كلّها x_agent_token الآن.
- bot healthcheck: compose كان curl :8000 (البوت polling بلا HTTP) → pgrep
  (يطابق Dockerfile) + أُزيل JWT_SECRET المهمل.
- MarkdownV2 (Lane 6): أُضيف _md2() escape + طُبّق على health_status
  الديناميكي (كان يسبّب 400 مع نقاط/أقواس).

## compose
- SAHOOL_AGENT_TOKEN أُضيف لـedge (يتطلّبه الآن) + كتلة agriai المعلّقة.

## التحقّق
- 326/326 (+3 RLS) · 329 ملفّ يُترجم · YAML 31 خدمة
- اختبار RLS: fail-closed + tenant_connection + supervisor identity

## ⚠️ ملاحظة صدق حرجة
- **fail-closed يعني**: أيّ سكربت/migration يستعلم بلا ضبط app.current_tenant
  سيرى صفر صفوف. للعمليّات الإداريّة استخدم دور BYPASSRLS منفصل (لا تتّصل
  بـsahool_user للإدارة العابرة للمستأجرين).
- لم أشغّل PostgreSQL — التحقّق بنيويّ. **اختبر العزل حيّاً** (مستأجران A/B،
  set app.current_tenant=A، أكّد استعلام B = صفر).
- **دوّر كلّ الأسرار**: .env حُذف من الأرشيف لكن قيمه شُحنت سابقاً مرّة.
- agriai معلّق في compose (لا أثر حيّ حتّى التفعيل).
