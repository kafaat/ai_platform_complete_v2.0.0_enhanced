# Coverage Ratchet — `services/` unit tests (SEC-5)

بوّابة تغطية غير-كاسرة (non-breaking ratchet) لوظيفة CI **Unit Tests**. الأرضيّة
تُضبط أسفل المقيس الفعليّ بهامش صغير، وتُرفع تدريجيّاً — لا تنزل أبداً.

## المصدر (source of truth)

- الأمر (نفس CI): `pytest -m unit --cov=services --cov-fail-under=<floor> -q`
- الأرضيّة مضبوطة في `.github/workflows/ci.yml` (خطوة *Coverage gate (fail-under)*).
- **مهمّ:** وظيفة CI *Unit Tests* تعمل في **بيئة دنيا** — تُثبّت `tests_v9/requirements-test.txt`
  فقط، **بلا fastapi/خدمات**. لذا الوحدات التي تستورد fastapi لا تُجمَع (تُتخطّى)،
  والمقيس يختلف عن تشغيل محلّيّ بتبعيّات كاملة. القياسات أدناه من البيئة الدنيا
  (المُلزِمة للبوّابة).

## القياس الحاليّ (2026-07)

| البيئة | المقيس | الملاحظة |
| --- | --- | --- |
| **الدنيا (مطابِقة لـCI، بلا fastapi)** | **44.55%** | المُلزِم للبوّابة — 9201/20655 عبارة |
| المحلّيّة الكاملة (مع fastapi) | 48.10% | مرجعيّ فقط — 19901/41373 عبارة |

- **الأرضيّة الحاليّة: `--cov-fail-under=40`** (هامش ~4.5 نقطة دون 44.55%). تُرك
  الهامش كي لا يُحمِّر انخفاض صغير البناءَ.
- نتيجة التحقّق المحلّيّ: `Required test coverage of 40% reached. Total coverage: 44.55%` (exit 0).

> ملاحظة: وظيفة CI منفصلة **Platform Unit Tests** تفرض أرضيّة أعلى (60٪) عبر
> `services/sahool-platform/.coveragerc` على حزمتَي `api/`+`core/`. هذه الوثيقة
> وهذه الأرضيّة (40٪) تخصّان بوّابة `--cov=services` الأوسع فقط ولا تمسّان بوّابة 60٪.

## التفصيل حسب النطاق الحرج (بيئة CI الدنيا)

أبرز الوحدات منطقيّة-صرفة في كلّ نطاق (النسبة = تغطية الوحدة):

- **auth / RLS / authz:**
  `services/sahool-platform/core/authorization.py` 76٪ ·
  `services/auth/mfa_crypto.py` 97٪ · `services/auth/otp.py` 100٪ ·
  `services/auth/main.py` 3٪ و`routers/*` 0٪ (تطبيق fastapi — يُتخطّى في البيئة الدنيا).
- **field-state:**
  `services/sahool-platform/api/field_state_projection.py` 44٪ ·
  `services/sahool-platform/api/field_state_gateway.py` 29٪.
- **raster:**
  `change_detection.py` 94٪ · `quality_metrics.py` 97٪ · `sar_rvi.py` 94٪ ·
  `fvc.py` 89٪ · `cdse_client.py` 66٪ · `job_store.py` 51٪ · `band_math.py` 44٪ ·
  `db_persist.py` 17٪ (كلّها تحت `services/raster-service/`).
- **orchestration:**
  `services/sahool-platform/core/internal_orchestrator.py` 48٪ ·
  `services/supervisor-agent/tool_contracts.py` 44٪ ·
  `services/supervisor-agent/main.py` + `routers/*` + `skills/*` 0٪ (fastapi — يُتخطّى).

الفجوات الكبرى (0٪) هي غالباً تطبيقات fastapi وطبقات persistence غير المُجمَّعة
في البيئة الدنيا — رفعها يتطلّب إمّا اختبارات منطق أنقى أو ترقية بيئة البوّابة.

## الخطّة المرحليّة (staged targets)

| المرحلة | الأرضيّة | الشرط للانتقال |
| --- | --- | --- |
| ✅ 2026-07 | **40** | المقيس الدنيا 44.55٪ (هذه المهمّة). |
| التالية | 45 | حين يستقرّ المقيس الدنيا ≥ ~48٪ (أضِف تغطية منطق field-state/orchestration). |
| ثمّ | 50 | حين ≥ ~53٪. |
| الهدف | 55 | حين ≥ ~58٪ (يستلزم غالباً تجميع مسارات fastapi أو نقل منطقها لوحدات نقيّة). |

**قاعدة الرفع:** بعد أيّ عمل يرفع المقيس الدنيا، اضبط `--cov-fail-under` على
`floor(المقيس) - ~4` في `ci.yml`، وحدّث جدول «القياس الحاليّ» أعلاه. لا تُنزِل
الأرضيّة أبداً. لا تضبطها فوق المقيس الفعليّ للبيئة الدنيا (يُحمِّر CI).
