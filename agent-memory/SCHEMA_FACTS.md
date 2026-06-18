# حقائق المخطّط المكتشَفة (SCHEMA_FACTS.md)

> حقائق DB ثابتة اكتُشِفت من الهجرات. حدّثها عند اكتشاف عمود/قيد جديد. لا تفترض.

## القاعدة الحاكمة
> **لا تفترض أسماء أعمدة أو أنواعها — اقرأ ملفّ الهجرة المعنيّ أوّلاً.** إن لم تجد العمود/الجدول: **توقّف وأبلِغ**، لا تخترع اسماً.

## `fields`
- `field_id`: **`VARCHAR(50)` / TEXT** — **ليس UUID**. كلّ FK للحقل نصّيّ (راجع v18، v74، v75).
- `geom`: `geometry(Geometry, 4326)` — العمود المكانيّ للاستعلام (`ST_Within(g.geom, f.geom)`). أُضيف في `v43_fields_geom_index.sql` مع فهرس GIST.
- `geometry`: عمود نصّيّ قديم (GeoJSON) كمصدر؛ يُحوَّل إلى `geom`. **استخدم `geom` للمكانيّ، لا `geometry`، ولا عمود اسمه `boundary`.**

## طبقة الطقس (`v74_weather_intelligence.sql`)
- `field_weather_overlay`: `field_id` نصّ، `tenant_id`، `time`، أعمدة درجات (`spray_suitability_score`, `disease_risk_score`, `heat_stress_hours`, `frost_risk_hours`, `trafficability_score`)، `grid_cells_count`, `spatial_coverage`. PK يشمل `(tenant_id, field_id, time)`.
- `weather_signals`: `signal_type`, `confidence_score`, `time`, `valid_until`, `payload` (jsonb).
- `weather_grid` / `weather_forecasts`: **عالميّة بلا `tenant_id`** (موثّق في MANIFEST) — مرجعيّة مشتركة.
- RLS + FORCE على جداول المستأجرين بسياسة `current_setting('app.current_tenant', true)`.

## FOES (`v75_work_orders.sql`)
- `work_orders`: `field_id` نصّ، `tenant_id`، آلة حالات `planned → assigned → in_progress → done → verified` (+`cancelled`)، أنواع: `irrigation/fertilization/spraying/scouting/harvest`. RLS + FORCE.

## ثوابت RLS
- `USING`: `tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')`.
- `WITH CHECK`: يسمح بكتابة سياق-فارغ (نظام/هجرة).
- كلّ جدول مستأجر: `ENABLE` + `FORCE ROW LEVEL SECURITY`.
