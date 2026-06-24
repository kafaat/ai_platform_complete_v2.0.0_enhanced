# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

---

## 2026-06-24 (ظ) — Water Use Efficiency: Outcome KPI لكفاءة استخدام المياه

**رأس `main`:** `486de6a` (#476 مُدمج). فرع `claude/water-efficiency-kpi`. **تحسين** يخدم مؤشّر «خفض المياه»
المقترح. **فجوة حقيقيّة مُتحقَّقة:** `water_ledger` (v98) يحمل الحقول اليوميّة لكن لا تجميع/كفاءة؛ الـWUE
الوحيد الموجود يتطلّب غلّة (لا حلقة غلّة-أرضيّة ⇒ لا يُقاس بصدق).
- **`api/water_efficiency.py`** (`compute_water_efficiency(entries)` نقيّة): كفاءة من **التوازن المائيّ** —
  `etc_total` (الطلب) مقابل `supplied = ريّ + مطر فعّال (min(rain,etc))`. يُخرِج `water_use_efficiency`
  (نسبة المُورَّد المُستغَلّ، ≤1؛ أدنى = إفراط/هدر) · `demand_met_pct` (تغطية الطلب) · `over_application_mm`
  (الماء الزائد — ذراع الخفض). أوزان/تبسيط **مُعلَنة** (`calibrated=False`).
- **بوّابات الصدق:** لا طلب ⇒ `needs_data`؛ لا ريّ مُسجَّل ⇒ `needs_irrigation_data` («سجّل الريّ») — لا
  رقم مُضلِّل من المطر وحده. **الغلّة خارج النطاق صراحةً** (لا حلقة). مدخل فاسد ⇒ كتلة needs_data (fail-safe).
- **نقطة `GET /api/v1/fields/{id}/water-efficiency?from=&to=`** في `routers/water_ledger.py` — تُعيد استخدام
  نمط `list_water_ledger` (auth/tenant/RLS/503/422 + قراءة الدفتر)؛ قراءة فقط، **لا هجرة، لا تغيير قرار**.

**صدق:** توازن مائيّ لا غلّة؛ يُعلِن النقص؛ يُعيد استخدام الدفتر. تحقّق: ٧ اختبارات
(`test_water_efficiency.py`: إفراط/تطابق/نقص · المطر مقصوص · needs_irrigation_data · needs_data · fail-safe)
· tests_v9 1865 (فشل MFA الـ5 سابقٌ) · platform 1104 · حارس تفكيك الراوترات أخضر · **مسح ruff كامل**.

---

## 2026-06-24 (ض) — Field Data Readiness Index: درجة جاهزيّة بيانات الحقل المُفسَّرة

**رأس `main`:** `d156146` (#475 مُدمج). فرع `claude/field-readiness-index`. **تحسين** (لا إغلاق فجوة)
مستوحى من تحوّل الزراعة العالميّة نحو «نتائج + ثقة قابلة للقياس»، بنسخة يمنيّة (smallholder/offline/
explainable-first): درجة **واحدة مُفسَّرة** لكلّ حقل «كم نثق بذكاء هذا الحقل الآن؟» + إرشاد عمليّ صادق
(«صورة أحدث»/«تحليل تربة») — تجعل صدق المنصّة (النقص المُعلَن) **مرئيّاً وقابلاً للفعل**.
- **`api/field_readiness.py`** (`compute_field_readiness(state)` نقيّة): تُجمّع إشارات **قائمة** بلا حساب
  جديد ولا اختلاق — النضارة (أعمار NDVI/تربة/طقس) · الثقة (`confidence_level`) · المعايرة
  (`calibration_status` من C5؛ insufficient=0.5 نقص مُعلَن لا فشل) · تغطية الكتل الكنسيّة. أوزان **مُعلَنة
  لا معايَرة** (`calibrated=False`)؛ بُعد غائب ⇒ يُستبعَد + إعادة تسوية (لا عقاب على ما لا يُقاس)؛ مدخل فاسد
  ⇒ None.
- **الإسقاط:** `recompute_field_state` يُسقط `state["readiness"]` أخيراً (best-effort، **معلوماتيّ لا يمسّ
  validity/execution_mode**، لا هجرة — كتلة محسوبة على القراءة). `diagnose` يقرؤها.
- **لا تكرار:** `data_readiness.py` القائم للـonboarding (ما البيانات اللازمة؟)؛ هذا للجاهزيّة التشغيليّة
  الحيّة (كم نثق الآن؟) — مكمِّل.

**صدق:** تجميع صرف، لا تغيير قرار، أوزان مُعلَنة. تحقّق: ٦ اختبارات قارئ (`test_field_readiness.py`:
excellent/fair+إرشاد · إعادة تسوية · insufficient · معايرة 0.5 · None) + ١ إسقاط · tests_v9 1858 (فشل MFA
الـ5 سابقٌ) · platform 1104 · حارس التفكيك أخضر · **مسح ruff كامل**.

---

## 2026-06-23 (ذ) — مراجعة حالة Bundle C R&D (إغلاق توثيقيّ لا برمجيّ)

**رأس `main`:** `2e08f65` (#474 مُدمج). فرع `claude/bundle-c-rd-status`. آخر عنصر في سحب الإطار
«implemented-but-off-by-default». **القرار الصادق (توافق المستخدم↔الوكيل 2026-06-23):** Bundle C **مسار
R&D**، وأجزاء كبيرة منه **ليست فجوات تنفيذيّة** — فلا تُختلَق أعلام/إغلاقات مصطنعة لما لا وجود له، ولا يُعاد
حراسة المحروس. إغلاقه **توثيقيّ** بإعلان حالة كلّ عنصر:
- **SAM2** → closed (gated, env-unverified) — محروس بـprofile=gpu، 503 صادق بلا GPU.
- **Field Embeddings / RAG** → closed (implemented-as-optional-services) — qdrant-seed/local-ai-rag خدمات
  اختياريّة بالنشر؛ **مُتحقَّق:** RAG لا يدخل مسار قرار إنتاجيّ بلا حراسة (`conservative_rag` خارج مسار
  القرار؛ `local-ai-rag` إثراء شرح opt-in في `decision_explainer`) ⇒ **لا حاجة `FEATURE_CONSERVATIVE_RAG`**.
- **Multi-engine Ensemble** → open (concept-only) — `fusion.py` للمؤشّرات الطيفيّة شيء مختلف، ليس تنفيذاً.
- **نماذج أساس (Prithvi/DINOv3)** → not started (لا كود).
- **ISOXML** → deferred by design (#456، Shapefile كافٍ — مُلاءمة اليمن).

**المخرَج (لا كود):** صفحة جديدة [`decisions/bundle-c-status.md`](decisions/bundle-c-status.md) + تحديث
`gaps/registry.md` (صفوف C-Embeddings/RAG · C-Ensemble · C-Foundation · C-ISOXML + SAM2) + `strategy.md`.
**يكتمل بذلك سحب الإطار:** 4 إغلاقات كود (#471 ETc-dual · #472 C5 · #473 H2 · #474 C4/M1) + 1 إغلاق حالة
(Bundle C). تحقّق: doc-only (لا اختبارات/كود) — لا تغيير سلوك.

---

## 2026-06-23 (د) — إغلاق C4/M1: علم push الموبايل (default off) + سجلّ احتياطيّ دائم

**رأس `main`:** `c9c70a7` (#473 مُدمج). فرع `claude/c4-m1-mobile-push-flag`. الفجوة C4/M1 (push موبايل +
WebSocket). **حقيقة صدق:** الـpush مُنفَّذ أصلاً ومحروس بقدرة FCM (`fcm_push_active()` على `FCM_SERVER_KEY`،
no-op صادق خامل)؛ و`create_notification_record` (جدول `notification_delivery` v83) منفَّذ. الفجوة الفعليّة
الوحيدة: عند رغبة المستخدم بالـpush وتعطّل FCM ⇒ الإشعار **يُسقَط بلا سجلّ**. الإغلاق (إطار
implemented-but-off-by-default، في وكيل الإشعارات `agents/notification/agent.py`):
- **علم `FEATURE_MOBILE_PUSH` (default off)** + `mobile_push_enabled()` (opt-in صريح فوق قدرة FCM —
  التفعيل يتطلّب العلم **و** `FCM_SERVER_KEY`).
- **`push_decision()` نقيّة:** `send` (العلم on ∧ FCM نشط) · `record_only` (رغبة لكن العلم off أو FCM خامل)
  · `skip` (لا رغبة).
- **`_record_push_fallback()`:** عند `record_only` يُدِيم إيصال `notification_delivery`
  (`channel='push'`, `status='queued'`, سبب) — **لا إسقاط صامت** (create_notification_record). fail-soft:
  غياب `tenant_id` (NOT NULL/RLS) أو تعذّر القاعدة ⇒ تخطٍّ مع debug (لا تلفيق). dispatch يستبدل البوّابة
  البسيطة بالقرار + السجلّ.

**التصنيف الصادق:** OFF آمن مُختبَر؛ مسار الإرسال الفعليّ (ON + FCM) **env-unverified** (يحتاج FCM حيّاً +
device tokens). WebSocket (M1) منفَّذ أصلاً في الوكيل (خارج نطاق هذا العلم). تحقّق: ٧ اختبارات
(`test_c4m1_mobile_push.py`: قرار skip/send/record_only · العلم off افتراضيّاً/on · السجلّ يُكتَب مع
tenant/يتخطّى بدونه) · انحدار `test_notification_tenant_isolation` أخضر · tests_v9 1851 (فشل MFA الـ5
سابقٌ) · platform 1104 · **مسح ruff كامل**.

---

## 2026-06-23 (خ) — إغلاق H2: علم نشر NATS (default off) — يحرس تشغيل الناشر

**رأس `main`:** `768c396` (#472 مُدمج). فرع `claude/h2-nats-publishers-flag`. الفجوة H2: «اشتراكات NATS
يتيمة بلا ناشر». البنية موجودة بالكامل: `_emit_domain_event` يُسجّل كلّ حدث ذرّيّاً في `events`+`event_outbox`،
و`OutboxWorker` يستنزف الـoutbox ويُسلّم إلى NATS (`sahool.events.>` → مستهلِك `notif_domain_events`).
الإغلاق ضمن إطار «implemented-but-off-by-default»:
- **علم `FEATURE_NATS_PUBLISHERS` + `nats_publishers_enabled()`** (`event_bus.py`، يُعيد استخدام
  `feature_registry.is_enabled`؛ ليس علم راوتر).
- **`main._start_outbox_worker` يُحرَس بالعلم:** OFF (افتراضيّ) ⇒ **لا يُشغَّل الناشر**، والأحداث تبقى مسجَّلة
  في outbox (`record_decision_only`) — يُعلَن السبب صراحةً في السجلّ؛ ON ⇒ يُشغَّل OutboxWorker فيُسلّم
  (`publish_event`).
- **مفتاح الصدق:** التسجيل الذرّيّ (`events`+`outbox`) **مستقلّ عن العلم** ⇒ لا يُفقَد حدث عند OFF (record
  دائم، التسليم opt-in).

**التصنيف الصادق:** OFF آمن ومُختبَر بالكامل؛ **ON env-unverified** (يحتاج خادم NATS حيّاً — لا يُتحقَّق في CI).
الاشتراكات الـ8 الخدميّة الأخرى (`sahool.alerts.weather`/`pest`/…) تبقى يتيمة لأنّ خدماتها غير مُسلَّمة —
خارج نطاق هذا العلم (يغلق ناشر الأحداث `sahool.events.>` فقط). تحقّق: ٤ اختبارات بوّابة
(`test_h2_nats_publishers_flag.py`: off افتراضيّاً · truthy ⇒ on · falsy ⇒ off · اسم العلم) · انحدار
event_bus/outbox (١٠٣) أخضر · tests_v9 1844 (فشل MFA الـ5 سابقٌ) · platform 1104 · smoke/حارس التفكيك ·
**مسح ruff كامل**.

---

## 2026-06-23 (ج) — إغلاق C5: بوّابة عتبات NDVI خلف feature flag + إعلان عدم المعايرة

**رأس `main`:** `b722b4c` (#471 مُدمج). فرع `claude/c5-ndvi-threshold-flag`. الفجوة C5: «NDVI الحقيقيّ
معلوماتيّ لا يُغيّر صلاحيّة القرار» — أُغلِقت ضمن إطار «implemented-but-off-by-default». **حقيقة صدق
حاسمة:** لا توجد عتبات NDVI **معايَرة ميدانيّاً** لأيّ محصول/مرحلة في النظام (لا بطاقة تحمل
`ndvi_thresholds`)، ولفلسفة «لا تلفيق» **لا نختلقها** — لذا الإغلاق **إعلانيّ + opt-in خامل**:
- **العلم `APPLY_NDVI_THRESHOLDS` (default OFF، ليس علم راوتر).**
- **`_apply_ndvi_threshold_gating`** (`field_state_projection`) يُعلن في `remote_sensing` (عند توفّر NDVI):
  `ndvi_thresholds_enabled` · `threshold_source` · `thresholds_applied` ·
  `calibration_status` = `insufficient_field_calibration` (OFF أو لا معايرة) / `calibrated` (ON + بطاقة
  تحمل عتبات). **لا يغيّر validity/execution_mode** — NDVI يبقى معلوماتيّاً.
- **`_ndvi_thresholds_for`** يقرأ مظروف `ndvi_thresholds` من بطاقة المحصول (غائب الآن ⇒ None دائماً —
  مهيّأ للمستقبل حين تُضاف عتبات معايَرة).
- **NDVI غير متاح ⇒ كتلة «غير متاح» الصادقة تبقى كما هي** (لا حقول عتبات بلا معنى).

**القيمة:** يحوّل حالة C5 من «Open ambiguity» إلى «Closed (implemented, gated, calibration absent)» —
إعلان صريح مُدقَّق بدل صمت، بلا أيّ تغيير قرار إنتاجيّ، ودون اختلاق عتبات. تحقّق: ٥ اختبارات
(`test_ndvi_threshold_gating.py`: OFF يُعلن insufficient · ON بلا معايرة يبقى insufficient · العتبات None
لمحصول حقيقيّ · fail-safe بلا remote_sensing · ON بلا محصول) · انحدار `test_field_state_ndvi_enrichment`
أخضر · tests_v9 1840 (فشل MFA الـ5 سابقٌ) · platform 1104 · smoke/حارس التفكيك أخضر · **مسح ruff كامل**.

---

## 2026-06-23 (ث) — إغلاق ETc-dual في CanonicalFieldState خلف feature flag (default off)

**رأس `main`:** `72586ee` (#470 مُدمج). فرع `claude/canonical-etc-dual-flag`. أوّل إغلاق ضمن إطار المستخدم
«implemented-but-off-by-default»: تحمل الحالة الكنسيّة `etc_mm = Kc·ET0` (single)؛ محرّك dual-Kc
(`compute_etc_dual`, `(Kcb·Ks+Ke)·ET0`) موجود لكن غير موصول. الإغلاق خلف `FEATURE_CANONICAL_ETC_DUAL`
(default OFF = single الحاليّ).
- **النواة (`core/engines/fao56.compute_etc_dual`، إضافيّان محفوظا السلوك):** `et0_override` (يُمرَّر ET0
  الكنسيّ الموحّد ⇒ النهج المزدوج يستعمل **نفس** ET0، حفاظاً على SSOT/H4 — تفادي تناقض et0↔etc من penman
  الداخليّ)؛ و`soil_ece=None` ⇒ `Ks=1` (الملوحة **غير مطبّقة**، قرار H5) + assumption.
- **الإسقاط (`field_state_projection`):** `_apply_canonical_etc_dual` يُعدّل كتلة `water`: العلم OFF ⇒
  `etc_source="single_kc"` بلا تغيير؛ ON + مدخلات (محصول/عمر/ET0/طقس كافٍ لـKe) ⇒ `etc_mm=etc_dual_mm` +
  `etc_source="dual_kc"` + `etc_single_mm`/`kcb`/`ke`/`dual_assumptions` (تشمل `salinity_disabled_by_default`
  + `surface_depletion_untracked_assumed_zero`) + إعادة حساب demand_class؛ ON + نقص ⇒ تراجع single +
  `etc_disabled_reason="dual_inputs_unavailable"` (declare reason). `_weatherday_from_payload` يبني WeatherDay
  من نفس حمولة الطقس (لا صيغة جديدة)؛ نقص tmin/tmax/rh/wind ⇒ None ⇒ تراجع single.
- **العلم ليس علم راوتر** ⇒ خارج `feature_registry.FEATURE_FLAGS` ⇒ `test_feature_flags_smoke` أخضر.

**صدق + أمان:** OFF افتراضيّاً ⇒ لا تغيير إنتاجيّ (single كما هو)؛ dual لا يُدخِل الملوحة ضمنيّاً (H5) ولا
يُلفّق de (معلَن)؛ ET0 مصدر واحد (override). تحقّق: ٤ اختبارات نواة (override/soil_ece) + ٦ إسقاط
(`test_etc_dual_canonical.py`: OFF single · ON dual · نقص طقس/محصول → تراجع · بلا NDVI → dual عمريّ) ·
tests_v9 1835 (فشل MFA الـ5 سابقٌ) · platform 1104 · canonical_water/smoke أخضر · حارس التفكيك · **مسح ruff كامل**.

---

## 2026-06-23 (ت) — Bundle D / D2b: تفعيل تصعيد الإجهاد المائيّ بتأكيد طيفيّ خلف feature flag

**رأس `main`:** `7c897ea` (#469 مُدمج). فرع `claude/bundle-d2b-spectral-escalation`. أقرّ المستخدم قاعدة
التصعيد المائيّ (نموذج 4 مستويات) ثمّ قرارَين: **(١)** العلم `FEATURE_WATER_STRESS_ESCALATION` معطَّل
افتراضيّاً (إطار «implemented-but-off-by-default» — مراقبة ميدانيّة قبل تغيير القرار الإنتاجيّ)؛ **(٢)**
**NDMI + MSI معاً** (متانة ضدّ غبار/سحب اليمن لتصعيد قانونيّ).
- **الإشارة الطيفيّة:** هجرة `v99_imagery_spectral_indices.sql` (أعمدة `last_ndmi/msi_mean/date` على
  `imagery_automation_fields`). NDMI/MSI **مدعومان أصلاً في الراستر** (`IndicatorKind.ndmi/msi`) ⇒ لا تغيير
  راستر؛ `imagery_automation.py` يطلبهما (`DEFAULT_INDICATORS`) ويجمعهما/يخزّنهما (نمط NDVI).
  `gather_field_freshness` يقرؤهما (SAVEPOINT منفصل عن NDVI، توافق ما-قبل-الهجرة).
- **الأهليّة (`canonical_water_stress` النقيّ):** `fuse_water_stress(ndmi, msi)` ⇒
  `spectral_confirmation_available` (كلا المؤشّرين) · `spectral_stress_detected` (moderate/severe) ·
  `escalation_eligible = critical ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ`. غياب أيّ مؤشّر ⇒ available=False
  و detected=None (صدق: «فيزياء+رصد»، لا تصعيد بلا رصد).
- **العلم + التصعيد (`field_state_projection`):** يُعاد استخدام `feature_registry.is_enabled` (العلم **ليس**
  علم راوتر ⇒ خارج `FEATURE_FLAGS` dict، يبقى `test_feature_flags_smoke` أخضر). الكتلة تُعلن دائماً
  `escalation_eligible`/`escalation_triggered`/`disabled_reason` (`feature_flag_off`). عند العلم ON ⊕ الأهليّة ⊕
  `execution_mode==auto` ⇒ `human_review` + degraded + سبب (نمط الملوحة/الحدّ).

**صدق + أمان:** العلم off افتراضيّاً ⇒ **لا تغيير قرار إنتاجيّ** (الإشارة + الأهليّة معلوماتيّتان، السبب
مُعلَن). إعادة استخدام صرفة (`fuse_water_stress`/`is_enabled`/نمط NDVI/التصعيد). تحقّق: ٥ اختبارات قارئ + ٤
إسقاط (علم OFF لا يُصعّد + `disabled_reason` · علم ON يُصعّد · غياب طيف لا · ثقة<0.8 لا) · tests_v9 1825
(فشل MFA الـ5 سابقٌ) · platform 1104 · `test_feature_flags_smoke` أخضر · حارس التفكيك · **مسح ruff كامل**.

---

## 2026-06-23 (ش) — Bundle D / D2a: كتلة الإجهاد المائيّ الكنسيّة (معلوماتيّة، بلا تصعيد)

**رأس `main`:** `208454d` (#468 مُدمج). فرع `claude/bundle-d2a-water-stress`. بعد Bundle B، D2 هو الأخير
في ترتيب المستخدم — **حسّاس (يغيّر القرار)**، فطُلِبت خطّة رسميّة + إقرار عتبة. أُنشئت
[`decisions/water-stress-d2.md`](decisions/water-stress-d2.md) وأُقِرّت العتبة (نموذج 4 مستويات).
- **قرار المستخدم (2026-06-23):** NORMAL (AWF>1−p) · WATCH (Dr≥RAW، تنبيه) · CRITICAL (AWF≤0.2، توصية) ·
  **ESCALATE→human_review** حصراً عند `AWF≤0.2 ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ (NDMI/MSI)` —
  «فيزياء+رصد»، نادر عالي الثقة (بدء الإجهاد Dr≥RAW **لا** يُصعّد كي لا يُغرِق المهندس).
- **D2a (هذا العمل — إضافيّ محفوظ السلوك):** قارئ نقيّ `api/canonical_water_stress.py`
  (`canonical_water_stress(row)` → AWF عبر `soil_water.available_water_fraction` + مستوى + موسوم
  `calibrated=False`؛ غياب Dr/TAW ⇒ None). `recompute_field_state` يقرأ أحدث استنزاف+ثقة من
  `water_ledger` ويشتقّ TAW من `soil_water_params` ويُسقط كتلة `water_stress`. `diagnose` يقرؤها.
  **بلا تصعيد** — المسار القانونيّ (validity/execution_mode) كما هو تماماً.
- **D2b (التصعيد) مؤجَّل بإشارة:** يتطلّب `spectral_stress_detected` (NDMI/MSI) غير المحقون في المسار
  الكنسيّ بعد — بقرار المستخدم نفسه لا تصعيد بلا طيف، فبناؤه الآن = كود خامد. ينتظر توصيل الطيف.

**صدق + أمان:** إعادة استخدام صرفة للفيزياء القائمة (`soil_water`/`water_ledger`)؛ TAW/p غير معايَرين
يمنيّاً ⇒ موسوم `calibrated=False` (لا اختلاق دقّة). تحقّق: ٥ اختبارات قارئ
(`tests_v9/test_canonical_water_stress.py`) + ٢ إسقاط (`test_field_state_unification.py`: كتلة حاضرة بلا
تصعيد · لا دفتر لا كتلة) · tests_v9 1816 (فشل MFA الـ5 سابقٌ) · platform 1104 · حارس التفكيك أخضر ·
**مسح ruff كامل**. (يشمل هذا الفرع أيضاً بكرة دفتر Bundle B بعد دمج #468: رأس main + سجلّ القرارات §4.)

---

## 2026-06-23 (ر) — Bundle B: تصعيد ثقة حدود الحقل في الحالة القانونيّة

**رأس `main`:** `bc16209` (#467 مُدمج). فرع `claude/bundle-b-boundary-confidence`. بعد D3 اختار المستخدم
boundary_confidence ثانياً (مستقلّ عن SSOT). الفجوة: محرّك التهديف `api/boundary_confidence.score_boundary`
+ تخزين `field_boundaries.confidence_score` (v58) **موجودان**، لكنّ الثقة **لا تُقرأ في الحالة القانونيّة**
فلا تُصعّد قراراً — حدّ ضعيف الترسيم يتسرّب بصمت إلى المساحة/الريّ/الإنتاجيّة.
- **قارئ كنسيّ نقيّ** `api/canonical_boundary.py`: `canonical_boundary(row)` يطبّع صفّ جودة الحدّ إلى كتلة
  `{boundary_confidence, boundary_source, boundary_version, review_status, review_recommended, source}` —
  `review_recommended` من **نفس عتبة** `CONFIDENCE_REVIEW_THRESHOLD=0.6` (مصدر واحد)؛ غياب الثقة ⇒ None.
- **تصعيد في `recompute_field_state`** (نظير تصعيد الملوحة الحرجة): ثقة < 0.6 و`execution_mode=="auto"`
  ⇒ `human_review` + `validity` يتدهور valid→degraded + سبب عربيّ. تصعيد سلامة لا تخفيض — لا يلمس إلّا
  auto/valid ولا يغيّر أرقاماً. كتلة `boundary` تُسقَط على نموذج الحالة + يقرؤها `diagnose` من مصدر واحد.

**صدق + أمان:** لا تهديف جديد (يُعاد استخدام score_boundary)؛ غياب صفّ/ثقة ⇒ لا كتلة ولا تصعيد (لا تصعيد
على غياب). تحقّق: ٤ اختبارات قارئ (`tests_v9/test_canonical_boundary.py`) + ٣ تصعيد
(`test_field_state_unification.py`: منخفضة تُصعّد · عالية لا · لا صفّ لا تصعيد) · tests_v9 1809 (فشل MFA
الـ5 سابقٌ) · platform 1104 · حارس التفكيك أخضر · **مسح ruff كامل** على الملفّات المتغيّرة.

---

## 2026-06-23 (ق) — Bundle D المرحلة D3: قراءة ET0/ETc من مصدر واحد (#467)

**رأس `main`:** `204b68e` (#466 مُدمج). فرع `claude/bundle-d3-canon-read`. اختار المستخدم D3 أوّلاً
(آمن، لا يغيّر القرار/الحسابات/SSOT) ثمّ boundary_confidence ثمّ D2 لاحقاً (خطّة رسميّة).
- **قارئ كنسيّ نقيّ** `api/canonical_water.py`: `canonical_water(operational_truths)` يستخرج كتلة
  `{et0_mm, etc_mm, etc_demand_class, kc, fao56_stage, source}` — **قراءة صرفة لا حساب**؛ غياب ET0/ETc
  ⇒ None (لا اختلاق). يُغلق فئة التناقضات: مصدر قراءة واحد بدل تعدّد.
- **كتلة `water` موحّدة** تُسقَط على نموذج الحالة في `recompute_field_state` (إضافيّ، read-only).
- **مستهلِك `diagnose`** يقرأ `field_state["water"]` بدل التنقيب في operational_truths متفرّقاً.

**صدق + أمان:** لا يمسّ المحرّكات/القرار (validity/execution_mode) ولا الحسابات ولا SSOT نفسه — قراءة
موحّدة فقط. تحقّق: ٣ اختبارات جديدة (`tests_v9/test_canonical_water.py`) · `pytest -m unit` 1802 (فشل
MFA الـ5 سابقٌ) · انحدار field_state/agronomic/diagnose (٧٩) أخضر · حارس التفكيك · **مسح ruff كامل**.

---

## 2026-06-23 (ف) — Bundle D المرحلة D1: ET0/ETc الكنسيّان في الحالة القانونيّة (#466)

**رأس `main`:** `f015fef` (#465 مُدمج). فرع `claude/bundle-d-water-canon`. أوّل خطوة من Bundle D
(FieldState Water Canonicalization) — **خطّة متأنّية مرحليّة (يمسّ SSOT)**؛ استكشافان مُسبقان (بنية
الحالة + خريطة حسابات المياه) أكّدا أنّ `operational_truths` يحمل `kc` لكن لا `et0`/`etc`.
- **D1 (إضافيّ محفوظ السلوك):** إسقاط الحالة (`api/field_state_projection.py`) يشتقّ ET0 من الطقس
  المخزَّن (`weather_automation_cache`) عبر **`core/engines/et0` الموحّد** (H4 — Hargreaves/PM، لا صيغة
  جديدة)، ويمرّر المحصول/العمر + ET0 عبر `CropContext` إلى `compose_field_state`. كتلة Kc القائمة
  (`agronomic_state_engine._wire_phenology_and_calendar`) تضيف `et0_mm`/`etc_mm`=Kc·ET0/`etc_demand_class`
  + provenance — **دون مسّ** التحكيم (validity/execution_mode/الملوحة) ولا مخطّط القاعدة ولا المستهلكين.
- **صدق + fail-safe صارم:** طقس/محصول/عمر ناقص ⇒ ET0=None ⇒ `etc` يغيب (لا اختلاق)؛ المسار best-effort
  لا يكسر الحالة التشغيليّة. حفظ السلوك مؤكَّد (٥٦ اختبار field_state/agronomic أخضر، والإضافة لا تمسّ
  Kc/effective_status). **D2 (تحكيم الإجهاد) + D3 (نقل المستهلكين/إزالة تكرار) مؤجَّلتان بإقرار.**

تحقّق: ٦ اختبارات جديدة (`tests_v9/test_fieldstate_water_canon.py`) · `pytest -m unit` 1799 (فشل MFA الـ5
سابقٌ) · حارس التفكيك · **مسح ruff كامل** · انحدار field_state/agronomic أخضر.

---

## 2026-06-23 (ع) — Bundle B صغيرة: TAW ديناميكيّ من Zr + NDVI من COG الطازج (وكيلان، #465)

**رأس `main`:** `08211af` (#464 مُدمج). فرع `claude/bundle-b-zr-ndvi`. تثبيت خارطة الحِزَم أوّلاً
(Bundle D — FieldState Water Canonicalization مستقلّة متأنّية + Bundle C R&D، بتوجيه المستخدم) ثمّ
وكيلان متوازيان (بصمات منفصلة، cherry-pick نظيف):
- **أ — ربط Zr بالاستنزاف:** نقطة `/api/v1/fields/{id}/water-twin` تشتقّ **TAW ديناميكيّاً** من عمق
  الجذور: `root_depth_for_crop(profile, das)` → `taw_from_root_depth(Zr, texture)` (FAO-56 §8/Eq.82)
  عند غياب `taw_mm`؛ `taw_source` مُعلَن. حفظ السلوك: تمرير `taw_mm` صريحاً ⇒ كما كان. (`routers/water_twin.py`)
- **ب — NDVI من COG الطازج:** نقطة `etc-dual` تجلب NDVI الأطزج من raster `indicator-grid` (`real_data`)
  بأولويّة **تجاوز > طازج (raster_fresh_cog) > مخزَّن > none** — تدرّج صادق عند تعذّر raster؛ علم
  `prefer_fresh_ndvi`. دالّة اختيار نقيّة `_pick_ndvi`. (`routers/etc_dual.py`)

**صدق:** مصدر كلّ قيمة مُعلَن (`taw_source`/`ndvi.source`)؛ لا اختلاق (TAW يحتاج بطاقة/عمر وإلّا 422؛ NDVI
طازج فقط بـ`real_data=true`)؛ Zr/θ تقديريّة مُعلَنة. تحقّق: `pytest -m unit` 1793 (فشل MFA الـ5 سابقٌ) ·
حارس التفكيك · **مسح ruff كامل على كلّ الملفّات المتغيّرة** (تفادياً لدرس lint #464) أخضر.

---

## 2026-06-23 (س) — توحيد H5: الملوحة مفتاح اختياريّ + تفعيل تلقائيّ من جودة التحليل (٣ وكلاء، #464)

**رأس `main`:** `8e35fde` (#463 مُدمج). فرع `claude/h5-irrigation-unify`. **القرار البشريّ (المستخدم):**
«نفّذ بلا ملوحة، وليكن مرناً قابلاً لإدخالها في أيّ مرحلة» ثمّ «تُفعَّل تلقائيّاً عند تحليل مخبريّ موثوق».
ثلاثة وكلاء متوازين (بصمات منفصلة، عقد واجهة مُحدَّد مسبقاً، cherry-pick نظيف) + ربط يدويّ:
- **أ — المحرّك:** `compute_irrigation` اكتسب `apply_salinity: bool = False` (off ⇒ Ks=1، تسريب=0) +
  `IrrigationResult.salinity_applied`. حفظ السلوك عند on (نفس Eq.81/82).
- **ب — الـAPI:** `water_balance` اكتسب نفس الخطّاف (off=محفوظ تماماً، شكل القاموس الثمانيّ سليم) +
  تفويض `salinity_management.leaching_requirement` لـ`fao56` (إزالة تكرار، مصدر صيغة واحد).
- **ج — السياسة:** `core/salinity_policy.salinity_decision` (نقيّة، ٢٢ اختباراً): تُفعِّل الملوحة عند
  ECe/ECw حديثة (<365) + ثقة (≥0.8) أو ECe>2/ECw>1.5/محصول حسّاس؛ تُعطِّل عند الغياب/القِدم/تقدير؛
  تُنبّه (warn) في المناطق المالحة ببيانات قديمة. عتبات مُعلَنة قابلة للمعايرة.
- **الربط (يدويّ):** `water_balance_auto` + حقول تحليل اختياريّة في `WaterBalanceRequest` + راوتر
  `/api/v1/water-balance` يحسب `apply_salinity` تلقائيّاً من التحليل المُمرَّر ويعرض `salinity_decision`
  (غياب التحليل ⇒ الردّ كما كان تماماً). ٤ اختبارات ربط (بحارس تخطّي api).

**صدق:** الملوحة **مُطفأة لا محذوفة** (`salinity_applied`/`salinity_decision` مُعلَنان)؛ لا تفعيل على
بيانات غير موثوقة؛ صيغ FAO-56 محفوظة، صيغة تسريب واحدة. التضارب (جوابان) مُغلَق (اختبار يُثبت تطابق
المسارين افتراضيّاً). **متبقٍّ موثَّق:** ربط `salinity_decision` بـ`compose_field_state`/water_kernel (SSOT).
تحقّق: `pytest -m unit` 1775 (فشل MFA الـ5 سابقٌ) · حارس التفكيك · ruff · انحدار water_balance/engines أخضر.

---

## 2026-06-23 (ن) — اكتمال ذكاء المياه: Open-Meteo + Zr + لوحة etc-dual (٣ وكلاء، #463)

**رأس `main`:** `1e112a7` (#462 مُدمج). فرع مستقلّ `claude/water-intel-self-sufficient`. ثلاث مهامّ
جاهزة مستقلّة بثلاثة وكلاء (بصمات منفصلة؛ A أعدته يدويّاً بعد فشل اتّصال وكيله؛ B/C cherry-pick نظيف):
- **A — طقس Open-Meteo حيّ:** نقطة `etc-dual` صارت ذاتيّة-الاكتفاء — الطقس اختياريّ يُجلب من
  Open-Meteo بإحداثيّات الحقل (`api/connectors/openmeteo`) خارج اتّصال القاعدة؛ `weather_source` مُعلَن؛
  تعذّر ولا طقس ⇒ 503 صادق. `_resolve_weather` نقيّ + ٤ اختبارات.
- **B — عمق جذور ديناميكيّ Zr:** `core/engines/fao56.py` (إضافيّ نقيّ) — `root_depth_m`/
  `root_depth_for_crop`/`taw_from_root_depth` + جدول θFC/θWP (FAO-56 §8/Table 19) + ١٨ اختباراً.
- **C — لوحة واجهة:** `EtcDualPage.tsx` («ETc المزدوج» تحت الريّ) — منتقي حقل + طقس + تجاوزات +
  عرض ETc/Kcb/مصدر NDVI/الافتراضات. مُسجَّلة في App/routes/permissions (`PageId 'etc-dual'`).

اتّساقاً مع الاستراتيجيّة: نُفِّذت الجاهزة المستقلّة فقط؛ أُبقي المُعطَّل بسببه (H5 إقرار زراعيّ · H2
معماريّ · C5/C4/SAM2 ميدان/Flutter/GPU · LULC بيانات · CanonicalFieldState أكبر). **صدق:** كلّ القيم
تقديريّة مُعلَنة المصدر؛ لا اختلاق طقس/NDVI. تحقّق: `pytest -m unit` 1739 (فشل MFA الـ5 سابقٌ) ·
حارس التفكيك · ruff · typecheck/build/vitest 332.

---

## 2026-06-23 (م) — الربط الاستهلاكيّ: نقطة etc-dual تحقن NDVI الحيّ (#462)

**رأس `main`:** `56f2f79` (#461 مُدمج). فرع مستقلّ `claude/etc-dual-ndvi`. يُغلق حلقة #461: محرّك
`compute_etc_dual` كان كامناً (غير مكشوف)؛ الآن نقطة field-scoped تستهلكه بـNDVI حيّ:
- **`api/routers/etc_dual.py`:** `POST /api/v1/fields/{id}/etc-dual` (FIELD_VIEW، RLS) — يقرأ الحقل
  (محصول/تاريخ زراعة) + أحدث NDVI/ملوحة مخزَّنة، يبني `WeatherDay` (الطقس يمرّره المتّصِل)، ويستدعي
  المحرّك. NDVI من `gather_field_freshness` (`imagery_automation_fields.last_ndvi_mean`) — **تجاوز >
  مخزَّن > none** (تدرّج صادق، مصدر مُعلَن). بطاقة/عمر مفقودان ⇒ 422؛ خارج المستأجِر ⇒ 404؛ DB ⇒ 503.
- **DRY:** استُخرِج `crop_kc_profile(crop_id)` في `core/season_phenology.py` (يُستدعى من `stage_kc`
  القائمة ومن النقطة) — بلا تغيير سلوك. أُعيد استخدام `resolve_crop_id` + `gather_field_freshness`.
- **صدق:** لا اختلاق NDVI؛ الطقس صريح (لا اعتماد شبكة جديد)؛ مصدر كلّ قيمة في الردّ (`ndvi.source`،
  `soil_ece_source`). **متبقٍّ موثَّق:** طقس Open-Meteo حيّ · NDVI من COG طازج · لوحة واجهة.

تحقّق: ٤ اختبارات جديدة (`tests_v9/test_etc_dual_router.py`) + حارس التفكيك · `pytest -m unit` 1717
ناجح (فشل MFA الـ5 سابقٌ) · ١٧+٦ انحدار dual-Kc/NDVI أخضر · ruff/format.

---

## 2026-06-23 (ل) — Kc ديناميكيّ من NDVI (FAO-56 §9.4، #461)

**رأس `main`:** `5ed73c0` (#460 مُدمج). فرع مستقلّ `claude/dynamic-kc-ndvi`. يربط محرّك المياه
بالأقمار: بدل اشتقاق Kcb من عمر المحصول (منحنى جدوليّ)، يُشتقّ من **غطاء نباتيّ مرصود** (NDVI):
- `core/engines/fao56.py`: `fractional_cover_from_ndvi` (fc من NDVI، مقصوص + معايرة) +
  `density_coefficient_kd` (FAO-56 Eq. 76: `min(1, ML·fc, fc^(1/(1+h)))`) + `kcb_from_ndvi`
  (`Kcb=Kcb_full·Kd`). و`compute_etc_dual` يقبل `ndvi` اختياريّاً ⇒ Kcb وfc مرصودان.
- **حفظ السلوك:** غياب NDVI ⇒ المسار القائم تماماً (١٧ اختبار dual-Kc أخضر؛ المسار المفرد سليم).
- **صدق:** الحدود (NDVI_bare/full=0.15/0.85) و ML تقديريّة **تحتاج معايرة محلّيّة** — تُعلَن في
  `assumptions` وقت التشغيل (لا تلفيق دقّة). إضافة engine-level (كنمط dual-Kc): الربط الاستهلاكيّ
  (تمرير NDVI الحيّ من raster-service) مرحلة تالية موثَّقة.

تحقّق: ٦ اختبارات جديدة (`tests_v9/test_kc_ndvi.py`) + ١٧ انحدار dual-Kc · `pytest -m unit` 1713
ناجح (فشل MFA الـ5 سابقٌ) · ruff/format.

---

## 2026-06-23 (ك) — Water Twin المرحلة الثانية: تغذية بالدفتر v98 + واجهة منزلقات (#460)

**رأس `main`:** `7fe1244` (#459 مُدمج). فرع مستقلّ `claude/water-twin-phase2` (فُرِّع من tip v1
ثمّ `rebase --onto origin/main` لإسقاط commit v1 المُدمَج). يُكمل Water Twin v1:
- **backend:** نقطة field-scoped `POST /api/v1/fields/{id}/water-twin` تقرأ أحدث صفوف دفتر المياه
  (RLS) فتشتقّ النضوب الابتدائيّ + متوسّط ETc، ثمّ تحاكي «تأجيل/تخفيض الريّ». وحدة نقيّة
  [`api/water_twin_seed.py`](../services/sahool-platform/api/water_twin_seed.py) (٦ اختبارات) +
  [`api/routers/water_twin.py`](../services/sahool-platform/api/routers/water_twin.py) (مُسجَّل،
  حارس التفكيك أخضر). **صدق:** مصدر كلّ قيمة مُعلَن (`seed.*_source`)؛ غياب المصدر ⇒ 422 صادق؛
  TAW/RAW صريحان (لا يُخمَّنان).
- **frontend:** [`WaterTwinPage.tsx`](../frontend/src/sections/WaterTwinPage.tsx) — قسم «توأم المياه»
  (تحت الريّ): منتقي حقل + منزلقا (تأجيل أيّام / تخفيض ٪) + جدول المقارنة + مسار النضوب اليوميّ
  + إعلان مصدر التغذية. `simulateFieldWaterTwin` في `api.ts` + تسجيل في routes/permissions/App.

تحقّق: `pytest -m unit` 1707 ناجح (فشل MFA الـ5 سابقٌ) · حارس التفكيك · ruff · typecheck/build/vitest 332.

---

## 2026-06-23 (ي) — Water Twin Simulator v1 (مسار رطوبة التربة الأماميّ، #459)

**رأس `main`:** `3f87180` (#458 مُدمج). فرع مستقلّ `claude/water-twin-simulator`. أبرز فكرة من
إلهام IrriPro (`water-intelligence-direction.md`): محرّك نقيّ `api/water_twin.py` يحاكي **نضوب
الجذور أماميّاً** (FAO-56 فصل ٨: `Dr` يوميّ + `Ks` تحت الإجهاد `ETa=Ks·ETc` + قصّ `[0,TAW]`) +
محوّلات «ماذا لو» (تأجيل/تحجيم الريّ) + مقارنة أساس↔بديل (أيّام إجهاد · استهلاك ماء · أقصى نضوب).
نقطة `POST /api/v1/scenario/water-twin` أُضيفت لراوتر scenario المُفكَّك (لا توسيع main.py، حارس
التفكيك أخضر) + ١١ اختبار وحدة.

**صدق:** حساب فيزيائيّ offline — **لا يدّعي غلّة/إنتاج** (لا نموذج مُعايَر)، المخرَج أيّام الإجهاد/
النضوب/الماء فقط والملخّص يصرّح بذلك. يكمّل `scenario_whatif.py` (يوم-واحد) بالبُعد الزمنيّ متعدّد
الأيّام. **متبقٍّ موثَّق:** تغذية الحالة من دفتر v98 آليّاً + واجهة منزلقات (مرحلة ثانية).
تحقّق: `pytest -m unit` 1701 ناجح (فشل MFA الـ5 سابقٌ لا صلة له) · حارس التفكيك · ruff/format.

---

## 2026-06-23 (ط) — دفتر مياه يوميّ (v98) + تصدير Parquet + تحقيق H2 (بثلاثة وكلاء، #458)

**رأس `main`:** `89d848e` (#457 مُدمج). ثلاثة وكلاء متوازون في worktrees منفصلة الملفّات؛ دُمج
الكوديّان عبر cherry-pick نظيف (لا تضارب):
- **أ — دفتر المياه اليوميّ (Bundle B، فجوة IrriPro #1):** ترحيل `v98_water_ledger.sql` (جدول معزول
  بالمستأجِر + RLS/FORCE، PK مركّب `(field_id, ledger_date)`) + راوتر `api/routers/water_ledger.py`
  (POST upsert + GET بمدى، honest-503) + وحدة نقيّة `api/water_ledger_compute.py` + 18 اختباراً.
  **صدق:** كلّ القيم nullable — الناقص `NULL` لا تلفيق؛ `bool`/نصّ فارغ مرفوضان كعدد.
- **ب — تصدير Parquet لورشة SQL (Bundle B):** `frontend/src/services/duckdb.ts` (`exportQueryToParquet`
  عبر `COPY … (FORMAT PARQUET)` → `copyFileToBuffer`) + زرّ في `SQLEditor.tsx`. **صدق التسمية:**
  «Parquet» لا «GeoParquet» (جدول `fields` سمات بلا هندسة) + `TODO(GeoParquet)` موثَّق. vitest 332.
- **ج — تحقيق H2 (تقرير فقط، بلا كود):** مسح يدويّ كامل (الأداة `sahool_inspector` تفحص `services/`
  فقط فتفوّت مُشترِكي `agents/`). النتيجة: **٧** اشتراكات يتيمة لا ٨ (`satellite.*.computed`/
  `sahool.events.>` لهما ناشرون)، تصنيفها «ناشر مفقود متوقَّع» (قرار معماريّ ⇒ امتناع عن تغيير الكود
  بقاعدة اللبس). حُدِّث سجلّ الفجوات. **مخرَج صادق نافع: منع حذف عقود تكامل مقصودة.**

اتّساقاً مع الاستراتيجيّة: نُفِّذت B الجاهزة فقط؛ H2 بقي معماريّاً مفتوحاً (لا إصلاح آليّ غامض).
تحقّق: 26 اختباراً (دفتر+حارسان) · v98 يجتاز `validate_migrations` · ruff · vitest 332 · cherry-pick نظيف.

---

## 2026-06-23 (ح) — CDSE مزوّداً افتراضيّاً للصور + fallback تلقائيّ إلى Element84

**رأس `main`:** `1146021` (#456) — العمل على فرع `claude/code-review-34hO3` فوق #457.
أُضيف **Copernicus Data Space Ecosystem (CDSE)** كمزوّد صور **افتراضيّ أقوى** (Sentinel Hub
Process API): يحسب المؤشّر **خادميّاً** عبر `evalscript` على نطاقات Sentinel-2 L2A الكاملة
(فسيفساء أقلّ غيوماً) فيُرجِع GeoTIFF نطاق-واحد جاهزاً — مع **تحوّل تلقائيّ (fallback) إلى
Element84** عند تعذّر CDSE.

- **raster-service:** وحدة جديدة [`cdse_client.py`](../services/raster-service/cdse_client.py)
  (OAuth client_credentials + ذاكرة توكن + `build_evalscript` نقيّ لـ11 مؤشّراً + `bbox_dims`).
  نقطة `POST /v1/fields/{id}/process-cdse` (خدمة-لخدمة، `_require_service_token`) + مسار
  `precomputed_index` في [`main.py`](../services/raster-service/main.py) (يقرأ المؤشّر الجاهز
  → COG/persist/provenance، يعيد استخدام تسجيل الطبقات).
- **المنسّق:** [`imagery_automation.py`](../services/sahool-platform/api/imagery_automation.py)
  `_try_cdse` يُجرَّب أوّلاً في `trigger_field_imagery_processing`؛ غياب الاعتمادات/تعذّر ⇒
  `None` ⇒ يسقط بصمت إلى مسار Element84 القائم (best + process-from-stac). فالنقطة القائمة
  `/imagery/refresh` وأتمتة إنشاء الحقل تستفيدان تلقائيّاً (لا تغيير واجهة لازم).
- **صدق/أمان:** بلا `CDSE_CLIENT_ID/SECRET` (أو `CDSE_ENABLED=false`) ⇒ `is_configured()=False`
  ⇒ Element84 (السلوك القائم — لا كسر). **السرّ يُمرَّر بالمرجع `${CDSE_CLIENT_SECRET}`** في
  compose من `.env` غير المتتبَّع — لا قيمة حرفيّة في أيّ ملفّ. لا يُتحقَّق CDSE حيّاً في CI
  (لا اعتمادات/شبكة) — الدوالّ النقيّة فقط مُختبَرة؛ المسار الحيّ يؤكّده المشغّل.

تحقّق: 16 اختبار وحدة جديد ([`test_cdse_evalscript.py`](../tests_v9/test_cdse_evalscript.py)) ·
حارس تفويض الراستر أخضر (أُدرجت النقطة في `FIELD_SCOPED_SERVICE_ONLY`) · `pytest -m unit`
1686 ناجح (فشل MFA الـ5 سابقٌ لا صلة له، في `services/auth`) · ruff/format نظيف.

---

## 2026-06-23 (ز) — تنفيذ الاستراتيجيّة بوكيلين: تأكيد توحيد ET0 + Dual Kc (#457)

**رأس `main`:** `1146021` (#456). أوّل تنفيذ من [`decisions/strategy.md`](decisions/strategy.md) (Bundle A/B)، وكيلان متوازيان منفصلا الملفّات (cherry-pick نظيف):
- **توحيد ET0 (H4):** اكتشاف صادق — كان مُنجَزاً (#351/#356)؛ `core/engines/et0.py` يحسب Ra per FAO-56
  (لا ثابتاً) وكلّ المستدعين يُفوّضون. أُضيف **5 اختبارات انحدار** تُقفل الإصلاح + توثيق. لم يُعَد refactor
  (كان هدّاماً). متبقٍّ موثَّق: إعادتان عبر-خدمات (`weather_server`/`wofost`) — مؤجَّلتان (ربط عبر-خدمات).
- **Dual Kc (#457):** `compute_etc_dual` في `core/engines/fao56.py` (إضافيّ، المفرد افتراضيّ سليم) —
  `ETc=(Kcb·Ks+Ke)·ET0` (FAO-56 71-80) + 17 اختباراً. صدق: Kcb بإزاحة موثّقة؛ TEW/REW جداول؛
  الافتراضات تُعرَض وقت التشغيل (`DualKcResult.assumptions`).

اتّساقاً مع الاستراتيجيّة: نُفِّذت مهامّ A/B الجاهزة فقط؛ أُجّل C (R&D) وH5 (إقرار زراعيّ) والغامض.
تحقّق: 27 اختباراً (et0+dual) · ruff · حارس الراوترات · الفجوة H4 → ✅ مؤكَّدة.

---

## 2026-06-23 (و) — مراجعات إلهام (CultiWise/IrriPro، #455) + تصدير وصفة Shapefile (#456)

**رأس `main`:** `6e770b7` (#455). مراجعتا اتّجاه مُسنَدتان + أوّل اقتباس CultiWise منفَّذ:
- **#455:** صفحتا دماغ — [`precision-ag-direction.md`](decisions/precision-ag-direction.md) (CultiWise) +
  [`water-intelligence-direction.md`](decisions/water-intelligence-direction.md) (IrriPro/FAO-56). الكشف:
  SAHOOL يملك أصلاً معظم اللبنات (وصفات v95 · سجلّ قرار/نتيجة · FAO-56/ET0/هيدروليك/سيناريو/تفسير) —
  لا نُعيد البناء؛ الفجوات الحقيقيّة فقط (تصدير آلة · دفتر مياه يوميّ · توحيد ET0 H4 · Water Twin).
- **#456 (تصدير الوصفة Shapefile):** يملأ TODO موثَّقاً — `GET …/prescriptions/{id}/export?format=shapefile`
  → ZIP (.shp/.shx/.dbf/.prj) عبر `pyshp` (نقيّ-Python). وحدة نقيّة
  [`api/prescription_shapefile.py`](../services/sahool-platform/api/prescription_shapefile.py) (7 اختبارات) +
  راوتر + زرّ في PrescriptionBuilderPage. تبعيّة `pyshp==2.3.1` (pip-audit: 0 ثغرات). **ISOXML يبقى TODO
  موثَّقاً** (يحتاج نمذجة معدّات — لا ندّعي ما لا ننتجه). يحوّل المنصّة من «مراقبة» إلى «تنفيذ».

تحقّق: pip-audit نظيف · ruff · حارس الراوترات · 7 اختبارات وحدة · typecheck/build/vitest 332 · روابط الدماغ سليمة.

---

## 2026-06-23 (هـ) — AI GIS Assistant (NL→SQL، الفكرة 4 الأخيرة من GeoLibre، #454)

**رأس `main`:** `8781cce` (#453). مهمّة LLM-shaped — قُرئ مرجع claude-api؛ المفتاح خادميّ.
- صندوق «اسأل بالعربيّة» في ورشة SQL → `POST /api/v1/nl-sql` يستدعي Claude (`claude-opus-4-8`،
  قابل للضبط بـ`NL_SQL_MODEL`) → SELECT للقراءة فقط → يملأ المحرّر للمراجعة → DuckDB العميل.
- خادم: [`api/routers/nl_sql.py`](../services/sahool-platform/api/routers/nl_sql.py) +
  [`api/nl_sql_validate.py`](../services/sahool-platform/api/nl_sql_validate.py) (تحقّق نقيّ، 22 اختباراً).
  تبعيّة `anthropic` (pip-audit: 0 ثغرات). واجهة:
  [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) + `api.ts`.
- صدق/أمان: خصوصيّة (السؤال فقط) · SELECT مُتحقَّق + sandbox العميل + إنسان-في-الحلقة · مُغلَق
  بـ`FEATURE_NATURAL_LANGUAGE_GIS`+`ANTHROPIC_API_KEY` (honest-503). المشغّل يوفّر المفتاح.
- **خارطة GeoLibre الأربع مكتملة v1** ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

تحقّق: pip-audit نظيف · 22 اختبار وحدة + حارس الراوترات أخضر · typecheck/build/vitest 332.

---

## 2026-06-23 (د) — إكمال خارطة GeoLibre بـ٣ وكلاء متوازين (#453)

**رأس `main`:** `c3c7d28` (#452). ثلاثة وكلاء في worktrees منفصلة الملفّات (بلا تضارب عدا منطقة أزرار
SQLEditor — حُلّت بإبقاء CSV+JSON معاً)، دُمجت عبر cherry-pick:
- **و1 — ورشة SQL v2:** سجلّ استعلامات (localStorage) + أمثلة جاهزة + نسخ JSON
  ([`sqlHistory.ts`](../frontend/src/lib/sqlHistory.ts) + [`SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx)).
- **و2 — حفظ مساحة العمل v2:** التقاط/استعادة مركز+تكبير الخريطة عبر المحرّكين
  ([`HubMap.tsx`](../frontend/src/components/maphub/HubMap.tsx) · [`HubMapGL.tsx`](../frontend/src/components/maphub/HubMapGL.tsx) ·
  [`projectFile.ts`](../frontend/src/lib/projectFile.ts)) — بمنع حلقة moveend↔restore وحفظ auto-fit.
- **و3 — استوديو الهندسة المكانيّة:** قسم «أدوات الهندسة» + Turf buffer/simplify معاينةً
  ([`GisToolsPage.tsx`](../frontend/src/sections/GisToolsPage.tsx) + [`fieldGeometryOps.ts`](../frontend/src/lib/fieldGeometryOps.ts)).
  تبعيّتا `@turf/buffer`/`@turf/simplify` (0 ثغرات).

تحقّق دفعةً: typecheck نظيف · build (chunks منفصلة) · **vitest 332** · روابط الدماغ سليمة.

---

## 2026-06-23 (ج) — ورشة SQL في المتصفّح (DuckDB-WASM، إلهام GeoLibre الفكرة 2)

**رأس `main`:** `cd68a33` (#450، الاسترجاع التلقائيّ مدموج).

- **حفظ مساحة العمل (تكملة):** الاسترجاع التلقائيّ عبر localStorage (#450) — اكتملت الفكرة 1.
- **ورشة SQL (#451):** قسم جديد lazy «ورشة SQL (DuckDB)» تحت «البيانات والتحليل» — يحمّل حقول
  المستأجر إلى جدول `fields` في DuckDB-WASM (عميل-فقط، مستضاف ذاتيّاً) ويستعلمها بـSQL.
  ملفّات: [`frontend/src/services/duckdb.ts`](../frontend/src/services/duckdb.ts) ·
  [`frontend/src/hooks/useDuckDB.ts`](../frontend/src/hooks/useDuckDB.ts) ·
  [`frontend/src/components/sql/SQLEditor.tsx`](../frontend/src/components/sql/SQLEditor.tsx) ·
  [`frontend/src/sections/SQLWorkspacePage.tsx`](../frontend/src/sections/SQLWorkspacePage.tsx).
  تبعيّة `@duckdb/duckdb-wasm` (0 ثغرات، كسولة ~8MB gzip خارج الحزمة الرئيسة). النطاق v1: سمات
  الحقول فقط — spatial/المؤشّرات مؤجّلة ([`decisions/gis-direction.md`](decisions/gis-direction.md)).

---

## 2026-06-23 (ب) — الدماغ على main + حفظ مساحة العمل (إلهام GeoLibre)

**رأس `main`:** `033fabe` (#448، الدماغ مدموج).

- **الدماغ (#448):** دُمج `sahool-brain/` على main — الوكيل القادم يقرأ hot/index بداية الجلسة.
- **حفظ مساحة العمل (GeoLibre، الفكرة 1):** ملفّ `.sahool-project.json` قابل للتسلسل (عميل-فقط) —
  تصدير/استيراد إعدادات «مركز الخرائط» (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات/الحقل
  المختار): [`frontend/src/lib/projectFile.ts`](../frontend/src/lib/projectFile.ts) + أزرار في
  [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx). v1 لا يحفظ مركز/تكبير
  الخريطة ولا الرسومات (مؤجّلة v2). انظر [`decisions/gis-direction.md`](decisions/gis-direction.md).

---

## 2026-06-23 — سلسلة الموبايل/الصور/QA + إنشاء الـbrain

**رأس `main` بعد الجلسة:** `0023f57` (#447).

- **auth (#437):** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في
  التسجيل/الدخول (يكمّله ترحيل `v97_user_self_with_check.sql`).
- **الصور (#438/#439):** تفعيل صور Sentinel-2 الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة)؛
  خادم SAM2 على GPU كـopt-in خلف `profile=gpu` (503 صادق بدونه).
- **dev-proxy (#440/#442):** توحيد وكيل تطوير Vite مع بوّابة nginx (v9) — يُصلح `npm run dev` +
  رؤية تشخيصيّة (offline/معالجة الصور).
- **QA الخرائط (#441):** سويت Playwright لبوّابة جودة MapLibre/WebGL (9 خطوات) + وظيفة CI.
- **الحقول الذرّيّة (#443):** دمج/انقسام الحقول عبر نقطتَي backend ذرّيّتين
  ([`fields.py`](../services/sahool-platform/api/routers/fields.py)) — سدّ خطر البيانات الثلاثيّة؛
  اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../tests_v9/test_fields_merge_split_atomic.py).
- **تكافؤ الموبايل (#444/#445/#446/#447):** مسار سلسلة NDVI (404)، مصدر المؤشّرات الصحيح + إدارة
  المزارع، ربط أقسام مساحة العمل بالخلفيّة، السمة الداكنة الرسميّة (`AppTheme.dark`).
- **الـbrain:** إنشاء `sahool-brain/` — هذا الـvault (README/index/hot/log/dashboard +
  architecture/schema/gaps/decisions/agronomy) + قسم «الدماغ المعرفيّ» في
  [`../CLAUDE.md`](../CLAUDE.md).
