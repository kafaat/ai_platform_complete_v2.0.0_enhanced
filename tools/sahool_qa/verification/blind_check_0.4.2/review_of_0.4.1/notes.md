# blind_041 checker notes

How I solved it: everything computed in `work/solve.py`. Areas come from the drawn GeoJSON on WGS84, using ellipsoidal equal-area maps (LAEA, plus an authalic-sphere check; the two agree to under 1 mm²). Area per field: pivot_1 504,795 m², pivot_2 504,792, marib_pivot 384,535, marib_1 134,965, tihama_pivot 282,566, tihama_1 209,988, tihama_2 113,088, flood 100,005. Every polygon is valid. A spherical area (R=6371008.8) differs by about 0.35%, which flips no item.

Result: 62 answered, 20 of them with the abstain option.

## Ambiguous or under-specified rule text

1. **Refill flow window: "تدفق البئر من فرق عداد الماء وفرق عداد ساعاتها خلال 7 أيام حتى اليوم المسؤول عنه"** (sq-e61e414056ea). There are two readings:
   - reading(D) − reading(D−7), the same end-of-day convention as the depth rule.
   - reading(D) − reading(D−6), i.e. "7 dated rows".

   In sq-e61e414056ea, P1B last ran on 01-13. Under the first reading, P1B has 9 h and 1170 m³, so Q=130 m³/h, pump_days=11.7 and the answer is د (>5). Under the second reading, P1B hours are flat, so the flow is unknown and the answer is هـ (abstain). I chose د. The rule should say "من نهاية اليوم D−7".
2. **θ0 from a single 30 cm probe, while Zr = 1 m.** The rule says "θ0 متوسط رطوبة حجمية للمنطقة الجذرية", but every stress/refill item supplies only `probe-30cm`. A strict agent could reject that as not a root-zone average and abstain on all 26 balance items. I accepted it, because only the unit is named as a rejection reason.
3. **Time of the moisture reading is not stated.** I took Dr0 as the end-of-day state and started the balance the next day, as "من اليوم التالي لقراءة الرطوبة" implies. Starting the balance on the moisture day itself changes no answer; I checked this.
4. **p in `Ks_end` and RAW at the end of the day.** The rule does not say which day's p to use; I used the target day's p. Using a fixed p_table=0.55 changes no answer; I checked this.
5. **"آخر قراءة صالحة"**: the rule never defines "valid". The only intraday case is TP1 on 07-05 (53520 at 06:00 / 54360 at 21:00). It is not a drop because it equals the previous day, so it has no effect.
6. **Range notation «أ-ب» يشمل أ ولا يشمل ب**: the letters أ and ب are also option keys, which is a minor source of confusion.
7. **Well-inventory matching is implicit.** The inventory lists `P1A` and the meters are `meter_total_P1A`, so the mapping relies on the suffix.

## Traps that look intentional (rule is clear, but a careless agent would fail)

- **Depth vs stress handling of gaps.**
  - Under the depth rule, missing P2A rows on 01-21..23 are allowed (sq-4ad26cb78901, sq-3c064c1c5e85, sq-1f408933b540 are computable).
  - Under the stress rule, the same gap makes the result unknown (sq-0fd71a31360a, sq-ef96b39fe8b1). If the gap is interpolated, the trap answers are ب and ج.
- **MP1 reset on 01-25.**
  - It voids the 01-24..01-31 and 01-10..02-07 depths, the 01-11..02-07 plan comparison, and the stress results to 01-31 and 02-07.
  - It does not void 01-31..02-07 or the refill to 01-24.
  - The drop happens on the day right after endpoint a (sq-8a9cc1fff668). Its lower bound of 30.8 mm falls in the 26-36 option.
  - For the plan item, the lower bound gives a ratio of 0.97, which is a "within ±10%" trap.
- **Shared meter T12** (sq-3f3d9a32439b, sq-7a41df82e393, sq-77750d3d87a1, sq-c955f5718df8). The traps are 272 mm (200-300), 147 mm (120-170), and "no stress".
- **No boundary** (sq-5e19125c8ada). Using the registered 18 ha gives 87.1 mm, which lands on option أ (80-100).
- **kPa moisture** (sq-478ee0acf9e9). Read as %, θ0 is above field capacity, so Dr0=0 and the trap answer is "no stress".
- **Idle well in the refill window** (sq-7b79fdecfb8c, sq-8e4e08d4159f, sq-1279fb7ebfb2, sq-c11ebcc86207, sq-a6f412c84346). ΔV=0 together with Δh=0 means the flow is unknown and the abstain option applies. It is **not** "zero flow, no finite duration", and the idle well must not be dropped.
- **Rain source.** Station data is missing on 07-20..22, so CHIRPS applies to 07-22 and 07-29 (sq-035a63c8dcb5, sq-44afe98e95d3). Station data applies to 07-15. Station has duplicate readings on 01-18 (8.4/8.2), which I averaged to 8.3.

## Options that are never correct, or barely tested

- **"لا مدة تعويض محدودة عند التدفق الصفري المقيس"** is never correct in any of the 12 refill items. No item has hours advancing while volume stays flat, so this branch of the rule is untested and the option acts only as a lure.
- **Key هـ** is never the correct answer in this set (only under the alternative window reading of sq-e61e414056ea).
- **The ET_actual cap** (`max(0, TAW − Dr_start + P + I_net)`) never binds in any trace; Dr stays at or below 112 of 140. The cap is not exercised.
- The "registered area forbidden" rule is barely tested on pivot_2: 50.5 ha is registered against 50.48 ha computed, which flips nothing.

## Leaks and elimination without data

There is no positional leak. The correct range sits at the low, middle or high slot in a mixed pattern, and the answer letters are spread across أ/ب/ج/د. Plan, stress and refill options are fixed category sets.

## Answers closest to a boundary (all still robust)

- sq-c6b15d75c5df: 1.77 pump-days against the 2-day cut.
- sq-db82fb2004be: this item is an abstain. If the reset were wrongly bridged, Dr would be 68.75 against RAW 69.36, which shows the trap value sits right on the stress boundary.
- sq-18e00ab9e53f: Ks_end 0.436 against the 0.5 cut.
- sq-135f287b53c4: ratio 1.055 against the 1.1 cut.
