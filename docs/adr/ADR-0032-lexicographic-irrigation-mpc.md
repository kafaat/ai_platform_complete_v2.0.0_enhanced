# ADR-0032 — متحكّم الريّ التنبّؤيّ الهرميّ المعجميّ (Lexicographic MPC)

**الحالة:** مقبول — المرحلتان 0 و1 + **P1.1 تصلّب النَّسَب/العقد** + **P1.1b وصل الجسر
والنقطة** مُنفَّذة (نواة الحلّال + العقد؛ نموذج Ky؛ نَسَب مُحكَم؛ جسر محكوم + نقطة إنتاجيّة).
انتشار النَّسَب الكامل عبر PostgreSQL/السلسلة يُشهَّد على staging (محاكاة حتى ذلك، نفس وضع
`water_decision_bridge`). المراحل 2–4 (طاقة/آبار · أفق ساعيّ · واجهة MPC مخصّصة) مُخطَّطة.

**تحديث P1.1 (تصلّب النَّسَب والعقد — استجابةً لتدقيق جنائيّ):** أُصلِح **خلل P0 مُثبَت**: كان
`candidate_lineage_id` يتصادم عبر قرارات مختلفة (37.5/5/2 مم بميزانيّة/سقف مختلفَين ⇒ نفس
النَّسَب) لأنّ البصمة أغفلت القيود واقتُصَّت لـ16-hex. الآن: **`content_digest` كامل sha256
(64-hex)** على canonical-JSON لكلّ الحقائق (المدخلات + القيود + الإصدار + السياسة الفائزة +
الخطّة الناتجة)؛ **فصل** `idempotency_key` (فتحة الطلب المنطقيّة: نفس الحقل/الموسم/الأفق) عن
`content_digest` (المحتوى) عن `candidate_lineage_id` (عرض قصير). حقول حوكمة: `tenant_id`،
`season_id`، `solver_version`، `execution_allowed=False`، `constraint_trace`،
`modeled_capabilities`. **صدق حدّ الإنتاج:** نطاق `forecast_horizon` صراحةً (لا موسميّ)؛ Ky
العامّ (`generic_stage`) **لا يُثبِت** حدّ إنتاج؛ التأكيد بـ**الحدّ الأدنى للثقة** (نشر عدم
يقين Ky: أسوأ حالة Ky+uncertainty). فصل `first_action_depth_mm` عن `horizon_total_irrigation_mm`،
وإعادة تسمية `predicted_water_m3_per_ha`→`recommended_gross_water_m3_per_ha`. توحيد التهجئة
`not_modeled`. فشل-مُغلَق على مدخلات NaN/Inf/خارج المدى (استنزاف<0 أو >TAW، أفق غير منتهٍ،
هدف حدّ إنتاج خارج [0,1]). التنفيذ/MQTT/التفويض لم يُمَسّ. **32 اختبار وحدة** (شمل: النَّسَب
يختلف بالقيود · ثبات فتحة idempotency · عزل المستأجر/الموسم · 64-hex · فشل-مُغلَق للمدخلات ·
Ky العامّ لا يُثبِت). **المتبقّي P1.1b:** Route يقرأ water_ledger + وصل الحلّال إلى
water_decision_bridge (مرشّح `lexicographic_irrigation`) + استمرار PG + انتشار النَّسَب عبر
execution→outcome→learning — يحتاج سلسلة decision-service وPG حقيقيّ.

