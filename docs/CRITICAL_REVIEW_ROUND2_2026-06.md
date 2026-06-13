# مراجعة نقديّة — الجولة ٢ (باقي المشروع) — يونيو 2026

٥ وكلاء راجعوا: المصادقة/الصلاحيّات · بنية الأحداث/Outbox · كلّ الهجرات (init_v8→v50) ·
نواة التعلّم/التوصيات · إعدادات النشر (compose/nginx/odoo-bridge). أدناه كلّ ما **أُكِّد**،
مفصولاً: أُصلِح الآن · مؤجَّل بقرار (deploy/cross-service/agronomic).

## أُصلِح الآن (PR هذا — مع اختبارات)

| # | الخطورة | الموضع | الخطأ → الإصلاح |
|---|---------|--------|----------------|
| 1 | 🔴 حرجة | `events` CHECK (v11) | `entity_type` يرفض `activity`/`soil_lab_test` ⇒ **كلّ حدث نشاط وفحص تربة يُبتلَع صامتاً** (أحداث مفقودة لمجالين) → `v51`: توسيع القيد |
| 2 | 🔴 حرجة | `lifecycle_temporal_rejections` (v9) | جدول مستأجِر **بلا RLS** (تسرّب عبر المستأجرين) → `v51`: ENABLE+FORCE+policy |
| 3 | 🔴 عالية | `requeue_dead_letter`/`_all` (v48) | تمسّان `event_outbox` (بلا RLS) لكلّ المستأجرين ⇒ مدقّق مستأجِر يعيد جدولة موتى الجميع → `v51`: قصر عبر ربط `events` بمستأجِر السياق |
| 4 | 🔴 حرجة | `recommendation_log.py` | `provenance` (dict) يُكتَب CSV كـrepr ويُحمَّل نصّاً ⇒ `explain_recommendation` ينهار (سلسلة الـforensics/replay مكسورة) → JSON ترميز/فكّ |
| 5 | 🟠 عالية | `command_dispatcher.py` | `dispatch` لا يحرس حالة `PROCESSING` ⇒ نسخة متزامنة تُعيد التنفيذ (يكسر exactly-once) → حارس PROCESSING |
| 6 | 🟠 متوسّطة | `oauth_middleware.py` (MCP) | `tenant_id` افتراضيّ `"default"` عند غيابه (ضعف عزل) + لا حدّ لطول السرّ → رفض الغائب + سرّ ≥32 |

**1251 اختبار ناجح** (+٣ انحدار). الهجرة `v51` idempotent وتتحقّق ✓.

## مؤجَّل بقرار — يلزمه تنسيق نشر/بيئة حيّة (موثَّق، لم يُغيَّر)

### nginx/النشر (PR إعداد منفصل — لا يُتحقَّق في CI)
- 🔴 **`nginx.v9.conf` upstreams بأسماء قصيرة لا تطابق `container_name`** (`sahool-indicators`↛`sahool-indicators-service`، vegetation/weather/supervisor/guardrails) + **`sahool-frontend:80`** بينما الحاوية تستمع **8080** ⇒ 502 على مسارات الخدمات والـSPA، وقد لا يُقلِع nginx (اسم upstream لا يُحلّ). **تأكَّد ثمّ يُصلَح في PR إعداد.**
- 🟠 `soil_backend`/`/tts/`/`/metrics` تشير لخدمات غير موجودة؛ شبكة erpnext الخارجيّة بـ`COMPOSE_PROJECT_NAME` غير مضبوط؛ `.env.example` بـJWT_SECRET 28 محرفاً (<32) بلا فحص طول.

### عبر الخدمات (يلزم Redis denylist مشترك — موثَّق في SECURITY_AUTH_FOLLOWUP)
- 🟠 توكنات المنصّة 24س بلا تحقّق `iss`/`jti`/`is_active` ⇒ تسجيل الخروج/تعطيل المستخدم لا يُبطِل الوصول لنقاط البيانات. اختلاف RS256/HS256 وأسماء متغيّرات السرّ بين الخدمات.

### نمذجة زراعيّة (يلزم تحقّق ميدانيّ قبل التغيير — لا يُغيَّر أعمى)
- 🟠 `fao56.py`: `ke_factor` يُضرب في كامل ETc (يُضخّم النتح) بدل الجمع (FAO-56 dual-Kc: Kc=Kcb+Ke). يؤثّر على رقم الريّ للمزارع.
- 🟠 `deficit_irrigation.py`: مقارنة ECw (ماء) بعتبة ECe (تربة) دون تحويل ⇒ تحذير ملوحة في النقطة الخطأ.
- 🟡 `_emit_domain_event` يبتلع كلّ الأخطاء (يُخفي #1) — يُوصى بتضييق الالتقاط ليصرخ، **بعد** دمج v51 (وإلّا يُسقِط كتابات النشاط/التربة). 
- 🟡 NATS core fire-and-forget يُعلَّم `sent` قبل التأكيد (يلزم JetStream للضمان)؛ truthiness على 0.0 في `multi_season_analytics`؛ نطاقات `water_cost` غير متماثلة.

## نظيف ومُؤكَّد (لا تغيير)
- **المصادقة:** bcrypt cost-12، لا خلط خوارزميّات/`alg=none`، لا تصعيد دور (farmer مثبّت خادميّاً)، لا انتحال tenant (يُعاد فحص `req.tenant_id != user.tenant_id`)، MFA/قفل/تدوير refresh.
- **RLS:** كلّ جدول مستأجِر (≈50 جدولاً) معزول عدا الذي أُصلِح (#2). الـcast يطابق نوع UUID في كلّها.
- **idempotency الهجرات:** كلّها re-runnable؛ ترتيب الدوالّ سليم.
- **odoo-bridge:** منفذ 8126 صحيح، `ERP_PROVIDER=erpnext` افتراضيّاً في كلّ مكان، gating سليم، webhook HMAC fail-closed.
- **منافذ النشر:** الخدمات الداخليّة مربوطة بـ`127.0.0.1` (لا `0.0.0.0`)، أحجام named، restart policies سليمة.
