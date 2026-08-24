# IRRIGATION-DECISION-INTELLIGENCE — المراجعة الموحّدة v1.1-errata2-CORR1

**الحالة:** FOUNDATION — مرجع توجيهي، لا تنفيذ.
**المرجع:** [`IRRIGATION-CONTRACTS-v1.1-errata2.md`](IRRIGATION-CONTRACTS-v1.1-errata2.md)
(المرجع الملزم النثري) + السكيمات المودَعة في
[`services/sahool-platform/schemas/irrigation-contracts/v1.1-errata2/`](../../services/sahool-platform/schemas/irrigation-contracts/v1.1-errata2/)
(التمثيل الآلي القانوني؛ `schema-catalog.json` هو قائمة البصمات الحاكمة) +
Gap Matrix + المقال المعتمد (سلسلة منطق الري الذكي — الجزء الثاني: طبقة صنع القرار).

---

## 1) تصحيح جدول حالة SAHOOL — الصيغة المعتمدة

| القدرة | الحكم المعتمد | الدليل |
|---|---|---|
| Root-zone water balance | IMPLEMENTED-BUT-NOT-LIVE-PROVEN | `services/sahool-platform/api/root_zone_balance.py` (blob `fb1e0b6bc0`)، `api/water_balance.py` (blob `2de3b2596f`) |
| MPC | موجود محكوم، غير مفعّل | `api/lexicographic_irrigation_mpc.py` (blob `67e1a643d5`)، `api/lexicographic_mpc_bridge.py` (blob `4239dada30`) — `execution_allowed=False` بنيويًا، والجسر مُطفأ افتراضيًا (`LEXICOGRAPHIC_MPC_BRIDGE_ENABLED` فاشل-مغلق) |
| Outcome → Learning | جزئي محكوم | `api/learning_feedback.py` (blob `94304f720d`) — `auto_adjust=False` صريح، الترقية بمراجعة بشرية |

يبقى 🔴 فعليّ: Fertigation/EC/pH closed-loop، RL.
يتأكّد ✅: Weather/ET0/GDD (`services/weather-service/canonical_weather_state.py`
blob `4f6f632498` — **تصحيح مسار**: الملفّ في weather-service لا في `api/`)،
و`gdd_lineage_id` حاضر (`weather_runtime.py` + اختباراه).

## 2) القيود الثلاثة الملزمة

1. **ممنوع** تصنيف أي قدرة «غير موجود» إذا كان لها ملف + sha في Gap Matrix.
2. **ثوابت المقال محظورة كثوابت عالمية**:
   - VPD 0.5/3 kPa
   - 200–250 J/cm²
   - ±15–20%
   - نسب EC drainage 1.2–1.5/1.8

   تصبح policy parameters لكل محصول/مرحلة/بيئة، تحت سياسة، لا في الكود.
   (مقيس عند الإيداع: **صفر تسرّب** لهذه الثوابت في السكيمات — كل حدودها
   فيزيائية صرفة: 0/1/14/100.)
3. أي بناء لاحق يمرّ حصرًا عبر:
   - المرجع الملزم + السكيمات المودَعة (v1.1-errata2)
   - الخط السداسي C1–C6
   - القاعدة الذهبية
   - يبدأ من الموجود المثبت.

## 3) خارطة الطريق — من المثبت، لا من الصفر

> **قاعدة نطاق الكود في المراحل 0–2** (توضيح CORR1 — كانت الصياغة الأولى «لا كود
> جديد» وتناقض مضمونها): الممنوع هو **كود قدرة جديد** (محرّكات قرار/جرعة/تعلّم)؛
> **كود التحقّق والربط مسموح** — طبقات التحقق الخارجية والمُهايئات المذكورة أدناه
> هي كود جديد من هذا الصنف المسموح.

**المرحلة 0 — إغلاق الفجوات التصنيفية بلا كود قدرة جديد**
- توثيق التصحيحات أعلاه في المقارنة والمرجع.
- إصدار schema-catalog محدّث إن لزم.

**المرحلة 1 — سد C4/C6 للقدرات الخمس الأولى**
- لا كود قدرة جديد.
- بناء IrrigationDecisionEvidenceChain **كطبقة تحقق خارجية** فوق EvidenceChain
  (كود تحقق — مسموح).
- إنتاج أدلة C6 قدرة-خاصة:
  - C6-LIVE-OBSERVED لـCanonicalWaterState
  - C6-LIVE-DECISION لـMPC
  - C6-LIVE-EXECUTED لـIrrigationExecution

**المرحلة 2 — ربط الموجود بالطلب**
- ربط `root_zone_balance.py` مع IrrigationDemandEngine من خلال
  HydraulicFeasibilityAdapter (كود ربط — مسموح).
- لا إنشاء محرك جديد.

**المرحلة 3 — FertigationState (بناء القدرة الجديد الوحيد)**
- وفق عقد FertigationState v1.1-errata2 + oxygen_proxy.
- نموذج كيمياء مرجعي، ثم C1–C5، ثم C6-LIVE-DECISION.
- لا EC > X → dose.