**تحديث P1.1c-a (تصلّب fail-closed + فصل المحاكاة/العمليّ — استجابةً لتدقيق جنائيّ):** التدقيق
أثبت **فجوة P0 في كودي**: الراوتر كان يضع `Dr=0` عند غياب صفّ الدفتر — وهو **اختلاق** (يعني
رطوبة ممتلئة، فقد يُصدِر `hold` بينما الحقل جافّ). أُصلِح: غياب Dr المرجعيّ ⇒ **`blocked`**
(`reason=no_ground_truth_depletion`، لا قرار قابل للإرسال). وأُضيف **فصل صريح**: تمرير
`initial_depletion_mm` صراحةً ⇒ **محاكاة** (`mode=simulation`) لا تُصدِر مرشّحاً محكوماً
(`submit` ⇒ `rejected_simulation`)؛ غيابه + صفّ دفتر ⇒ **عمليّ** (`mode=operational`) قابل
للإصدار. وحدود صارمة على العقد (Pydantic `ge/gt/le`) ترفض ET0/Kc/TAW/السعر/الميزانية السالبة
و`raw_fraction`/`yield_floor_ratio` خارج المدى بـ422. **متبقٍّ P1.1c (مُعلَن صراحةً):** مصدرة
كلّ الحقائق (TAW/RAW/المحصول/المرحلة/الطقس) من SoR خادميّاً (لا من العميل) + مساران منفصلان
`/simulate` و`/recommendation` + بصمات لقطات (دفتر ماء/طقس) + شهادة PostgreSQL للسلسلة
حتى outcome. لذا `LEXICOGRAPHIC_MPC_BRIDGE_ENABLED=true` يبقى **غير جاهز للإنتاج** حتى P1.1c الكامل.

**تحديث P1.1b (وصل الجسر + النقطة الإنتاجيّة):** أُضيف **أوّل مستهلك إنتاجيّ** للحلّال:
- **جسر محكوم** `api/lexicographic_mpc_bridge.py`: `build_mpc_candidate` يبني مرشّح قرار من
  النوع **`irrigation_mpc`** ينشر النَّسَب الكامل صراحةً على مستوى القمّة
  (`content_digest` 64-hex + `idempotency_key` + `solver_version` + `candidate_lineage_id`)
  وداخل `decision_value` (فينتقل عبر review→execution→outcome→learning). `emit_mpc_candidate`
  (async) يُصدِر المرشّح إلى مركز القرار عبر `record_decision` — **توصية-فقط بنيويّاً**
  (`execution_allowed=False`، `requires_human_review=True`، لا مسار authorize/execution/MQTT)،
  **مُطفأ افتراضيّاً** (`LEXICOGRAPHIC_MPC_BRIDGE_ENABLED`)، **فاشل-مُغلَق** على
  `EMERGENCY_FAIL_CLOSED`. نفس وضع `water_decision_bridge`.
- **نقطة إنتاجيّة** `POST /api/v1/irrigation/mpc/plan` (+ `GET …/capabilities`): تقرأ
  **حقيقة الخادم** (أحدث استنزاف من `water_ledger`) عند غياب `initial_depletion_mm`؛ بلا صفّ ⇒
  استنزاف 0 + `data_degraded` مُعلَن (**لا اختلاق**). `tenant_id` من المستخدم المُصادَق لا من
  الجسم (عزل المستأجِر). `submit=true` (خلف عَلَم الجسر) يُصدِر المرشّح المحكوم فقط.
- **حارس CI** `scripts/ci/mpc_lineage_propagation_guard.py`: يؤكّد المرشّح يحمل مفاتيح النَّسَب
  والنوع `irrigation_mpc`، وأنّ الجسر يبقى توصية-فقط (لا استدعاء تنفيذ). **11 اختبار وحدة** للجسر
  والنقطة (شكل المرشّح · انتشار النَّسَب · قرارات مختلفة ⇒ معرّفات مختلفة · مُطفأ افتراضيّاً ·
  فاشل-مُغلَق · مركز قرار مموّه · قراءة الدفتر/التدهور · عزل المستأجِر). النقطتان مُعفَيتان بصدق في
  عقد تغطية الواجهة (توصية تظهر عبر Decision/Approvals Console القائمة؛ شاشة MPC مخصّصة دَين
  مُتتبَّع `MPC-P2-UI`). **⚠ محاكاة حتى staging:** انتشار النَّسَب الكامل عبر PostgreSQL يُشهَّد
  على بيئة حيّة.

