# مواصفة WATER-SALT-01 (A5) — عقد قدرة الملوحة المُعلَن

- **الحالة:** ✅ مُنفَّذة (`7b16442`) — هذه الوثيقة للسجلّ والمرجعيّة.
- **النوع:** توثيق + عقد قدرة مُعلَن · **الأثر على رياضيّات الملوحة:** صفر (عميقة وصحيحة أصلاً).
- **التنفيذ:** `services/sahool-platform/core/salinity_capability.py` · الحارس `tests/test_salinity_capability_contract.py` · الوثيقة `docs/capabilities/SALINITY_CAPABILITY.md`.

## 0 · الجوهر (القيد الحاكم)
**عقد قدرة لا يقول متى يتوقّف عن الثقة = fail-open مقنّع.** لذا العقد يُعلِن **الحدود قبل القدرة**: لا `salinity_supported: true`
عارٍ — بل قدرة مقيَّدة صريحة تقول أين تعمل، وأين تتوقّف، وماذا تفعل عند غياب المُدخل.

## 1 · الدافع
السلوك موجود وعميق (مُثبَت `file:line`) لكن **مبعثر عبر ثلاث آليّات** (بوّابة HALT · `requires_expert_review` ·
deficit `recommended=False`) وبلا عقد مُعلَن. المستهلك يجمّعها يدويّاً. A5 يوحّدها في **عقد قدرة واحد** — من «دفاع مبعثر»
إلى **ميزة مُعلَنة**.

## 2 · النطاق (توثيق + تجميع، لا تغيير منطق)
عقد قدرة يُصرّح بالسلوك القائم، مُسنَداً بمراجعه الحقيقيّة:
- `salinity_stress_ks()` — `core/engines/fao56.py:127-135` (Maas-Hoffman، FAO-56 Eq.81)
- `leaching_requirement()` — `core/engines/fao56.py:590-597` (Eq.82، مسقوف 0.5)
- تطبيق H5 — `compute_irrigation_dual:525-531` · سياسة — `irrigation_recommendation_policy.py:139-183`
- ملاءمة — `crop_suitability.py:46,105-111` (وزن 0.35) · عقوبة غلّة — `deficit_irrigation.py:81,93-96`

## 3 · شكل العقد (الحدود أوّلاً)
```yaml
salinity_capability:
  supported: true
  model: "maas_hoffman_ks + fao56_leaching_eq82"
  references: ["fao56.py:127-135", "fao56.py:590-597"]        # لا قدرة بلا مرجع
  covers:                                                      # ما يُنمذَج فعلاً (كلٌّ بمرجعه)
    - "soil-EC-driven Ks when soil_ece present"
    - "leaching when ECw + crop threshold + acceptable drainage present"
    - "EC crop suitability (weight 0.35) + deficit gate"
  limits:                                                      # ← القيد الحاسم (متى يتوقّف عن الثقة)
    - "no salinity adjustment when soil_ece absent ⇒ Ks=1.0 (H5 off-by-default) — DECLARED, not silent"
    - "leaching NOT computed without irrigation-water salinity (ECw)"
    - "leaching fraction capped at 0.5 (LR>0.5 ⇒ flagged, not applied)"
    - "no time-dynamic salt transport / no root-zone salt-accumulation model"
    - "no soil-EC field measurement ingested ⇒ capability inert for that field"
  status_enum: ["net_only","salinity_adjusted","salinity_with_leaching","blocked_for_review"]
```
مفردات الحالة = مفردات سياسة الريّ الحقيقيّة (`irrigation_recommendation_policy.py:14`) لا enum موازٍ مخترَع.

## 4 · الحُرّاس والبرهان السلبيّ (يمنع fail-open بنيويّاً)
- **حارس «القدرة تُعلِن حدودها»:** أيّ عقد `supported:true` **يحمل `limits` غير فارغة + `status_enum` + `references`**، وكلّ `covers` له مرجع `file:line`.
- **برهان سلبيّ:** عقد `supported:true, limits=()` **يُرفَض**، والحقيقيّ يُقبَل.
- بوّابات: `pytest -m unit` · ruff · CI أخضر SHA واحد.

## 5 · ما ليس
ليس: تغيير رياضيّات الملوحة · تفعيل Ks افتراضيّاً (يبقى H5 off-by-default، لكن **مُعلَناً**) · نموذج نقل ملح.
**تجميع + إعلان + حدّ صادق فقط.**