**المرحلة 4 — Adaptive Model**
- استخدام `learning_feedback.py` الموجود مع `auto_adjust=False`.
- تحويل مخرجات النتائج إلى مرشح معايرة محكوم.

**المرحلة 5 — RL في الظل**
- فقط بعد استقرار 1–4.
- RL → اقتراح تصحيح، لا actuator.

## 4) الملحق A — oxygen_proxy + الصيغ المرجعية

`rootzone.oxygen_proxy` **مدمج في السكيما المودَعة** (حقل اختياري؛ عند وجوده
تكون `value/method/observed_at/freshness_seconds` إلزامية؛ enum الطرائق مغلق؛
لا يُقرأ قياس أكسجين مباشرًا إلا مع `method=oxygen_sensor`). الإسناد بالبصمة
لا بالتضمين (درس نسختَي الملفّ الواحد):

| الملف | sha256 |
|---|---|
| `irrigation-state-snapshot.schema.json` | `ec1a11317242eeae8b68c88be222fbf8669685519773f1837c3805d017489ccd` |
| `evidence-chain.schema.json` | `d84a6fb6956c44956ccbc4efd93de6d4ca8b48439f3bddd2f749c1b77114af16` |
| `fertigation-state.schema.json` | `43ee6ef47ac41fb515ad2ffee8bf3e1b6bec48b43d6fcc4b27afd8eb09d61912` |
| `decision-evidence-envelope.schema.json` | `b50f79a32bd5445ba3b91fd8a7e2de0368b24517d18df32f0858fb6fb16f6b85` |

و`schema-catalog.json` هو القائمة الحاكمة — عند أي تعارض بينه وبين هذا
الجدول، الكتالوج يحكم.

الصيغ المرجعية غير المنفَّذة (ET₀ FAO-56 Penman–Monteith **بالصيغة الصحيحة —
γ لا √** كما وردت خطأً في المقال المصدر؛ موازنة منطقة الجذور بقيدَي θ؛ دالة
جرعة الحمض بالقلوية والبيكربونات وتسلسل
calculate→simulate→gate→inject→measure→reconcile) تبقى مرجعًا تصميميًا في
المرجع الملزم: لا تتحول كودًا ولا تُستعمل في قرار إنتاجي قبل C2 + اختبارات
مرجعية + ربط Decision Service + C6-LIVE-DECISION.

**ملاحظة v1.2 المسبقة (كي لا يُقرأ الغياب سهوًا):** لقطة الحالة الحالية تحمل
`radiation_w_m2` اللحظيّ فقط — حقلا `instantaneous_par` (μmol·m⁻²·s⁻¹)
و`daily_dli` (mol·m⁻²·day⁻¹) بوحدتيهما الصحيحتين يأتيان في تمديد v1.2 عندما
يبدأ مقدّر الطلب الضوئي، لا قبل ذلك.

## 5) أثر هذه الوثيقة على التصنيف

الختم السداسي لا يتغيّر:

```json
{
  "C1_code": false,
  "C2_model": false,
  "C3_decision": false,
  "C4_feedback": false,
  "C5_e2e": false,
  "C6_live": false,
  "classification": "FOUNDATION",
  "evidence": "نص مراجَع فقط، لا كود ولا اختبار ولا تشغيل حي"
}
```

---

**سجلّ CORR1 (ما جرى عند الإيداع):** الفرع حمل إيداع المالك الأصلي (المرجع
الملزم + السكيمات)، وطُبّقت عليه ثلاث رقع مراجعة قبل الدمج الأول — بلا تغيير
على `contract_revision` ولا `schema_id` ولا الختم:

1. **نمط ULID** `^[0-7][0-9A-HJKMNP-TV-Z]{25}$` — النمط الأوسع كان يقبل
   معرّفات مستحيلة (خانة الزمن العليا لا تتجاوز 7). مقيس قبل/بعد.
2. **نمط RFC3339 صريح** في `IsoDateTime` — `format` تعليقي في Draft 2020-12،
   وقياس المراجعة أثبت مرور نص غير زمني حتى مع FormatChecker بلا
   rfc3339-validator.
3. **دمج `oxygen_proxy`** في fertigation (كان الملحق نصًا بلا تمثيل آلي).

نسخة الفرع من EvidenceChain **أقوى** من نسخة المراجعة الأولى: المراحل غير
الجذرية تثبّت `parent_stage_id/parent_digest` غير-null صراحةً — تعزيز
حُفظ كما هو. البطاريّة العدائية أعيدت كاملة على النسخ النهائية: **17/17**
(وقبلها 44 اختبارًا على نسخ المراجعة الأولى)؛ جدول القدرات في §1 مُصدَّق
بصمةً بصمة بـ`git hash-object` (6/6) والأعلام السلوكية الثلاثة مقيسة في الكود.