**تحديث المرحلة 1 (نموذج Ky الكنسيّ):** J3 لم يعد وكيل إجهاد — صار
`Ya/Ym = 1 − Ky·(1 − ETa/ETm)` بمعاملات Ky من `core/engines/ky_registry.py` (FAO-33،
Table 24، حسب المحصول والمرحلة، كلّ مدخل يحمل `ky_source`/`version`/`effective_from`/
`uncertainty` — لا اختلاق). الترتيب: Ky خاصّ بالمحصول ⇒ صفّ عامّ حسب المرحلة (`generic_stage`
مُعلَّم، ثقة أدنى) ⇒ لا شيء. غياب Ky/المرحلة أو ETm غير صالح ⇒ `insufficient_data` (لا استبدال
صامت؛ J3 محايد في الترتيب). `yield_floor_preserved=true` فقط ببيانات كاملة (ETa/ETm صالحان +
مرحلة معروفة + Ky متاح + داخل حدود النموذج + هدف حدّ إنتاج مُحقَّق). ETa/ETm من Ks اليوميّ
(FAO-56). J3 مربوط بـ`objective_trace` + `candidate_lineage_id`. **عزل اقتصاديّ صارم:** لا
يُشتَقّ إيراد/هامش من Ky — حارس CI `scripts/ci/ky_no_economic_coupling_guard.py` يمنع ذلك حتى
وصول نموذج اقتصاديّ صريح. لم يُمَسّ التنفيذ/MQTT/التفويض.

## السياق

ندرة المياه والطاقة وخطر الإجهاد في اليمن **لا يمكن اختزالها في دالّة تكلفة واحدة
موزونة**: خطأ في تجربة قد يقتل محصولاً، ولا يجوز أن يقايض المُحسِّن حماية المحصول بوفر
طاقة. لذا نتبنّى **ترتيب أولويّات صريحاً غير قابل للمقايضة الماليّة** بدل مجموع موزون.

قبل هذا القرار كان لدى المنصّة `api/irrigation_mpc.plan_irrigation` — مُخطِّط جشِع بأفق
متحرّك يقيّم **سياسة واحدة** فوق فيزياء FAO-56، ويصف نفسه صراحةً أنّه ليس مُحسِّناً
عامّاً (QP/LP). البنية التحتيّة للقرار المحكوم موجودة كاملةً: `water_ledger` (Dr يوميّ)،
`canonical_water_stress` (AWF/الفئات)، `core/engines/fao56.py` (ETc مزدوج، TAW، Zr،
Ks الملوحة، الغسيل)، وسلسلة candidate → review → execution → verify → outcome → learning
عبر `decision-service` (SoR محكوم) و`actuator-service` (MQTT + kill-switch).

**الغائب كلّيّاً كبيانات:** طبقة الطاقة/الآبار/الشمسيّة (منحنى مضخّة، q_max بئر، توقّع
قدرة PV، حدود شبكة/مولّد، حدود دورات المضخّة، تسعير TOU). المخطّط مرسوم في
`docs/history/COMPETITIVE_ANALYSIS.md` فقط.

## القرار

**سلّم الأولويّات (غير قابل للمقايضة عبر المستويات، بهامش ε مضبوط):**

1. **J1 — حماية المحصول:** `Σ max(0, Dr−RAW)² + λ_s·(أيّام إجهاد في مرحلة حرجة)`.
   المرحلة الحرجة = حسّاسيّة Ky (FAO-33) ≥ 0.85 (الإزهار/امتلاء الحبّ).
2. **J2 — تقليل الماء (والطاقة):** ماء مُطبَّق + رشح عميق. **الطاقة `not_modelled`** في
   المرحلة 0 (لا بيانات) — تُعلَن صراحةً ولا تُلفَّق.
3. **J3 — حدّ إنتاج أدنى:** المرحلة 0 وكيلٌ قائم على الإجهاد الحرج
   (`stress_proxy_pending_ky`)؛ يُستبدَل بمعادلة Ky الكنسيّة
   `Ya/Ym = 1 − Ky·(1 − ETa/ETm)` في المرحلة 1.
4. **J4 — الهامش الاقتصاديّ:** وكيل تكلفة ماء ($/m³). الإيراد والطاقة `not_modelled`.

