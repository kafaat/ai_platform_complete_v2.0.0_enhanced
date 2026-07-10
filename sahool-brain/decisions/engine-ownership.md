# خريطة ملكيّة المحرّكات (Engine Ownership Map)

**قرار المستخدم (بعد C.1c، رسالة معماريّة صريحة):** كلّ منتج له **مالك واحد**، لا تكرار
حسابات، وكلّ محرّك يُستبدَل مستقلّاً. الحذر الأكبر: عدم إعادة إنتاج «الخدمة الضخمة»
(God Service) بإقحام منطق المحصول داخل محرّك الطقس.

## الطبقات (Intelligence Engines)

```
Satellite Intelligence → Vegetation Engine → Crop Intelligence Engine
                                                     ▲
Weather Intelligence Engine ─────────────────────────┤
Soil Intelligence Engine ────────────────────────────┤
Water Intelligence Engine ───────────────────────────┘
                                                     ▼
                                          Decision Intelligence Engine
```

## Weather Engine = مالك الطقس ومشتقّاته الجوّيّة (المصدر الوحيد)

Observations · Forecast · Historical · **ET0 · VPD · GDD (اليوميّ الخام + التراكم)** ·
Chill · Heat/Cold/Humidity stress · Wind · Rain · Solar · Cloud · Reference ET ·
Spray/Harvest/Fertilizer windows · Disease weather risk · Weather/Provider confidence.
**لا منطق محصول هنا** — الحارس `weather_engine_formula_guard` يمنع تسرّب النوى للخارج،
والملكيّة تمنع تسرّب منطق المحصول للداخل.

## Crop Twin = Crop Intelligence Engine (مالك المحصول)

**لا يحسب الطقس** — يستهلك منتجات Weather ويضيف معرفة النبات:
Phenology · Crop Stage · Root Depth · Leaf/Canopy · Biomass · Yield Projection ·
Crop Water Need · Nitrogen Demand · Stress Memory/Recovery · Scenario · Digital Twin.

**ما يُنقَل من crop code إلى Weather:** كلّ حساب جوّيّ (GDD/ET0/VPD/Solar/RH/Wind/
Chill/Heat Units). **ما يبقى:** سلوك النبات أعلاه.

## أثر ذلك على تفويض GDD (WS-C.1c)

| المستهلك | يجلب الطقس؟ | القرار |
|---|---|---|
| `gdd_track` route | لا (temps من الطلب) | ✅ مُفوَّض (073613a) — يطلب النواة من المحرّك |
| `season_simulation` route | **نعم** (fetch_historical) | ✅ مُفوَّض (5fff601) — حقن سلسلة المحرّك |
| `crop_twin` compose/decision | لا (**forecast + et0_mm من الطلب**، حاسبة offline) | ⏳ **C.2 (BFF)** — الـBFF يجلب منتجات الطقس (ET0/VPD/GDD) مرّة ويُغذّيها؛ crop_twin يستقبل GDD مُورَّداً (نظير `et0_mm` المُورَّد أصلاً) بلا فرض تبعيّة شبكة على حاسبة كانت offline |
| `gdd_phenology` kernel | — | 💤 ميت (لا مستهلك حيّ) |

**لماذا crop_twin في C.2 لا C.1c:** compose حاسبة تستقبل الطقس مُورَّداً من العميل
(`et0_mm` مثال قائم). فرض استدعاء المحرّك داخلها يحوّلها لتبعيّة-شبكة fail-closed لحساب
كان offline — والمكان الصحيح لجلب منتجات الطقس مركزيّاً هو BFF (C.2). فيبقى `gdd_day`
في `season_simulation` (يستهلكه crop_twin) على allowlist حتّى C.2.

**شرط الحذف النهائيّ:** لا retirement لأيّ نواة إرث حتّى (1) ترحيل crop_twin عبر C.2،
و(2) **قرار المالك الزراعيّ للطريقة الموحَّدة** (`simple` مقابل `modified` مقابل single-sine).

المصدر: رسالة المستخدم المعماريّة (هذه الجلسة) · `services/weather-service/{et0,vpd,gdd,vapor_pressure}.py` · `scripts/ci/weather_engine_formula_guard.py`.
