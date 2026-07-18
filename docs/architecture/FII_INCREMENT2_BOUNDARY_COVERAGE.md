# FII Increment 2 — Chemical Lineage Audit Hardening — Boundary Coverage

**النطاق:** تقسية التدقيق فقط. **يبقى audit-only** (`FII_CHEMICAL_LINEAGE_MODE` افتراضه `audit`؛ لا enforce).
**لا** Workspace/SoR/schema/جدول جديد. يُطبَّق **فوق** `FII_SAFETY_CORRECTED_DELTA`.

## ما تغيّر
- `services/sahool-platform/core/chemical_lineage.py` — أُعيد تصميمه: تحقّق خادميّ حقيقيّ للتشخيص عبر **resolver قابل للحقن**، رموز مخالفة ثابتة، fail-loud.
- `services/sahool-platform/api/routers/pest_escalation.py` — يمرّر `tenant_id` من التوكن (لا من الجسم).
- اختبارات: `test_fii_chemical_lineage_hardened.py` (مصفوفة كاملة) + `test_fii_chemical_lineage.py` (مُحدَّث للعقد الجديد). **38 اختباراً أخضر.**

## التحقّق الخادميّ (عند توفّر الخدمة المالكة)
عند حدّ `SUBMIT` فأقوى، يُستدعى المالك (افتراضاً `HttpDiagnosisResolver` → `DIAGNOSIS_SERVICE_URL/internal/diagnoses/{ref}` بتوكن خدمة) ويُتحقَّق:
- التشخيص موجود · غير منتهٍ (`valid_until`) · غير مُستبدَل (`superseded_by`) · `review_state` مسموح · `insufficient_evidence=false` · `evidence_level ≥ العتبة` · تطابق `tenant_id`/`field_id`/`season_id` مع سياق المصادقة (لا الجسم).
- **fail-loud:** أيّ تعذّر (URL غير مضبوط · timeout · 5xx · 401/403) ⇒ `VALIDATION_UNAVAILABLE` مُسجَّل — **ليس نجاحاً صامتاً أبداً**. في audit يُسمَح ويُسجَّل؛ في enforce (لاحقاً) يحجب.

## رموز المخالفة الثابتة (كلّها مُختبَرة)
`MISSING_FIELD_ID` · `MISSING_SEASON_ID` · `MISSING_DIAGNOSIS_REF` · `MISSING_EVIDENCE_REF` · `EVIDENCE_DIGEST_MISSING` · `DIAGNOSIS_NOT_FOUND` · `DIAGNOSIS_EXPIRED` · `DIAGNOSIS_SUPERSEDED` · `REVIEW_STATE_NOT_ALLOWED` · `DIAGNOSIS_INSUFFICIENT_EVIDENCE` · `EVIDENCE_INSUFFICIENT` · `TENANT_MISMATCH` · `FIELD_MISMATCH` · `SEASON_MISMATCH` · `MISSING_HUMAN_APPROVAL` · `VALIDATION_UNAVAILABLE`.

## تغطية الحدود السبعة (+ الفرعيّة)

| الحدّ | الخدمة | الحالة | ملاحظة |
|---|---|---|---|
| Recommendation draft/submission | sahool-platform (`pest_escalation`) | **موصول** (DRAFT/EXECUTE) | يمرّر tenant الآن؛ التدقيق يعمل audit |
| Recommendation submission | sahool-platform (`recommendations.py`) | **جاهز غير موصول** | الوحدة مستوردة محليّاً؛ يُضاف استدعاء عند `SUBMIT` |
| Prescription (chemical) export | sahool-platform (`prescriptions.py`) | **جاهز غير موصول** | يُوصَل فقط لأنواع منتجات كيميائيّة |
| Work-order creation | sahool-platform | **جاهز غير موصول** | حدّ `WORK_ORDER` مُعرَّف |
| Decision approval | **decision-service** | **مؤجَّل** | خدمة منفصلة — تحتاج ترقية الوحدة لمشتركة |
| Dispatch authorization | **decision-service** | **مؤجَّل** | نفسه |
| Execution request | **decision-service** | **مؤجَّل** | نفسه (والحدّ `EXECUTE` مُغطّى في platform) |
| Inventory reservation | **odoo-bridge** | **مؤجَّل** | خدمة منفصلة |
| Actuator/machine dispatch | **actuator-service** | **مؤجَّل** | خدمة منفصلة |

## الخطوة المعماريّة لإكمال الحدود عبر-الخدمات
`chemical_lineage.py` صُمِّم **مكتفياً ذاتيّاً** (stdlib فقط؛ httpx كسول). لإكمال حدود decision/actuator/odoo:
1. رقِّ الوحدة إلى حزمة مشتركة (`shared/governance/chemical_lineage.py`) قابلة للاستيراد من كلّ خدمة.
2. اجعل `sahool-platform/core/chemical_lineage.py` يعيد التصدير منها (بلا كسر).
3. وصِّل كلّ حدّ في خدمته باستدعاء `audit_chemical_lineage(..., boundary=<الحدّ>)`، مع resolver الخدمة المالكة.
4. أضِف endpoint تحقّق للتشخيص لدى المالك (vegetation-analysis-service) حتى يصبح التحقّق حيّاً بدل `VALIDATION_UNAVAILABLE`.

## شرط الانتقال إلى enforce (غير الآن)
قبل `FII_CHEMICAL_LINEAGE_MODE=enforce`: (أ) endpoint تحقّق التشخيص حيّ · (ب) كلّ الحدود موصولة · (ج) نافذة audit تُظهر `VALIDATION_UNAVAILABLE`/المخالفات ضمن عتبة منخفضة · (د) لا false-rejection غير متوقّع · (هـ) التراجع إلى audit مجرَّب.

## الحكم
النسخة الحاليّة: **صالحة كتقسية audit لـIncrement 2** — لا تُفعّل enforce. الوحدة والاختبارات جاهزة؛ الحدود عبر-الخدمات تحتاج ترقية الوحدة لمشتركة (خطوة مستقلّة تالية).