**الاختيار المعجميّ (ε-constrained):** نُثبّت أفضل J1؛ ضمن هامش `EPS_J1` نختار أفضل J2؛
ضمن `EPS_J2` أفضل J3؛ ضمن `EPS_J3` أدنى J4 (كسر تعادل حتميّ بترتيب المرشّحين). فضاء
القرار في المرحلة 0 = السياسات الخمس القائمة، كلٌّ يُحاكى أماماً عبر `plan_irrigation`.

**آلة الحالات التشغيليّة:** `NORMAL_OPTIMIZATION` · `CROP_PROTECTION` (مرحلة حرجة +
اقتراب/تجاوز RAW) · `WATER_SCARCITY` (نفاد ميزانيّة مع إجهاد) · `ENERGY_CONSTRAINED`
(غير قابلة للوصول في المرحلة 0 — لا طاقة) · `DATA_DEGRADED` (ثقة منخفضة ⇒ ثقة مخفوضة) ·
`EMERGENCY_FAIL_CLOSED` (مدخلات حرجة مفقودة ⇒ لا أمر، موافقة بشريّة، ثقة 0).

**الحوكمة والاستقلاليّة المتدرّجة:** المرحلة 0 **توصية-فقط** (`approval_required=True`
دائماً). الحلّال **لا يرسل أمراً للمضخّة** — يُصدِر مرشّح قرار محكوماً يمرّ بمركز القرار
(review → approve → execute → verify). الاستقلاليّة تُرفَع لاحقاً على مراحل خلف أعلام.

**الصدق:** كلّ حقل غير مُنمذَج يُعلَن في `not_modelled` (`predicted_energy_kwh`،
`source_well_id`، `start_at`، `duration_minutes`، `zone_id`، إيراد الهامش). المقابض
والأوزان `calibrated=False` — تحتاج معايرة يمنيّة.

## العواقب

- **إيجابيّة:** حماية المحصول مضمونة بنيويّاً (J1 يفوز دائماً)، لا مقايضة ماليّة تُضرّ
  المحصول، قرار قابل للتفسير برموز أسباب معدودة، يُعاد استخدام فيزياء FAO-56 والسلسلة
  المحكومة القائمة، ولا تلفيق لبيانات غائبة.
- **قيود المرحلة 0:** أفق يوميّ لا ساعيّ (لا نوافذ رياح/شمس داخل اليوم)؛ J3 وكيل حتى Ky؛
  لا قيد طاقة/بئر؛ فضاء القرار = 5 سياسات لا شبكة قرار مستمرّة.
- **المراحل التالية:** م1 نموذج Ky الكنسيّ؛ م2 طبقة الطاقة/الآبار (هجرات wells/pumps +
  توقّع PV) تفتح J2/ENERGY_CONSTRAINED؛ م3 أفق ساعيّ؛ م4 واجهة + كاتب `irrigation_runs`
  من مسار التنفيذ + إغلاق الحلقة.

## المراجع

- التنفيذ: `services/sahool-platform/api/lexicographic_irrigation_mpc.py`
- الجسر المحكوم: `services/sahool-platform/api/lexicographic_mpc_bridge.py` (P1.1b)
- النقطة الإنتاجيّة: `services/sahool-platform/api/routers/irrigation_mpc.py` (P1.1b)
- حارس النَّسَب: `scripts/ci/mpc_lineage_propagation_guard.py` · حارس العزل الاقتصاديّ:
  `scripts/ci/ky_no_economic_coupling_guard.py`
- الاختبار: `tests_v9/test_lexicographic_irrigation_mpc.py` (نواة الحلّال) +
  `tests_v9/test_lexicographic_mpc_bridge.py` (الجسر + النقطة)، `-m unit`
- يعمّم: `api/irrigation_mpc.py` · يعيد استخدام: `api/irrigation_policy.py` ·
  `core/engines/supplemental_irrigation.py` (Ky) · `api/canonical_water_stress.py` ·
  `api/soil_water.py`
