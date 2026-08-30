# IRRIGATION-CONTRACTS v1.1-errata2 — المرجع الملزم

**الحالة:** FOUNDATION — نص مراجَع ملزم، بلا كود / اختبار / تشغيل حي.
**السلسلة:** v1.1 (العقود الأربعة) ← errata (الشروط الثمانية) ← errata2 (خمسة تشديدات E1–E5).
**تاريخ الاعتماد:** 2026-08-24.

```json
"capability_hex_status": {
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

> هذا الختم إلزامي في رأس كل عقد من العقود الأربعة، ولا يتغير إلا بدليل تنفيذي قابل للتحقق (ملف + sha + اختبار + إثبات حي)، وليس بتصريح.

---

## القسم 0 — قواعد عابرة لكل العقود

### 0.1 البصمة الحتمية (الشرط 1 + E1)

يُحسب أي `*_digest` في هذه العقود حصريًا عبر:

- JSON canonicalization حتمي:
  - ترتيب المفاتيح أبجديًا في كل مستوى.
  - ترميز UTF-8.
  - **تمثيل الأعداد: IEEE-754 shortest round-trip، بلا أصفار زائدة؛ يُرفض NaN وInfinity.** *(E1)*
  - escaping نصي محدد: الحد الأدنى الإلزامي فقط (`\"` `\\` وأحرف التحكم U+0000–U+001F). *(E1)*
  - لا يدخل في الحمولة المُبصَمة: `stage_id`، `timestamp`، والحقل الحامل للبصمة نفسه.
- الخوارزمية: `sha256(canonical_json_bytes)`.
- يُرفق مع كل بصمة: `canonicalization_version` و`digest_algorithm`.

بدون هذا التعريف الكامل، البصمات غير قابلة لإعادة التحقق من طرف ثالث.

### 0.2 نموذج السلسلة (الشرط 2 + E2)

- السلسلة خطية، وليست DAG. عند الحاجة إلى DAG يُرفع الإصدار إلى v2 بقواعد تحقق منفصلة.
- `sequence` ترتيب عالمي داخل `chain_id` واحد.
- **تسلسل متصل صارم: n ثم n+1. يُرفض أي تكرار أو قفز، بلا استثناء «مبرر».** *(E2)*
- المرحلة المتخطاة تُسجَّل كمرحلة كاملة بـ `status: "skipped"`، لا كغياب في sequence. *(E2)*
- `PredictionError`: في النموذج الخطي يكون `parent_stage_id` = آخر مرحلة مكتملة، وتُضاف `related_stage_ids` للمراجع السببية الأخرى (قد تشمل `Prediction` و`ObservedOutcome` معًا).

### 0.3 سياسة تعاقد الإصدارات (الشرط 7 + E4 + E5)

قسم إلزامي في رأس كل عقد:

| الحقل | القاعدة |
|---|---|
| `schema_id` | ثابت: `sahool.<name>/v1.1` — لا يتغير بتعديل تحريري. *(E5)* |
| `contract_revision` | حقل مستقل يحمل الإصدار التحريري: `v1.1-errata2`. *(E5)* |
| `required_fields` | قائمة الحقول الإلزامية. |
| `nullability_rules` | تحديد الحقول القابلة لـ null صراحة. |
| `unknown_fields_behavior` | الأساسي: `reject`. |
| `backward_compatibility` | نطاق التوافق مع v1.1. |
| `version_bump_policy` | **كاسر (حذف/إعادة معنى حقل، تشديد nullability) → major؛ إضافة حقل اختياري فقط → minor؛ إضافة `decision_domain` → عقد جديد.** *(E4)* |

### 0.4 القاعدة الذهبية (ثابت معماري)

```
AI / Adaptive Model → parameter correction
        ↓
MPC → Policy/Safety Gate → Hydraulic Feasibility → Decision Service → Authorized Execution
```

ممنوع قطعيًا: AI → actuator، RL → actuator، Adaptive Model → actuator، Digital Twin → actuator.

---
---

## العقد 1 — IrrigationStateSnapshot v1.1

طبقة تجميع read-only، لا مصدر حقيقة بديل. تجمع المراجع والبصمات للحالات القياسية الموجودة وتضيف حقول القرار والأهلية.

