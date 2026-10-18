# CAP-INT-004-INTEGRATION: INT-004B/C: تسليم الآلة وإثبات التنفيذ

حالة القرار: معلق لدى المالك. الحالة تبقى `open`. هذه وثيقة خيارات وعقد مقترح فقط؛ لا تفويض تنفيذ.

أساس المراجعة: `1765d73a036499318beeb6d267fdaf803e4b0a40` بعد دمج #1213. مراجع الأسطر إرشادية؛ النص المصدر هو المرجع.

## العطل والأدلة

INT-004A مغلق في السجل بحد إنشاء وإدامة الحزمة. generate_export_package يربط package_bytes وpackage_sha256 وprofile_snapshot. لا يجعل إنتاج ISOXML الجهاز قد استلمه أو نفذه؛ لا دليل CAN/ISOBUS جديد في هذه المراجعة.

- `services/sahool-platform/api/machinery_export.py:193`
- `services/sahool-platform/api/machinery_export.py:214`
- `sahool-brain/gaps/registry.md:116`

## التوصية وأسبابها

أوصي بعقد تطبيق versioned مستقل عن ادعاء مطابقة ISO11783: schema_version، receipt_id، tenant_id، artifact_id، package_sha256، machine_id، controller_id، firmware_version، machine_profile_id/profile digest، transfer_id، task_id، sequence، observed_at، received_at، status، reason_code، executed quantities/units عند توافر قياس، ودليل مصدر التأكيد وتوثيقه. تُفصل حالات received وvalidated وloaded وexecuted/partially_executed/rejected. إن لم يرجع الجهاز hash، يصرح العقد بأن إسناد البصمة مصدره gateway ولا يسمى تأكيداً تشفيرياً من الآلة.

## قبول التنفيذ بعد قرار المالك

- بايتات مستلمة تطابق SHA الأثر المدام؛ عدم تطابق hash/profile أو تغيير artifact يرفض.
- إيصال مكرر أو قديم أو خارج الترتيب أو من جهاز/مستأجر آخر لا يعيد التنفيذ ولا يغير الملكية.
- انقطاع النقل، رفض terminal، تحميل ناجح دون تنفيذ، تنفيذ جزئي، استعادة بعد انقطاع، ووحدات/معايرة؛ الاحتفاظ بالسجل الخام من جهاز أو محاك معتمد.
- TC-BAS لتوثيق العمل وTC-GEO لبيانات موقع التنفيذ/as-applied؛ اختبار زوج terminal/implement ونسخ firmware المحددة وفق إمكاناتهما. تأكيد gateway ليس وحده دليلاً فيزيائياً.

## الحدود ومستويات القبول

open للجزأين B وC. وثيقة CAP-INT-004BC.md فقط؛ لا محاك يقدم كدليل، ولا تعديل actuator أو المسارات المجمدة. hash يربط بايتات الحزمة لكنه لا يصادق هوية الجهاز؛ إن اختير توقيع JSON لاحقاً يحدد canonicalization صراحةً، ولا يغيّر hash ZIP القائم.

محلي: مراجعة مصدر ووثيقة فقط. CI: غير مقيس لهذه الوثيقة. staging: غير مقيس. الإنتاج: غير مقيس. لا هجرة ولا نشر ولا دليل جهاز بهذه الوثيقة.

## مراجع الممارسات

- [AEF — وظائف TC-BAS وTC-GEO وTC-SC](https://www.aef-online.org/aef-tour/)
- [AEF — اختبار توافق TC-GEO لبرمجيات FMIS](https://www.aef-online.org/aef-news/tc-geo-conformance-test-fmis.html)
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/info/rfc8785/)
- [W3C — PROV overview](https://www.w3.org/TR/prov-overview/)

## حقول رسالة التأكيد المقترحة

| الحقل | النوع والدلالة |
|---|---|
| schema_version | نص ثابت sahool.machine-receipt.v1؛ الإصدار المجهول يرفض |
| receipt_id | UUID فريد؛ إعادة الرسالة نفسها لا تعيد التنفيذ |
| tenant_id / artifact_id | هوية المستأجر ومعرف الأثر المدام؛ يسترجع المستقبِل الأثر داخل RLS |
| package_sha256 | 64 حرف hex لبصمة بايتات الحزمة الأصلية؛ لا تحسب على JSON أو ZIP معاد ضغطه |
| machine_id / controller_id | معرفان مرتبطان بهوية اتصال موثقة؛ لا تقبل قيم الجسم وحدها كهوية |
| firmware_version / machine_profile_id / profile_sha256 | نسخة العتاد ومرجع ملف الإمكانات وبصمته المطابقة للـprofile_snapshot |
| transfer_id / task_id | رابط جلسة النقل والمهمة على terminal؛ لا يساويان artifact_id ضمنياً |
| sequence | عدد صحيح متزايد لكل جلسة؛ التكرار المتطابق idempotent والمتعارض يرفض |
| observed_at / received_at | وقت الجهاز ووقت الاستقبال UTC؛ لا تثق بساعة الجهاز وحدها للترتيب |
| status | received، validated، loaded، executed، partially_executed، rejected |
| reason_code | سبب آلي مسمى إلزامي للرفض والتنفيذ الجزئي |
| execution | فترة العمل والكميات والوحدات والتغطية ومصدر القياس؛ المفقود unknown |
| evidence_source / raw_evidence_sha256 | machine أو gateway مع بصمة الدليل الخام ومكان حفظه؛ يصرح بمن قاس البصمة |

received لا يثبت loaded، وloaded لا يثبت تنفيذ كمية في الأرض. يتطلب executed دليلاً من جهاز أو محاك معتمد ضمن نطاق قبوله مع حفظ التنفيذ الجزئي. لا انتقال رجعي بناء على إيصال قديم؛ إعادة تشغيل الآلة تنشئ جلسة جديدة مرتبطة بالسجل السابق. توثيق الاتصال والتوقيع والاحتفاظ قرار لاحق؛ sha256 وحده ليس مصادقة. لا تغيير مخطط أو تنفيذ الآن.
