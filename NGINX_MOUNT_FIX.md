# إصلاح خطأ nginx + إجابات Odoo والمرايا

## ✅ كلّ الحاويات اشتغلت — والخطأ الأخير nginx فقط
إصلاحات الذاكرة (Odoo) والمرآة (RAG) نجحت. الخطأ الأخير مختلف تماماً.

## السبب الدقيق (واضح من رسالتك)
الخطأ: "Are you trying to mount a directory onto a file?"
- compose يطلب تركيب `./nginx/nginx.conf` → لكنّ **هذا الملفّ غير موجود**!
- المجلّد يحوي: nginx.v9.conf، nginx.unified.conf، nginx.light.conf،
  proxy_params.conf — لكن **لا nginx.conf**.
- حين لا يجد Docker الملفّ، **ينشئ مجلّداً فارغاً** مكانه، ثمّ يفشل لأنّه
  يحاول تركيب مجلّد على ملفّ داخل الحاوية.

## الإصلاح
وجّهتُ compose للملفّ الموجود الصحيح لـv9 (`nginx.v9.conf`، 26 مرجع خدمة):
```
nginx.v9.conf → /etc/nginx/templates/nginx.conf.template
   → nginx:alpine يعالج ${DOMAIN} بـenvsubst → /etc/nginx/nginx.conf
```
- استخدمتُ آليّة templates المدمجة في nginx:alpine (تعالج متغيّر DOMAIN)
- **حماية حاسمة**: `NGINX_ENVSUBST_FILTER=DOMAIN` يقصر البدل على DOMAIN فقط،
  فلا يُخرّب متغيّرات nginx الداخليّة (\$host، \$request_uri، \$rate_limit_key...)
- ركّبتُ proxy_params.conf أيضاً (الملفّ يضمّه 10 مرّات)
- أضفتُ DOMAIN=localhost لـ.env (نطاقك للإنتاج)

## التحقّق
- nginx.v9.conf موجود ✓ · proxy_params موجود ✓ · DOMAIN في .env ✓
- الفلتر يحمي 6 متغيّرات nginx داخليّة من التخريب

## بخصوص سؤالك: تهيئة Odoo الزراعي
صورة odoo:17.0 **عامّة** (ERP أساسي) — لا تأتي بوحدات زراعيّة جاهزة. للتهيئة
الزراعيّة تحتاج (خطوة لاحقة على جهازك بعد تشغيل Odoo):
1. تثبيت وحدات Odoo: المخزون (stock)، المحاسبة (account)، المشتريات
   (purchase) — وهي ما يزامنها odoo-bridge أصلاً.
2. إنشاء فئات منتجات زراعيّة (بذور/أسمدة/مبيدات) تطابق LedgerKind.
3. odoo-bridge يتولّى المزامنة تلقائيّاً بعدها.
لم أُهيّئ Odoo زراعيّاً لأنّ ذلك يتمّ عبر واجهة Odoo الحيّة على جهازك (لا كود).

## بخصوص "نماذج متعدّدة للمرآة عند الفشل"
PyPI لا يدعم fallback تلقائيّاً بين مرايا في pip مباشرةً، لكن الحلّ العملي:
- الافتراضي الآن **PyPI الرسمي** (يعمل عالميّاً) — الأكثر موثوقيّة.
- للمرآة الصينيّة (لو أردت): `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
- بديل علي بابا: `https://mirrors.aliyun.com/pypi/simple/`
- pip يدعم `--extra-index-url` لمرآة احتياطيّة، لكنّ الأبسط لك: ابقَ على PyPI
  الرسمي (نجح معك الآن).

## ملاحظة صدق
السبب مؤكّد 100% هذه المرّة (رسالتك واضحة + تأكّدت أنّ nginx.conf مفقود فعلاً).
تهيئة Odoo الزراعيّة لم أنفّذها لأنّها تتمّ عبر واجهة Odoo لا الكود — قول ذلك
أصدق من تزييف ملفّات وحدات. fallback المرايا غير مدعوم تلقائيّاً في pip —
شرحتُ البدائل بدل ادّعاء آليّة غير موجودة.
