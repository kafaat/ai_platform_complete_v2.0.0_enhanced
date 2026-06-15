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

### عُولِجت لاحقاً (PR متابعة)
- ✅ `_emit_domain_event`: نُقِل بحث `EventType[name]` خارج `try` ⇒ اسم حدث مُخطئ يصرخ
  (KeyError) لا يُبتلَع صامتاً + حارس اختبار يتحقّق أنّ كلّ الأسماء المُصدَرة صالحة. (التقاط
  فشل الإصدار DB يبقى — تصميم availability متعمّد.)
- ✅ `multi_season_analytics`: تغيّر 0.0% (إنتاج مستقرّ) يُرجَع 0.0 لا None (`is not None`).

### نمذجة زراعيّة — **لا تُغيَّر أعمى** (تبسيطات موثَّقة، لا أخطاء؛ تغييرها يمسّ أرقام المزارع)
- `fao56.py`: النموذج **single-Kc** + `ke_factor` معامل تبخّر إقليميّ تجريبيّ (ضربيّ، مقصود).
  ترقيته لـdual-Kc (Kc=Kcb+Ke جمعيّ) يتطلّب بيانات Kcb لكلّ محصول + **تحقّق ميدانيّ** —
  تحسين مستقبليّ لا إصلاح.
- `deficit_irrigation.py`: تحذير ملوحة **heuristic** (لا حساب مُلزِم)؛ تحويل ECw→ECe يغيّر
  متى يظهر التحذير — يلزم معايرة ميدانيّة قبل التغيير.

### يلزم بنية حيّة (لا يُشحَن في الصندوق المعزول)
- توكنات 24س بلا إبطال `jti`/`is_active` (يلزم Redis denylist مشترك عبر الخدمات).
- NATS core fire-and-forget يُعلَّم `sent` قبل التأكيد (يلزم JetStream + PubAck للضمان).

## نظيف ومُؤكَّد (لا تغيير)
- **المصادقة:** bcrypt cost-12، لا خلط خوارزميّات/`alg=none`، لا تصعيد دور (farmer مثبّت خادميّاً)، لا انتحال tenant (يُعاد فحص `req.tenant_id != user.tenant_id`)، MFA/قفل/تدوير refresh.
- **RLS:** كلّ جدول مستأجِر (≈50 جدولاً) معزول عدا الذي أُصلِح (#2). الـcast يطابق نوع UUID في كلّها.
- **idempotency الهجرات:** كلّها re-runnable؛ ترتيب الدوالّ سليم.
- **odoo-bridge:** منفذ 8126 صحيح، `ERP_PROVIDER=erpnext` افتراضيّاً في كلّ مكان، gating سليم، webhook HMAC fail-closed.
- **منافذ النشر:** الخدمات الداخليّة مربوطة بـ`127.0.0.1` (لا `0.0.0.0`)، أحجام named، restart policies سليمة.