```json
{
  "schema": "sahool.irrigation-state-snapshot/v1.1",
  "contract_revision": "v1.1-errata2",
  "snapshot_id": "<ulid>",
  "field_id": "<string>",
  "timestamp": "<iso8601-utc>",
  "canonical_state_refs": {
    "water_state_digest": "<sha256>",
    "weather_state_digest": "<sha256>",
    "soil_state_digest": "<sha256>",
    "crop_state_digest": "<sha256>",
    "irrigation_state_digest": "<sha256>"
  },
  "observation_metadata": {
    "observed_at": "<iso8601>",
    "ingested_at": "<iso8601>",
    "freshness_seconds": "<int>"
  },
  "weather": {
    "air_temperature_c": "<float>", "relative_humidity_pct": "<float>",
    "wind_speed_m_s": "<float>", "radiation_w_m2": "<float>",
    "vpd_kpa": "<float>", "et0_mm_day": "<float>",
    "forecast": {
      "source": "<string>", "issued_at": "<iso8601>",
      "valid_from": "<iso8601>", "valid_to": "<iso8601>",
      "horizon_hours": "<int>",
      "temperature_c": ["<float>"], "radiation_w_m2": ["<float>"],
      "rain_mm": ["<float>"], "vpd_kpa": ["<float>"],
      "confidence": "<float 0..1>"
    },
    "quality": "verified|degraded|unknown",
    "decision_eligible": true,
    "reason_if_ineligible": null
  },
  "soil": {
    "root_zone_profile_id": "<string>",
    "root_zone_depth_m": "<float>",
    "taw_mm": "<float>", "raw_mm": "<float>",
    "layers": [
      { "depth_cm": 10, "value_m3_m3": 0.18, "sensor_id": "<string>",
        "quality": "verified|degraded|unknown",
        "observed_at": "<iso8601>", "freshness_seconds": "<int>" }
    ],
    "field_capacity_m3_m3": 0.30,
    "wilting_point_m3_m3": 0.12,
    "provenance": {
      "soil_digest": "<sha256>", "soil_profile_id": "<string>",
      "lab_evidence_id": "<string|null>",
      "quality": "verified|degraded|unknown", "freshness_seconds": "<int>"
    },
    "decision_eligible": true,
    "reason_if_ineligible": null
  },
  "water": {
    "depletion_mm": "<float>", "source": "<string>",
    "source_water_ec_ds_m": "<float>", "source_water_ph": "<float>",
    "salinity_gate_status": "PASS|WARN|REJECT",
    "salinity_gate_ref": "<gate_decision_id>",
    "quality": "verified|degraded|unknown",
    "decision_eligible": true,
    "reason_if_ineligible": null,
    "provenance": {
      "water_digest": "<sha256>", "water_ledger_id": "<string|null>",
      "source_quality_evidence_id": "<string|null>", "freshness_seconds": "<int>"
    }
  },
  "crop": {
    "crop": "<string>", "cultivar": "<string>", "growth_stage": "<string>",
    "kc": "<float>", "ks": "<float>",
    "stress_state": "none|mild|moderate|severe",
    "quality": "verified|degraded|unknown",
    "decision_eligible": true,
    "reason_if_ineligible": null,
    "provenance": {
      "crop_digest": "<sha256>", "crop_intelligence_id": "<string|null>",
      "ndvi_source": "<string|null>", "freshness_seconds": "<int>"
    }
  },
  "irrigation": {
    "recent_volume_l": ["<float>"], "recent_duration_min": ["<float>"],
    "delivery_efficiency_pct": "<float>", "drainage_ratio": "<float>",
    "drain_ec_ds_m": "<float>", "drain_ph": "<float>",
    "quality": "verified|degraded|unknown",
    "decision_eligible": true,
    "reason_if_ineligible": null,
    "provenance": {
      "irrigation_digest": "<sha256>",
      "execution_evidence_id": "<string|null>", "freshness_seconds": "<int>"
    }
  },
  "decision_eligibility": { "overall": true, "blocking_reasons": [] },
  "confidence": {
    "overall": "<float 0..1>", "weather": "<float 0..1>",
    "soil": "<float 0..1>", "water": "<float 0..1>",
    "crop": "<float 0..1>", "irrigation": "<float 0..1>",
    "calculation": "<string>"
  },
  "provenance": { "snapshot_digest": "<sha256>" }
}
```

### قواعد إلزامية على هذا العقد

