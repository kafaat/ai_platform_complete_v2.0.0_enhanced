# تقارير التدقيق والمراجعة (Audits & Reports)

نُقلت هذه التقارير (مراجعات الكود، التدقيقات، استجابات المراجعة، سجلّات الإصلاح)
من جذر المستودع إلى `docs/audits/` لتخفيف ازدحام الجذر مع حفظ تاريخ git (`git mv`).
بقي في الجذر فقط `README.md`.

> ملاحظة: هذه وثائق سرديّة تاريخيّة (snapshots)؛ المرجع الحيّ للحقيقة هو الكود و `invariants.yaml`.

| الملف | الموضوع |
|------|---------|
| [`ADDITIONAL_PROVIDERS.md`](./ADDITIONAL_PROVIDERS.md) | مزوّدون إضافيّون لصور الأقمار — تحقّق وتوسيع |
| [`AGRONOMIC_CORE_REVIEW.md`](./AGRONOMIC_CORE_REVIEW.md) | مراجعة النقد المعماري — ما صحّ وما لم يصحّ |
| [`AGRONOMIC_STATE_ENGINE.md`](./AGRONOMIC_STATE_ENGINE.md) | طبقة الغراء: agronomic_state_engine (الحالة الزراعيّة الموحّدة) |
| [`BACKUP_AND_MIGRATIONS.md`](./BACKUP_AND_MIGRATIONS.md) | النسخ الاحتياطي/الاستعادة + هيكل الهجرات — النتيجة |
| [`CDSE_PROVIDER_INTEGRATION.md`](./CDSE_PROVIDER_INTEGRATION.md) | تكامل Copernicus Data Space (CDSE) كمزوّد Sentinel Hub |
| [`CODE_REVIEW_REPORT.md`](./CODE_REVIEW_REPORT.md) | تقرير مراجعة الكود — منصة SAHOOL v9 الزراعية-المناخية |
| [`COHESION_ENDPOINTS_LIVE.md`](./COHESION_ENDPOINTS_LIVE.md) | إكمال تغذية Runtime Cohesion: النقطتان الحيّتان |
| [`CORE_DECISION_MD_REVIEW.md`](./CORE_DECISION_MD_REVIEW.md) | مراجعة md النواة والقرار — المؤشّرات والمدخلات والتقويم الناقص |
| [`CORE_WIRING_COMPLETE.md`](./CORE_WIRING_COMPLETE.md) | إكمال الربط: كلّ المؤشّرات + المدخلات + التقويم الزراعي |
| [`CORRELATION_WIRING.md`](./CORRELATION_WIRING.md) | ربط الـcorrelation بـworkflow_engine + event_bus |
| [`CRITICAL_REVIEW_RESPONSE.md`](./CRITICAL_REVIEW_RESPONSE.md) | الردّ على تقرير المراجعة الحرج (C1–C5 + H1–H8) |
| [`DEAFRICA_AND_3M_PROVIDERS.md`](./DEAFRICA_AND_3M_PROVIDERS.md) | دمج Digital Earth Africa + إجابة الدقّة 3 أمتار |
| [`DECISION_RULES_VERIFICATION.md`](./DECISION_RULES_VERIFICATION.md) | تحقّق قواعد القرار (Decision Rules) |
| [`DECISION_SOURCES_COMPLETENESS.md`](./DECISION_SOURCES_COMPLETENESS.md) | مراجعة مصادر القرار: الاكتمال والربط — ملخّص |
| [`DEEP_TEST_AUDIT.md`](./DEEP_TEST_AUDIT.md) | الجولة الخامسة — تدقيق المجموعة الكاملة وإصلاح كل الفشلات/الفجوات |
| [`DEPENDENCY_CONSISTENCY_AUDIT.md`](./DEPENDENCY_CONSISTENCY_AUDIT.md) | تدقيق تطابق إصدارات المكتبات والاعتماديّات |
| [`DISTRIBUTED_PATTERNS_REVIEW.md`](./DISTRIBUTED_PATTERNS_REVIEW.md) | مراجعة 15 مشروعاً موزّعاً — تصنيف وبناء |
| [`ECONOMICS_CULTIVAR_INTENT_WIRING.md`](./ECONOMICS_CULTIVAR_INTENT_WIRING.md) | ربط الاقتصاد + الأصناف + نيّة المزارع بالمنسّق |
| [`ERPNEXT_COST_BOOKING_READY.md`](./ERPNEXT_COST_BOOKING_READY.md) | تهيئة ERPNext push_field_cost للربط (أفضل الممارسات) |
| [`ERPNEXT_SETUP_GUIDE.md`](./ERPNEXT_SETUP_GUIDE.md) | دليل تهيئة ERPNext لـSAHOOL (نشر + إعداد زراعي) |
| [`ERP_PROVIDER_SWITCH.md`](./ERP_PROVIDER_SWITCH.md) | مفتاح تبديل مزوّد ERP + حاوية ERPNext |
| [`ERROR_AUDIT_FINDINGS.md`](./ERROR_AUDIT_FINDINGS.md) | تدقيق فئات الأخطاء — فحص فعلي لا نظري |
| [`EXCEPTION_HYGIENE_CAMPAIGN.md`](./EXCEPTION_HYGIENE_CAMPAIGN.md) | حملة exception hygiene — النتيجة |
| [`FIELD_INTELLIGENCE_COORDINATOR.md`](./FIELD_INTELLIGENCE_COORDINATOR.md) | الربط الكامل: field_intelligence_coordinator (مسار التنفيذ) |
| [`FIRMWARE_HARDENING.md`](./FIRMWARE_HARDENING.md) | تقوية الfirmware — replay window + watchdog |
| [`FIXES_APPLIED.md`](./FIXES_APPLIED.md) | الإصلاحات المُطبَّقة — استجابة لتقرير المراجعة (SAHOOL v9) |
| [`FOLLOWUP_FIXES.md`](./FOLLOWUP_FIXES.md) | الجولة الثالثة — إصلاح النتائج المتبقّية + الثغرات |
| [`FOUR_PROPOSALS_COMPLETE.md`](./FOUR_PROPOSALS_COMPLETE.md) | تنفيذ المقترحات الأربعة (بالترتيب) |
| [`GOVERNANCE_EXPLAINABILITY_RESPONSE.md`](./GOVERNANCE_EXPLAINABILITY_RESPONSE.md) | الردّ على مراجعة الحوكمة والتفسير — تحقّق + جسر صغير |
| [`IDEMPOTENCY_CHAIN_ANALYSIS.md`](./IDEMPOTENCY_CHAIN_ANALYSIS.md) | تتبّع idempotency عبر السلسلة كاملةً — فحص فعلي |
| [`INVARIANT_MANIFEST.md`](./INVARIANT_MANIFEST.md) | Invariant Manifest — تنفيذ مكيّف (مراجعة 11/12) |
| [`JWT_AUDIENCE_CONSISTENCY.md`](./JWT_AUDIENCE_CONSISTENCY.md) | اتّساق JWT audience — لماذا أبقيتُ نسختي لا المرفوع |
| [`KNOWLEDGE_BASE_VERIFICATION.md`](./KNOWLEDGE_BASE_VERIFICATION.md) | تحقّق قاعدة المعرفة (Knowledge Base) |
| [`LAYERS_IMPLEMENTATION_STATUS.md`](./LAYERS_IMPLEMENTATION_STATUS.md) | هل نُفّذ نموذج الطبقات الـ15 في الكود؟ — الإجابة الصادقة |
| [`LAYERS_REVIEW_RESPONSE.md`](./LAYERS_REVIEW_RESPONSE.md) | الردّ على مراجعة الطبقات الـ15 — تحقّق بالكود |
| [`LINT_DEBT_AND_HEALTH.md`](./LINT_DEBT_AND_HEALTH.md) | الجولة السادسة — معالجة دين lint + صحّة الحاويات (15 وكيلًا متوازيًا) |
| [`LOCAL_AI_RAG_BUILD_FIX.md`](./LOCAL_AI_RAG_BUILD_FIX.md) | إصلاح فشل بناء local-ai-rag (pip exit code 1) |
| [`MD_REVIEW_COMPREHENSIVE.md`](./MD_REVIEW_COMPREHENSIVE.md) | مراجعة شاملة لملفّات md — الاتّساق والتكرار والقِدَم |
| [`MOBILE_APP_REVIEW.md`](./MOBILE_APP_REVIEW.md) | مراجعة تطبيق الموبايل (Flutter) — فحص فعلي للكود |
| [`MOBILE_P0_P1_FIXES.md`](./MOBILE_P0_P1_FIXES.md) | إصلاحات الموبايل P0 + P1 — تحت الفشل والتزامن |
| [`NATIVE_LIVE_VERIFICATION.md`](./NATIVE_LIVE_VERIFICATION.md) | تحقّق حيّ أصيل (Native) — بلا صور Docker |
| [`NEW_TESTS_AND_FIXES.md`](./NEW_TESTS_AND_FIXES.md) | الجولة الرابعة — إصلاح كل الأخطاء + اختبار الجوانب غير المُختبَرة |
| [`NGINX_MOUNT_FIX.md`](./NGINX_MOUNT_FIX.md) | إصلاح خطأ nginx + إجابات Odoo والمرايا |
| [`ODOO_DB_INIT_FIX.md`](./ODOO_DB_INIT_FIX.md) | إصلاح: Odoo — قاعدة منفصلة + تهيئة base |
| [`ODOO_ECONOMIC_BRIDGE.md`](./ODOO_ECONOMIC_BRIDGE.md) | جسر Odoo → القرار الاقتصادي (البيانات من المزارع لاحقاً) |
| [`ODOO_EXCLUDED_SAFE.md`](./ODOO_EXCLUDED_SAFE.md) | استثناء حاوية Odoo — التحقّق من سلامة النظام |
| [`ODOO_RAG_CONTAINER_FIX.md`](./ODOO_RAG_CONTAINER_FIX.md) | إصلاح فشل حاويتَي Odoo وRAG |
| [`OPENAPI_EXPORT.md`](./OPENAPI_EXPORT.md) | تصدير OpenAPI — النتيجة |
| [`OPENSOURCE_PATTERNS_REVIEW.md`](./OPENSOURCE_PATTERNS_REVIEW.md) | مراجعة استلهام المشاريع المفتوحة — تحقّق وبناء |
| [`OPERATIONAL_CONTRACTS.md`](./OPERATIONAL_CONTRACTS.md) | OPERATIONAL_CONTRACTS — استجابة لمراجعات Production Readiness |
| [`PARTIAL_CODES_COMPLETED.md`](./PARTIAL_CODES_COMPLETED.md) | إكمال الأكواد الناقصة والجزئيّة (المنطق القابل للإكمال) |
| [`PLANETARY_COMPUTER_FALLBACK.md`](./PLANETARY_COMPUTER_FALLBACK.md) | دمج Microsoft Planetary Computer كمصدر احتياطي |
| [`PRODUCTION_PATH_AUDIT.md`](./PRODUCTION_PATH_AUDIT.md) | تدقيق مسار الإنتاج (Production-Path Audit) |
| [`PROJECT_COMPLETION_AUDIT.md`](./PROJECT_COMPLETION_AUDIT.md) | تدقيق اكتمال المشروع والتنفيذ الفعلي والتوصيل |
| [`PYTHON_COMPATIBILITY.md`](./PYTHON_COMPATIBILITY.md) | توافق إصدارات Python — SAHOOL |
| [`RAG_BUILD_FIX_COMPLETE.md`](./RAG_BUILD_FIX_COMPLETE.md) | إصلاح فشل حاوية RAG — التشخيص الكامل |
| [`RESILIENCE_AND_MUTATION.md`](./RESILIENCE_AND_MUTATION.md) | مرونة تحت الفشل + تأكيد قوّة الاختبارات |
| [`REVIEW_RESPONSE.md`](./REVIEW_RESPONSE.md) | الردّ على المراجعة الهندسيّة — تحقّق وتنفيذ |
| [`RUNTIME_COHESION_WIRING.md`](./RUNTIME_COHESION_WIRING.md) | معالجة Runtime Cohesion: ربط الأنظمة الفرعيّة بحلقة القرار |
| [`SATELLITE_ERP_REVIEW_AND_FIXES.md`](./SATELLITE_ERP_REVIEW_AND_FIXES.md) | الجولة الثامنة — مراجعة وإصلاح: ERPNext + الترحيلات + خطّ الأقمار (قصّ→بلاطات→pixel) |
| [`SMOKE_AND_BUILD.md`](./SMOKE_AND_BUILD.md) | الجولة السابعة — smoke tests + بناء الحاويات |
| [`SOURCE_OF_TRUTH.md`](./SOURCE_OF_TRUTH.md) | المرجع النهائي للبيانات (Source of Truth) — SAHOOL v9 |
| [`STATIC_ANALYSIS_RESPONSE.md`](./STATIC_ANALYSIS_RESPONSE.md) | الردّ على الفحص الفعلي (Ruff/Bandit/Pytest/Coverage) |
| [`STRUCTURED_LOGGING.md`](./STRUCTURED_LOGGING.md) | تسجيل منظّم موحّد (JSON) — النتيجة |
| [`SYSTEM_INDEX.md`](./SYSTEM_INDEX.md) | فهرس منظومة الذكاء المناخي-الزراعي (SAHOOL) |
| [`TATWEEL_BUG_FINDINGS.md`](./TATWEEL_BUG_FINDINGS.md) | اكتشاف حرج من تشغيلك الفعلي: خطأ tatweel في الموجّه |
| [`TEMPORAL_AUTHORITY.md`](./TEMPORAL_AUTHORITY.md) | نموذج السلطة الزمنيّة (Temporal Authority Model) — SAHOOL v9 |
| [`TEST_CAMPAIGN_RESULTS.md`](./TEST_CAMPAIGN_RESULTS.md) | نتائج حملة الاختبار — Build · Operational · E2E · Smoke |
| [`TEST_SUITE_INSTRUCTIONS.md`](./TEST_SUITE_INSTRUCTIONS.md) | دليل تشغيل حزمة الاختبار — لبيئتك الحيّة |
| [`TIMELINE_TENANT_COMPLETION.md`](./TIMELINE_TENANT_COMPLETION.md) | إكمال: سيادة البيانات + الذاكرة الزمنيّة + المقارنة الموسميّة |
| [`WOFOST_REMOTE_SENSING_BEST_PRACTICES.md`](./WOFOST_REMOTE_SENSING_BEST_PRACTICES.md) | أفضل الممارسات: WOFOST + الاستشعار عن بعد (الدقّة العلميّة) |
| [`WORKFLOW_ENGINE_ENHANCEMENTS.md`](./WORKFLOW_ENGINE_ENHANCEMENTS.md) | تطويرات محرّك الـworkflow — تقييم وبناء |
