# الخيار (ج) + تحسين الواجهات وتدفّق بيانات المستخدم

## الخيار (ج): بوّابة توجّه الويب للمنصّة الموحّدة
اكتشاف أثناء التنفيذ: المنطق الأساسي (sahool-platform، 143 endpoint) **لم يكن
منشوراً إطلاقاً** — لا Dockerfile ولا خدمة في compose. والبوّابة الفعليّة
Nginx (لا Kong كما توهّمت تعليقات الويب).

### ما نُفّذ
1. **نشر sahool-platform كخدمة**: Dockerfile جديد (ينسخ api/+core/+knowledge/)
   + إضافتها لـdocker-compose.v9.yml (الخدمة 30) + api/__init__.py للحزمة.
2. **توجيه Nginx (جوهر الخيار ج)**: في nginx.v9.conf
   - upstream `platform_backend` → sahool-platform:8000
   - `/api/v1/` → المنصّة (السطح الموحّد الكامل)
   - `/api/indicators/` → المنصّة (بدل الـstub الفارغ)
   - `/api/weather/` → المنصّة (بدل الـstub الرفيع)
   - `/api/soil/`, `/api/vegetation/` → خدماتها العاملة (دون تغيير)

النتيجة: الويب يستدعي مساراته كما هي، والبوّابة توجّهها شفّافاً للمنطق الفعلي.

## تحسين تدفّق بيانات المستخدم (الموبايل)
الفجوة: لو أقلع المستخدم offline (is_offline=true)، يبقى مُعلّماً offline
حتّى لو عادت الشبكة — حتّى إعادة تشغيل التطبيق.

### ما نُفّذ
- `refreshSession()` في authService: يُعيد التحقّق مع الـbackend دون إعادة
  تشغيل. ينجح → يرفع الحالة online + يحدّث بيانات المستخدم. 401 → خروج آمن.
- AuthContext: يكشف `refreshSession` للشاشات (pull-to-refresh أو عند عودة
  الاتّصال) لترقية الحالة بسلاسة دون فقدان الجلسة.

## التحقّق
- compose: YAML سليم (30 خدمة) · platform Dockerfile مساراته صحيحة
- backend: 283/283 · 6/6 CERTIFIED · py_compile سليم
- mobile: صفر أخطاء TypeScript

## ملاحظة صدق (الحدود)
- لا أستطيع تشغيل Docker/Nginx فعليّاً (لا بيئة) — تحقّقت بنيويّاً
  (YAML صالح، COPY مساراتها موجودة، التوجيه منطقيّ). التشغيل النهائي
  على جهازك: `docker compose -f docker-compose.v9.yml up -d --build`
- refreshSession يُكشف للشاشات لكن لم أربطه بمراقب NetInfo تلقائي (يتطلّب
  تبعيّة خارجيّة) — الشاشات تستدعيه عند pull-to-refresh أو نجاح طلب.