1. **تجميع لا مصدر منافس:** `canonical_state_refs` بدل إعادة حساب الحالة.
2. **freshness سياسة لا حكم (الشرط 3):** `freshness_seconds` قياس فقط. طبقة التجميع تنقل العمر ولا تقرر قِدَمه. حدود staleness تعيش في سياسة القرار وتظهر آثارها في `decision_eligibility.blocking_reasons`. **يُمنع أي `if freshness > X` داخل IrrigationStateSnapshot.**
3. **salinity_gate_status مخرَج بوابة (الشرط 4 + E3):** تُنقل نتيجة `evaluate_water_salinity_gate` من البوابة ولا تُعاد حسابها. `salinity_gate_ref` إلزامي. **عند غيابه ترفض طبقة التجميع إنتاج الـ snapshot.** وسم `SALINITY_GATE_PROVENANCE_MISSING` مخصص حصرًا للمستهلكين الذين يقرأون snapshots قديمة سبقت هذه الـ errata.
4. **فصل الجودة عن الأهلية:** `quality` وصف للدليل؛ `decision_eligible` حكم بوابة، ومع كل `false` يجب `reason_if_ineligible`.
5. **وحدات VWC:** `value_m3_m3` فقط.
6. **طبقات الجذر:** `root_zone_profile_id` + طبقات حسّية؛ الحساب الهيدروليكي من الملف الحاكم لا من العقد.

---

## العقد 2 — EvidenceChain v1.1

تسلسل Merkle-like سببي خطي: `parent_digest` + `stage_digest` + `sequence` للكشف عن الحذف/الاستبدال/الإدراج خارج الترتيب. البصمات وفق القسم 0.1، والتسلسل وفق 0.2.

### المخطط العام للمرحلة

```json
{
  "chain_id": "<ulid>",
  "correlation_id": "<ulid>",
  "stage_id": "<ulid>",
  "parent_stage_id": "<ulid|null>",
  "parent_digest": "<sha256|null>",
  "stage_digest": "<sha256>",
  "canonicalization_version": "<string>",
  "digest_algorithm": "sha256",
  "sequence": 4,
  "stage": "Prediction",
  "related_stage_ids": [],
  "timestamp": "<iso8601>",
  "status": "created|processing|succeeded|failed|skipped"
}
```

### ترتيب المراحل الملزم

`CanonicalState (seq 0) → Prediction (seq 1) → DecisionCandidate (seq 2) → HydraulicFeasibility (seq 3) → Execution → AsApplied → ObservedOutcome → PredictionError → ModelCalibrationCandidate`

- الترتيب السببي: `prediction_id` **قبل** `decision_id` **قبل** `execution_id`.
- `Prediction.parent_digest` = `state_digest` الخاص بـ CanonicalState.
- كل مرحلة لاحقة تحمل `parent_digest` = `stage_digest` للمرحلة السابقة.

### أمثلة المراحل

CanonicalState (seq 0, الجذر):

```json
{
  "chain_id": "<ulid>", "correlation_id": "<ulid>",
  "stage_id": "<ulid>",
  "parent_stage_id": null, "parent_digest": null,
  "stage_digest": "<sha256 of stage content>",
  "sequence": 0, "stage": "CanonicalState",
  "state_snapshot_id": "<snapshot_id>", "state_digest": "<sha256>",
  "timestamp": "<iso8601>", "status": "succeeded"
}
```

Prediction (seq 1):

```json
{
  "chain_id": "<ulid>", "correlation_id": "<ulid>",
  "stage_id": "<ulid>",
  "parent_stage_id": "<stage_id_of_CanonicalState>",
  "parent_digest": "<state_digest>",
  "stage_digest": "<sha256 of prediction content>",
  "sequence": 1, "stage": "Prediction",
  "prediction_id": "<ulid>", "model_version": "<string>",
  "input_digest": "<state_digest>",
  "predicted": {
    "required_volume_l": 18.4,
    "recommended_window_start": "<iso8601>",
    "recommended_window_end": "<iso8601>",
    "predicted_vwc_delta": 1.8,
    "confidence": 0.87,
    "explanation": "ET0=5.2 mm/day, Kc=1.1, VWC_30=0.18 => demand"
  },
  "timestamp": "<iso8601>", "status": "succeeded"
}
```

DecisionCandidate (seq 2) — مجال الري فقط:

```json
{
  "chain_id": "<ulid>", "correlation_id": "<ulid>",
  "stage_id": "<ulid>",
  "parent_stage_id": "<stage_id_of_Prediction>",
  "parent_digest": "<prediction_stage_digest>",
  "stage_digest": "<sha256 of candidate content>",
  "sequence": 2, "stage": "DecisionCandidate",
  "decision_id": "<ulid>", "prediction_id": "<prediction_id>",
  "decision_domains": ["irrigation"],
  "candidate": {
    "irrigation_volume_l": 18.4,
    "recommended_window_start": "<iso8601>",
    "recommended_window_end": "<iso8601>"
  },
  "policy_review": {
    "requires_human_review": true,
    "execution_allowed": false,
    "salinity_gate": "PASS"
  },
  "timestamp": "<iso8601>", "status": "succeeded"
}
```

> لا يحتوي `candidate` على `nutrient_recipe`؛ مجال القرار `irrigation` فقط حتى تكتمل FertigationState (الشرط 6).

HydraulicFeasibility (seq 3):

```json
{
  "chain_id": "<ulid>", "correlation_id": "<ulid>",
  "stage_id": "<ulid>",
  "parent_stage_id": "<stage_id_of_DecisionCandidate>",
  "parent_digest": "<decision_candidate_stage_digest>",
  "stage_digest": "<sha256 of feasibility content>",
  "sequence": 3, "stage": "HydraulicFeasibility",
  "decision_id": "<decision_id>",
  "feasibility": {
    "result": "feasible|infeasible|partially_feasible",
    "constraints": {
      "available_flow_l_s": 12.0, "required_flow_l_s": 9.5,
      "pressure_bar": 3.1, "reservations": ["<reservation_id>"]
    },
    "checked_network_model_version": "<string>"
  },
  "timestamp": "<iso8601>", "status": "succeeded"
}
```

### تدريج C6 حسب نطاق القدرة

| المستوى | الشرط |
|---|---|
| C6-LIVE-OBSERVED | إثبات قراءة حقيقية لحالة canonical حية |
| C6-LIVE-DECISION | إثبات إنتاج DecisionCandidate حقيقي من مدخلات حية، مع المرور بالبوابة |
| C6-LIVE-EXECUTED | إثبات تنفيذ حقيقي + as-applied + observed outcome |

لا يُشترط `execution_id` لكل قدرة؛ كل قدرة تُثبَت حسب نطاقها. MPC يُثبَت بـ C6-LIVE-DECISION (لا ينفّذ actuator بنيويًا)، وIrrigationExecution بـ C6-LIVE-EXECUTED.

---

## العقد 3 — FertigationState v1.1

نموذج كيميائي لا عتبة EC. فصل كامل بين EC/pH والتركيزات العنصرية، مع نموذج كيمياء مياه ومحاكاة للجرعة قبل الحقن.

```json
{
  "schema": "sahool.fertigation-state/v1.1",
  "contract_revision": "v1.1-errata2",
  "fertigation_state_id": "<ulid>",
  "field_id": "<string>",
  "timestamp": "<iso8601>",
  "crop_stage": "<string>",
  "input_water": {
    "ec_ds_m": "<float>", "ph": "<float>",
    "alkalinity_mg_l_caco3": "<float>", "bicarbonate_mg_l": "<float>",
    "temperature_c": "<float>",
    "source_water_chemistry_id": "<string|null>"
  },
  "nutrient_recipe": {
    "recipe_id": "<string>",
    "concentrations_mg_l": {
      "N": "<float>", "P": "<float>", "K": "<float>",
      "Ca": "<float>", "Mg": "<float>", "S": "<float>",
      "micronutrients": "<object>"
    },
    "calibrated": false
  },
  "rootzone": {
    "substrate_ec_ds_m": "<float>", "substrate_ph": "<float>",
    "drain_ec_ds_m": "<float>", "drain_ph": "<float>",
    "drainage_ratio": "<float>", "vwc_m3_m3": "<float>",
    "quality": "verified|degraded|unknown",
    "observed_at": "<iso8601>", "freshness_seconds": "<int>"
  },
  "crop_uptake_estimate": {
    "N_mg": "<float>", "P_mg": "<float>", "K_mg": "<float>",
    "model_version": "<string>", "calibrated": false
  },
  "provenance": {
    "fertigation_state_digest": "<sha256>",
    "source_ids": ["<water_quality_id>", "<drain_measurement_id>", "<recipe_id>"],
    "quality": "verified|degraded|unknown", "freshness_seconds": "<int>"
  },
  "decision_eligibility": {
    "overall": false,
    "blocking_reasons": ["FERTIGATION_MODEL_NOT_CALIBRATED"]
  }
}
```

