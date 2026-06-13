# مراجعة نقديّة كاملة — الجولة ٣ (باقي السطح) — يونيو 2026

٧ وكلاء راجعوا: الخدمات المساعدة · خوادم MCP/البوتات · باقي وحدات api/core · الواجهة
(web+mobile) · جودة الاختبارات · تثبيت الأخطاء. أدناه كلّ ما **أُكِّد**، مفصولاً:
أُصلِح · يحتاج متابعة (موثَّق بالإصلاح الدقيق) · نظيف.

## أُصلِح (PRات هذه الجولة)

### الواجهة (#90)
- 🔴 **حرج:** بيانات اعتماد المدير مطبوعة على شاشة الدخول → أُزيلت + إيميل افتراضيّ فارغ.
- 🟠 التوكن خارج localStorage (XSS) · WebSocket يقرأ sessionStorage (كان 'demo') ·
  user_id الفعليّ (كان 1 ⇒ تسريب إشعارات) · إزالة `VITE_CLAUDE_API_KEY`.

### وحدات المنصّة (#91)
- 🟠 `cross_reference_finder` outcome_quality: `error_pct` نسبة مئويّة ÷100 (كان يصفّر أيّ خطأ >1%).
- 🟠 `feedback_closure`: TypeError على `issued_date` aware (+00:00) — توحيد naive.
- 🟠 `data_readiness`: تلميح الدقّة ينقلب فارغاً عند المستوى 6 — قصّ المفتاح.

### الخدمات (هذا الـPR)
- 🔴 **supervisor-agent IDOR:** `/agent/tools` · `/agent/journal/{id}` · `/agent/actuator-audit`
  كانت **بلا مصادقة** وبـtenant من query ⇒ أيّ زائر يقرأ سجلّ actuator (ريّ/مضخّات)
  لأيّ مستأجِر → أُضيفت `Depends(_get_current_user)` + tenant من التوكن + admin للـaudit.
- 🔴 **market-mcp tenant من الجسم:** `/mcp/v1/tools/call` كان يهمل payload الـscope ويأخذ
  `tenant_id` من الجسم (set_config + WHERE) ⇒ قراءة/كتابة عابرة المستأجرين → حقن tenant
  المُتحقَّق + `market:write` لأدوات الكتابة (كانت بـread).
- 🔴 **notification-agent معطّل:** `dispatch` ينادي `broadcast_user`/`broadcast_all` غير
  الموجودين ⇒ AttributeError يُعطّل **كلّ** الإشعارات + حلقة redelivery → `send_to_user`/`broadcast`.
- 🟠 **weather-mcp معطّل:** `retry_request(client.get(...))` يمرّر coroutine بدل callable ⇒
  كلّ نداء طقس يفشل → `retry_request(client.get, url, ...)`.

## يحتاج متابعة — مؤكَّد + الإصلاح الدقيق (لم يُنفَّذ بعد، خدمات بلا اختبارات هنا)
- 🟠 **raster-service path traversal/SSRF** (`main.py:1213,822,1475`): `rasterio.open(raster_url)`
  بلا تحقّق ⇒ `file:///etc/passwd` أو SSRF. **الإصلاح:** قائمة بيضاء للمخطّطات +
  `realpath` تحت `UPLOAD_DIR` لـ`file://`.
- 🟠 **market-mcp REST writes** (`/procurement`, `/sales-listing`): تمرّر `body` للمعالِج ⇒
  انتحال tenant. **الإصلاح:** حقن `user["tenant_id"]` كما في مسار MCP.
- 🟠 **raster `/process` tenant من الجسم** + `fetch_latest_asset` بلا فلتر tenant. **الإصلاح:**
  فكّ التوكن واشتقاق tenant + `AND tenant_id=$N`.
- 🟡 **actuator-service:** `limit` بلا حدّ أعلى → `Query(50, ge=1, le=500)`؛ وغياب set_config
  للـRLS قبل الاستعلام.
- 🟡 **raster div-by-zero:** NDVI/GNDVI/NDWI/MSI بلا epsilon (VARI/GLI لديها) → وحّد الحارس.
- 🟡 **notification/supervisor:** نقاط `/notifications/test` بلا مصادقة (انتحال/حقن NATS)؛
  رسالة خطأ التوكن تسرّب تفاصيل PyJWT.
- 🟡 **trueup compounding** · **evidence_class low_plus** · **farm_memory/data_lineage** مقارنات
  نصّيّة — موثّقة (لبس تصميم/دفاع عميق).

## فجوات اختبار عالية الأثر (وكيل الجودة) — تُقترَح إضافتها
وحدات بلا اختبار: `workflow_engine` (Saga/تعويض)، `pest_escalation_flow` (تعليق الموافقة)،
`irrigation_water_analysis` (SAR/RSC — نقيّ سهل)، `agronomic_state_engine` (أرجحيّة الملوحة
فوق NDVI). واختبارات ضعيفة (نوع/وجود فقط): `test_remaining_engines` (diesel/organic_matter)،
`test_governance_modules` (who_can)، `test_field_geocode` (المحافظة لا تُتحقَّق).

## نظيف ومؤكَّد
guardrails-engine (مصادقة/حسابات) · local-ai-rag (عزل tenant + grounded + ingest مُبوَّب) ·
telegram-bot (polling، أفعال حسّاسة خلف /link) · sentinel/wofost MCP · mobile Flutter (secure
storage، fail-closed، TLS خلف debug) · لا أسرار حيّة مُودَعة · لا تثبيت أخطاء في اختبارات العلوم.
