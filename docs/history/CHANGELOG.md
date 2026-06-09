# CHANGELOG — SAHOOL

## [9.2.0] — 2026-06-06

### طبقة الذكاء المناخي-الزراعي (Climate Intelligence Layer)
- `agro_climate_zones`: 6 أقاليم مناخيّة-زراعيّة موثّقة (CEFAS) + تصنيف
  بالارتفاع + معالجة المحافظات متعدّدة الأقاليم (تعز/حضرموت)
- `geo_zone_locator`: إحداثيّات GPS → محافظة + إقليم + مناخ (FAO GAEZ +
  وزارة الزراعة اليمنيّة). الارتفاع يحسم في المحافظات الجبليّة-الساحليّة
- `seasonal_risk`: نوافذ المخاطر الموسميّة (حرّ/صقيع/مطر) + حاسبة ساعات
  البرودة (تفسّر علميّاً تصنيف التفاح للمرتفعات)
- `climate_analogs`: 5 مناطق عالميّة مشابهة (الجوف السعوديّة/النقب/أريزونا/
  المغرب/أستراليا) + محاصيلها المثبتة — مربوطة تلقائيّاً بتوصيات الصحراء
- `propagation_advisor`: الإكثار الخضري + اختيار الأصل المقاوم (نهج نجران)
- `crop_introduction`: مراجعة مناخيّة — منطقة HIGHLAND، التفاح/البنّ
  مُستبعدان من السهول الحارّة بصدق
- `seed_and_practices`: حساب الإنبات + قاعدة التخزين + عمق البذر

### التوثيق
- SYSTEM_INDEX.md: فهرس التدفّق المتكامل (GPS → قرار الزراعة)
- مراجعات: AGRO_CLIMATE_ZONES, GEO_LOCATOR, CLIMATE_DOC, PROPAGATION

### التحقّق
- اختبارات الوحدات: 209/209 · e2e: 9/9 · Qualification: 6/6 CERTIFIED
- backend: 121 endpoint · لا تكرار مسارات · 57 ملفّ api سليم

### مبدأ الصدق
- لا اختراع أصناف يمنيّة · المناطق المشابهة للصحراء الداخليّة فقط
- إقرار الطموح البعيد (لا تنبّؤ مناخي 10 سنوات، لا microclimate بلا مستشعرات)

## [9.1.0] — 2026-05-20

### الإضافات الجديدة
- Auth: Refresh tokens + JWT revocation (jti) + Account lockout + Password reset
- DB: v9_foundation.sql — users/fields/notification_preferences/audit_log
- Services: odoo-bridge, local-ai-rag, actuator-service, video-processor
- Firmware: ESP32 mesh gateway
- OpenTelemetry instrumentation
- MinIO bucket auto-creation
- retry_request() circuit breaker helper

### الإصلاحات
- 43+ إصلاح مُتحقق من تقارير المراجعة
- صفر أخطاء بناء Python
- RLS: pg_has_role bypass مُزال
- nginx: HSTS + proxy_params + upstreams موحّدة

## [9.0.0] — 2026-05-18

- النسخة الأولى من v9 مع MCP servers, Supervisor Agent, Guardrails Engine
