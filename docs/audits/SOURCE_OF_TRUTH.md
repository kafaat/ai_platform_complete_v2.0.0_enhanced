# المرجع النهائي للبيانات (Source of Truth) — SAHOOL v9

البند #8 (مراجعة 8). يحدّد **المرجع النهائي الواحد** لكلّ نوع بيانات، ويزيل
غموض "أيّ طبقة هي الحقيقة؟" الذي حذّرت منه المراجعة. مبني على فحص الترحيلات
والكود الفعلي (32 جدولاً).

## المبدأ الحاكم
لكلّ حقيقة **مرجع نهائي واحد** (writer). الطبقات الأخرى إمّا:
- **مشتقّة** (derived): تُحسَب/تُجمَّع من المرجع، لا تُكتَب مباشرةً
- **سجلّ** (log): تاريخ ثابت لا يُعدَّل (append-only)
- **كاش** (cache): نسخة مؤقّتة، المرجع غيرها

## الخريطة (المرجع النهائي لكلّ نوع)

### ١. الأحداث والحالة (Event Sourcing)
| النوع | المرجع النهائي | الطبقات المشتقّة/الساندة |
|-------|----------------|--------------------------|
| نيّة المستخدم (intent) | **commands** | — (المدخل الخام، قد يفشل) |
| ما حدث فعلاً (facts) | **events** | event_outbox (توصيل NATS)، append-only immutable |
| حالة الحقل الحاليّة | **field_lifecycle** | field_lifecycle_transitions (سجلّ الانتقالات) |
| نشر NATS | event_outbox | مشتقّ من events (نفس المعاملة atomic) |

**القاعدة**: commands = "طُلِب X" (قد يُرفَض). events = "حدث X" (حقيقة ثابتة).
field_lifecycle.current_stage = الحالة الحاليّة؛ transitions = كيف وصلنا.

### ٢. السجلّات والتتبّع (مشتقّة — ليست مرجعاً)
| الطبقة | الدور | المرجع الفعلي |
|--------|-------|----------------|
| data_lineage | **assembler فقط** — يقرأ ويجمّع | commands + events + transitions |
| audit_log | سجلّ تدقيق append-only | — (سجلّ، لا مرجع لحالة) |
| event_replay | يعيد بناء الحالة من events | events (المرجع) |
| guardrails_log | سجلّ قرارات الحماية | — (سجلّ) |

**حسم الغموض**: data_lineage **لا يملك حقيقة** — هو عدسة تجميع. لا تقرأ منه
كمرجع؛ المرجع هو commands/events/lifecycle التي يجمّعها.

### ٣. البيانات الزراعيّة
| النوع | المرجع النهائي | ملاحظة |
|-------|----------------|--------|
| حدود الحقل (geometry) | **field_boundaries** | PostGIS، fields يشير إليه |
| قراءات التربة | **soil_readings** | مع extraction_method (لا خلط) |
| NDVI/المؤشّرات الزمنيّة | **ndvi_timeseries** | السلسلة الزمنيّة الكاملة |
| مؤشّر لقطة واحدة | field_indicators | لقطة أحدث قيمة (مشتقّ/كاش من timeseries) |
| نتائج الحوسبة الطرفيّة | **edge_results** | مع idempotency_key + provenance |
| محاكاة WOFOST | **wofost_seasons** | — |
| الطقس المرصود | **weather_observations** | weather_automation_cache = كاش lat/lon |

**حسم الغموض (NDVI)**: ndvi_timeseries = المرجع الكامل. field_indicators =
لقطة أحدث قيمة للعرض السريع (مشتقّ). عند التعارض، timeseries يفوز.

### ٤. القرارات والموافقات
| النوع | المرجع النهائي |
|-------|----------------|
| طلبات الموافقة | **approval_workflows** (مع FOR UPDATE قفل) |
| سجلّ الحماية | guardrails_log (سجلّ، مشتقّ من القرار) |
| حالة سير العمل (Odoo) | workflow_states + workflow_transitions |

**ملاحظة**: workflow_states (Odoo bridge) منفصل عن field_lifecycle (دورة
حياة الحقل) — لا تداخل. الأوّل لسير عمل Odoo، الثاني لمراحل المحصول.

### ٥. الأصل والإعادة (Provenance)
| النوع | المرجع النهائي |
|-------|----------------|
| أصل نتيجة الراستر | provenance block داخل النتيجة (#7) + provenance_hash |
| معايرة | trueup_calibrations |
| استبيان الدخول | onboarding_responses |

## قواعد صارمة (لمنع الغموض مستقبلاً)
1. **لا تكتب حالة في طبقتين**. الحالة الحاليّة في field_lifecycle فقط؛
   events تروي القصّة، لا تُستعلَم كـ"الحالة الحاليّة".
2. **data_lineage/replay للقراءة فقط** — لا يكتبان حقيقة جديدة.
3. **الكاش يُعلَّم صراحةً** (weather_automation_cache, field_indicators) —
   لا يُعتمَد عند التعارض مع المرجع.
4. **events ثابتة** (immutable) — لا UPDATE/DELETE، فقط INSERT.
5. **commands قد تفشل**؛ events لا (حقيقة وقعت).

## ما يتبقّى (تحسين مستقبلي — قرارك)
- توحيد field_indicators لتكون VIEW مادّيّة من ndvi_timeseries (بدل جدول
  منفصل) — يلغي احتمال التعارض جذريّاً. تغيير schema، يحتاج قرارك.
- توثيق هذا كـADR (Architecture Decision Record) رسمي في المستودع.

## ملاحظة صدق
- مبني على فحص فعلي للترحيلات والكود (data_lineage يعرّف نفسه assembler،
  event_bus يوثّق commands vs events). لم أخترع البنية.
- البنية **سليمة أصلاً** — الطبقات لها أدوار واضحة. غموض المراجعة #8 كان
  نظريّاً أكثر منه فعليّاً؛ هذا التوثيق يجعل الأدوار صريحة لمنع انجراف مستقبلي.
- لم أغيّر كوداً — توثيق خالص (البند طلب توثيقاً، لا إعادة هيكلة).
