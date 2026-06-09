# إصلاح المكوّنات غير المُراجَعة (10 مسارات)

## 🔴 A1: firmware — الحلقة الأضعف (كان ينقض تأمين actuator)
- mqttCallback كان يشغّل الـrelay من أيّ حمولة MQTT بلا تحقّق → أيّ طرف ينشر
  على الموضوع يفتح الصمّامات، متجاوزاً JWT الذي أمّنّا به actuator-service.
- الإصلاح (طبقة التوقيع — قابلة للتطبيق في الكود):
  - firmware: verifyCmdHmac() — HMAC-SHA256(secret, cmd+"|"+ts) عبر mbedTLS
    المدمجة. يرفض أيّ أمر بلا توقيع صالح (CMD_HMAC_SECRET فارغ → رفض الكلّ).
  - actuator: send_mqtt_command يوقّع الآن بنفس الصيغة (CMD_HMAC_SECRET).
- يبقى عليك (قرارات نشر، خارج الكود):
  - ضبط CMD_HMAC_SECRET مطابقاً في الجهاز (NVS) وactuator (.env)
  - تفعيل TLS للـMQTT (tlsClient المعلّق)
  - ACLs على الوسيط: actuator-service فقط ينشر على /command

## ⚠️ A10: جداول الأتمتة خارج العزل
- imagery_automation_fields (يخزّن bbox لكلّ حقل) كان بلا tenant_id/RLS.
- الإصلاح: أُضيف tenant_id (ADD COLUMN IF NOT EXISTS — idempotent) + فهرس +
  أُدرج في مصفوفة RLS (policy + FORCE). weather_cache (lat/lon) محايد — تُرك.

## ⚠️ A2: توكن الواجهة في sessionStorage (لم يُغيَّر — قرارك)
- useAuth يخزّن JWT في sessionStorage (عرضة لـXSS). التحويل لكوكي
  HttpOnly;Secure;SameSite يتطلّب backend يضبط الكوكي + تعديل تدفّق المصادقة
  كاملاً — تغيير معماري واسع. لم أطبّقه (يحتاج قرارك + تنسيق backend/frontend).
  تخفيف جزئي: إزالة 'unsafe-inline' من CSP (لكن قد يكسر أنماطاً مضمّنة).

## النظيف (لا تغيير)
- A3 nginx محصّن · A4 CI جيّد · A5 MCP (require_scope — أقوى من JWT عادي)
- A6 video-processor مصادَق · A7 RAG لا حقن · A8 Flutter secure_storage
- A9 notification/tts سليم

## التحقّق
- 330/330 · 329 ملفّ يُترجم · firmware HMAC مضاف (3 مراجع)
- imagery: tenant_id + RLS

## ملاحظة صدق
- firmware (.ino) لا يُترجَم في بيئتي (يحتاج Arduino IDE + mbedTLS). راجعتُ
  منطق HMAC نصّيّاً؛ اختبر البناء فعليّاً على الجهاز.
- A1 الكامل يحتاج 3 طبقات (توقيع + TLS + ACL). طبّقتُ التوقيع (كود)؛ الباقي
  قرارات نشر على بنيتك.
- A2 (كوكي HttpOnly) أُجّل — تغيير معماري يحتاج تنسيقك.
