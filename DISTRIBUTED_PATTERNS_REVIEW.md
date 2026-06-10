# مراجعة 15 مشروعاً موزّعاً — تصنيف وبناء

المراجعة اقترحت 15 مشروعاً (Kafka/NATS/Kestra/Neo4j/OpenTelemetry...). وفق
المبدأ: تصنيف بنية-تشغيل مقابل كود، والبناء للفجوة الحقيقيّة فقط.

## التصنيف
| الفئة | المشاريع | قرار |
|------|---------|------|
| بنية تشغيل (infra على النشر، لا كود) | Kafka, NATS*, K3s, Grafana, Flink, ThingsBoard, TileServer, Home Assistant, Kestra, Prefect, Dagster | لا تُبنى (نسخها = هياكل وهميّة). *NATS مستخدَم أصلاً |
| DB رسوم (Neo4j/Memgraph) | knowledge graph | بنية تشغيل — النمط (ربط سببي) مغطّى جزئيّاً بـcorrelation |
| data lineage (dbt) | data_lineage.py | مغطّى |
| **تتبّع موزّع (OpenTelemetry)** | trace موحّد | **فجوة حقيقيّة — بُنيت** ✅ |

## الفجوة الحقيقيّة: Correlation/Trace موحّد
تأكّد: النظام يملك operation_id/workflow_id/event_id/command_id لكنّها
**منفصلة** — لا خيط يربط السلسلة عبر الخدمات. events يربط command_id فقط
(ربط محلّي). عند تتبّع "أيّ workflow أنتج أيّ event أنتج أيّ command؟" لا رابط.

## ما بُني: core/correlation.py
طبقة ربط خفيفة نقيّة-بايثون (نمط OpenTelemetry بلا collector/agent ثقيل):
- **correlation_id**: ثابت طوال السلسلة (الطلب عبر الخدمات)، عبر contextvars
  (انتشار async تلقائي).
- **انتشار عبر الخدمات**: correlation_headers() + from_headers() (X-Correlation-Id).
- **causation_id**: من أنتج من → build_trace_tree يبني الشجرة السببيّة الكاملة
  (op→workflow→command→events).
- **صدق**: كشف اليتيم (سبب مفقود) لا يُخفى؛ غياب السياق يُعلَن (None، لا اختراع).
- **موصول live** بنقطة field-intelligence (correlation_id في الرد).

## التحقّق (مُختبَر حيّاً)
- 703/703 roadmap (+6) · 0 خطأ (420 ملفّ)
- توليد + انتشار رؤوس ✓ · تواصل عبر الخدمات ✓ · شجرة سببيّة كاملة ✓ ·
  كشف يتيم ✓ · link تلقائي ✓ · موصول live ✓

## ما لم يُبنَ (صدق)
- **Kafka/NATS/Flink كاملاً**: بنية تشغيل — NATS مستخدَم أصلاً؛ Kafka/Flink
  تُضافان على النشر إن لزم (لا كود يُكتب في المستودع).
- **Neo4j knowledge graph**: DB رسوم (بنية تشغيل). النمط السببي مغطّى الآن
  بـcorrelation trace tree (op→workflow→event). graph DB كامل = قرار infra
  مستقبلي (ADR)، لا هيكل وهمي offline.
- **Kestra/Prefect/Dagster**: محرّك workflow عندنا (workflow_engine) يكفي
  الآن؛ هذه بدائل ثقيلة (نفس مبدأ عدم استنساخ Temporal).
- **OTel collector/exporter الفعلي**: بنيتُ correlation context (الكود)؛
  التصدير لـJaeger/collector بنية تشغيل تُضاف على النشر.

## ملاحظة صدق
صنّفتُ 15 مشروعاً، بنيتُ الفجوة البرمجيّة الوحيدة (correlation موحّد) خفيفةً
مناسبةً — لا استنساخ infra. مُختبَرة حيّاً وموصولة. الحدّ المعلَن: الطبقة تربط
المعرّفات منطقيّاً (correlation context + شجرة سببيّة)؛ التصدير لأداة تتبّع
حيّة (Jaeger/Grafana Tempo) + ربط كلّ event/command بالـcorrelation في DB
خطوة تشغيل تالية. لم أبنِ Kafka/Neo4j/collector لأنّها بنية تشغيل لا كود.
