# تكامل Copernicus Data Space (CDSE) كمزوّد Sentinel Hub

⚠️ **تنبيه أمان أوّلاً**: شاركتَ Client ID وSecret حقيقيّين في الدردشة. هما
الآن مكشوفان. **دوّرهما فوراً** من لوحة CDSE (احذف الـClient واصنع جديداً).
لم أضع أيّ سرّ في أيّ ملفّ مُسلَّم — الحقول فارغة، تملؤها محلّيّاً.

## ما كان موجوداً
موصّل CDSE (core/connectors/copernicus.py) كان موجوداً كهيكل:
- يستخدم sh.dataspace.copernicus.eu (CDSE الصحيح)
- المفاتيح من البيئة (CDSE_CLIENT_SECRET + CDSE_CLIENT_ID)
- لكن: URLs ثابتة، وتدفّق OAuth غير مُنفَّذ (هيكل فقط)

## ما أُضيف
1. **URLs قابلة للضبط من البيئة** (تطابق إعدادك الأربعة):
   - SH_BASE_URL (افتراضي sh.dataspace.copernicus.eu)
   - SH_TOKEN_URL (افتراضي identity.dataspace.copernicus.eu/.../token)
2. **تدفّق OAuth2 client_credentials فعلي** (fetch_access_token):
   - يطلب توكناً من SH_TOKEN_URL بالمفاتيح من البيئة
   - صدق: لا توكن وهمي — يُبلّغ عند غياب المفاتيح/httpx/فشل الاتّصال
3. **المتغيّرات الأربعة في .env (فارغة) + compose**:
   CDSE_CLIENT_ID, CDSE_CLIENT_SECRET, SH_BASE_URL, SH_TOKEN_URL

## CDSE مقابل Element84 (متى أيّهما؟)
- **Element84 Earth Search** (مستخدَم): مجّاني تماماً، بلا مفاتيح، STAC مباشر
  لتنزيل COG. الأفضل للبحث والتنزيل الخامّ.
- **CDSE Sentinel Hub** (مُضاف): يتطلّب OAuth، لكن يوفّر **معالجة سحابيّة**
  (Statistical/Process API + evalscripts) — يحسب NDVI/الملوحة سحابيّاً ويُرجِع
  النتيجة فقط (تحميل أقلّ — مهمّ لشحّ النطاق في اليمن).
- الاثنان مكمّلان: Element84 للتنزيل، CDSE للمعالجة السحابيّة الموفّرة للنطاق.

## التحقّق
- 476/476 roadmap (+4) · 0 خطأ ترجمة
- OAuth صادق (اختُبر: لا توكن بلا مفاتيح/httpx)
- لا سرّ حقيقي في أيّ ملفّ (تحقّقت بـgrep)

## ملاحظة صدق وأمان
- **دوّر مفاتيحك المكشوفة الآن.**
- تدفّق OAuth يعمل بنيويّاً؛ الاتّصال الفعلي بـCDSE يحتاج httpx + شبكة +
  مفاتيحك على جهازك. اختبرتُ مسارات الصدق (غياب المفاتيح/httpx).
- المفاتيح من البيئة حصراً — لا تُكتب في كود أو ملفّ مُسلَّم أبداً.
