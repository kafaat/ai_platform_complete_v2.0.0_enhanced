# تعداد عزل المستأجرين الشامل — كلّ استعلام قاعدة محسوب

مُولَّد آليّاً عبر `scripts/tenant_query_audit.py` (تحليل نصّيّ، لا تشغيل). يصنّف كلّ
استعلام يلمس جدولاً مُستأجَراً (يحوي `tenant_id`) حسب آليّة العزل.

**الإجماليّ:** 276 استعلاماً على جداول مُستأجَرة.

| الفئة | العدد | المعنى |
|---|---|---|
| RLS_CONN | 129 | داخل `tenant_connection` ⇒ RLS مضبوط (آمن بالبناء) |
| EXPLICIT | 12 | يضبط `app.current_tenant` صراحةً (آمن) |
| DELEGATED | 84 | يستقبل `conn` من المُنادي ⇒ سياقه مسؤوليّة المُنادي (آمن بالتفويض) |
| APP_FILTER | 21 | يكتسب اتّصاله لكن يرشّح `WHERE tenant_id=$` (عزل تطبيقيّ) |
| RAW | 30 | يكتسب اتّصاله بلا RLS ولا ترشيح — مُبرَّر فرديّاً (انظر أدناه) |

## RAW المُبرَّرة (كلّ منها مُتحقَّق فرديّاً)

| المفتاح (ملفّ::جدول) | التبرير |
|---|---|
| `services/actuator-service/main.py::automation_rules` | background scene-linkage worker |
| `services/auth/main.py::users` | auth identity-root: global user lookup pre-tenant |
| `services/guardrails-engine/human_in_loop.py::approval_workflows` | centralized expert approval by unguessable workflow_id + privileged role |
| `services/sahool-platform/api/event_replay.py::commands,events` | system replay (cross-tenant outbox) |
| `services/sahool-platform/api/event_replay.py::events` | system replay (cross-tenant outbox) |
| `services/sahool-platform/api/event_replay.py::field_state_snapshots` | system replay via bus conn |
| `services/sahool-platform/api/field_lifecycle.py::field_lifecycle` | scaffold not wired to request path; explicit tenant_id |
| `services/sahool-platform/api/imagery_automation.py::imagery_automation_fields` | background automation worker (fail-closed under sahool_app) |
| `services/soil-service/main.py::soil_readings` | soil ingestion service (sensor-scoped) |

## جدول الأدلّة الكامل (`file:line` لكلّ RAW)

| الموقع | الجداول |
|---|---|
| `services/actuator-service/main.py:405` | automation_rules |
| `services/soil-service/main.py:107` | soil_readings |
| `services/auth/main.py:855` | users |
| `services/auth/main.py:880` | users |
| `services/auth/main.py:898` | users |
| `services/auth/main.py:904` | users |
| `services/auth/main.py:923` | users |
| `services/auth/main.py:934` | users |
| `services/auth/main.py:953` | users |
| `services/auth/main.py:959` | users |
| `services/auth/main.py:971` | users |
| `services/auth/main.py:980` | users |
| `services/auth/main.py:1055` | users |
| `services/auth/main.py:1060` | users |
| `services/auth/main.py:1089` | users |
| `services/auth/main.py:1113` | users |
| `services/auth/main.py:1126` | users |
| `services/guardrails-engine/human_in_loop.py:134` | approval_workflows |
| `services/guardrails-engine/human_in_loop.py:148` | approval_workflows |
| `services/guardrails-engine/human_in_loop.py:203` | approval_workflows |
| `services/guardrails-engine/human_in_loop.py:222` | approval_workflows |
| `services/guardrails-engine/human_in_loop.py:228` | approval_workflows |
| `services/guardrails-engine/human_in_loop.py:243` | approval_workflows |
| `services/sahool-platform/api/event_replay.py:606` | field_state_snapshots |
| `services/sahool-platform/api/event_replay.py:706` | commands,events |
| `services/sahool-platform/api/event_replay.py:710` | events |
| `services/sahool-platform/api/field_lifecycle.py:125` | field_lifecycle |
| `services/sahool-platform/api/field_lifecycle.py:168` | field_lifecycle |
| `services/sahool-platform/api/field_lifecycle.py:356` | field_lifecycle |
| `services/sahool-platform/api/imagery_automation.py:340` | imagery_automation_fields |

> البوّابة: `tests_v9/test_tenant_query_audit.py` — أيّ RAW جديد خارج الـallowlist يُفشِل CI.

---

## تحديث (شهادة الإنتاج HIGH-001): تدقيق الاستعلامات الخام تحت السياقات المُتجاوِزة لـRLS

أبلغت شهادة الإنتاج عن «30 استعلاماً خاماً غير مُصنَّف على جداول المستأجرين» (auth 16،
guardrails/human_in_loop 6، event_replay 3، field_lifecycle 3، actuator 1، soil 1)
مع خطر تسرّب عابر. أداة `tenant_query_audit.py` تُصنّفها أصلاً (275 استعلاماً: 129
RLS_CONN، 84 DELEGATED، 21 APP_FILTER، 10 EXPLICIT، 31 RAW مُبرَّر). لكنّ هذه الجولة
أدخلت **سياقَين يتجاوزان RLS قصداً**، فأُعيد تدقيق المواقع تحتهما:

| السياق | المسار | الجداول الملموسة | الحكم |
|---|---|---|---|
| `app.current_role='admin'` (مسبح auth) | `services/auth/main.py` (16) | `users`, `audit_log` فقط | **آمن** — نطاق الهويّة؛ auth يقرأ بالبريد قبل معرفة المستأجِر (تصميم) |
| `sahool_jobs` (BYPASSRLS) | `api/event_bus.py` (المرسِل) | `event_outbox`, `events` فقط | **آمن** — نطاق المرسِل |
| `sahool_jobs` (BYPASSRLS) | `api/weather_automation.py` (المجدوِل) | `weather_automation_cache/locations` فقط | **آمن** — نطاق المجدوِل |
| `sahool_app` (NOBYPASSRLS) | guardrails/event_replay/field_lifecycle/actuator/soil | جداول مستأجَرة | **آمن بـfail-closed** — استعلام بلا سياق ⇒ صفر صفوف (لا يُسرِّب) |

**الخلاصة:** لا تسرّب عابر. السياقان المتجاوِزان محصوران بجداول نطاقهما (مُتحقَّق آليّاً)،
وبقيّة المواقع محميّة بـfail-closed RLS تحت الدور المقيّد.

**حارس جديد:** `tests_v9/test_elevated_context_scope.py` يثبت أنّ auth (سياق admin) لا
يلمس إلّا جداول الهويّة، وأنّ مساري `sahool_jobs` محصوران بنطاقهما — فأيّ استعلام مستقبليّ
يُوسّع نطاق سياق متجاوِز (تسرّب محتمل) يُفشِل CI.