### نموذج الجرعة الحمضية (الشرط 5 — pseudocode، C2 = ✗)

```python
def calculate_acid_dose(
    *,
    alkalinity_mg_l_caco3: float,
    bicarbonate_mg_l: float,
    ph_current: float,
    ph_target: float,
    tank_volume_l: float,
    acid_normality: float,
    acid_density_g_ml: float,
    temperature_c: float,
    mixing_volume_l: float,
    mixing_order: str,  # يجب أن يصبح enum مغلقًا
    max_injection_rate_ml_s: float,
    max_single_step_delta_ph: float,
) -> dict:
    # 1) حساب تقديري للجرعة
    # 2) محاكاة predicted_pH_after_injection   ← يتطلب نموذج اتزان كربونات/معايرة قلوية مرجعيًا محددًا
    # 3) التحقق من rate limiter و delta pH
    # 4) إرجاع الجرعة الآمنة مع predicted_pH_after_injection
    ...
```

**حتى يكتمل ما يلي تبقى FertigationState عند FOUNDATION / PARTIAL مع C2 = ✗، ولا تُمرَّر أي دالة جرعة إلى Decision Service:**

- نموذج اتزان كربونات/معايرة قلوية مرجعي محدد.
- `mixing_order` بقيم enum مغلق.
- تحقق وحدات كامل.
- اختبارات مرجعية.

**الخطوات الإلزامية:** `calculate → simulate → safety gate → inject → measure → reconcile`

**ممنوع:** `EC > X → fertilizer -20%`، و`ΔpH → acid volume` بدون alkalinity/bicarbonate.

**مقاييس C4 الخاصة:** `drain_ec_trend`، `drain_ph_trend`، `drainage_ratio_trend`، `nutrient_uptake_residual`، `salt_balance_error` — وتُنتج `FertigationOutcome → FertigationModelCalibrationCandidate` محكومًا.

---

## العقد 4 — DecisionEvidenceEnvelope v1.1

الحد الفاصل بين الذكاء الزراعي وخدمة القرار.

```json
{
  "schema": "sahool.decision-evidence-envelope/v1.1",
  "contract_revision": "v1.1-errata2",
  "decision_id": "<ulid>",
  "correlation_id": "<ulid>",
  "state_snapshot_id": "<snapshot_id>",
  "prediction_id": "<prediction_id>",
  "model_version": "<string>",
  "policy_version": "<string>",
  "input_digest": "<state_digest>",
  "candidate_digest": "<sha256 of candidate>",
  "hydraulic_feasibility_digest": "<sha256 of feasibility result>",
  "execution_allowed": false,
  "requires_human_review": true,
  "decision_domains": ["irrigation"],
  "fertigation_candidate_id": null
}
```

- `execution_allowed` و`requires_human_review` يأتيان من Policy/Safety Gate حصريًا.
- **حوكمة المجالات (الشرط 6):** `decision_domains` enum مغلق حاليًا بقيمة وحيدة: `["irrigation"]`. لا يُضاف `fertigation` إلا بعد: اكتمال C1–C5 لـ FertigationState، وتحقق C6-LIVE-DECISION لها، وقرار مالك صريح. `fertigation_candidate_id` يبقى `null` حتى ذلك الحين. أي إضافة مجال جديد = عقد جديد، لا تعديل صامت.

---

## أثر الإصدار والخطوات المشروعة

- تبقى العقود الأربعة مرجعًا تصميميًا لا تنفيذيًا، بختم FOUNDATION في رأس كل منها.
- الخطوة التالية المشروعة الوحيدة:
  1. تحويل العقود إلى JSON Schema متوافقة مع الشروط الثمانية + E1–E5.
  2. ربطها بالموجود الفعلي فقط: CanonicalWaterState، water_ledger، check_network_feasibility خلف `FEATURE_IRRIGATION_NETWORK`.
  3. أي بناء C1–C2 يكون فوق ما أثبتته Gap Matrix حصرًا.
- يسري بند: **لا force-push فوق عمل آخر دون إثبات ancestry/semantic equivalence.**
- يسري بند: **هذه العقود لا تُستخدم لتجاوز أو إعادة تفسير أي من بوابات D09–D13.**