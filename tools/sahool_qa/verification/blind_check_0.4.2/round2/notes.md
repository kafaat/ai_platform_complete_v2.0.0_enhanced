# Blind check 042b: notes

72 items solved from `questions.jsonl` alone. Code: `work/solve.py` (parser, rules) and `work/geo.py` (WGS84 area via authalic latitude with exact great-circle excess, cross-checked against an ellipsoidal LAEA projection; the two agree to within 0.001 m² on every field). Answers: `answers.json`.

Field areas (geodesic, m²): tihama_strip 31,444.2 · pivot_1 504,795.3 · pivot_2 504,792.2 · tihama_pivot 282,566.2 · marib_pivot 384,535.0 · marib_1 134,965.3 · orchard 63,016.0 · flood 100,005.4 · tihama_1 209,987.6 · tihama_2 113,088.2. All rings are closed and none self-intersects. demo_tihama_farm has no boundary.

No computed depth, ratio, Ks or pump_days value sits near a bucket edge. The nearest are a 9% margin on the depth items and pump_days 1.765 against the 2-day edge in sq-c6b15d75c5df.

## 1. Readings that change an answer

- **sq-1279fb7ebfb2 (refill, tihama_pivot, window 07-08→07-15).** The rules say «نافذة التدفق: من قراءة نهاية اليوم الذي يسبق ...» and «كل آبار الحقل خارج الخدمة بسجل حالة طوال النافذة». The status records are TP1 and TP2 = 0 from 07-09. If the window covers pumping days 07-09..07-15, every well is out of service, so the answer is **د (no finite duration)**, which I chose. If day 07-08, the start reading day with status 1, also counts as part of the window, the wells are not "out for the whole window". Hours are also flat (Δh = 0), so flow becomes unknown and the answer flips to **ب (abstain)**. The rule never says whether the start day belongs to the window. The same question for «في كل أيام النافذة» does not change sq-c11ebcc86207 or sq-a6f412c84346, because there the status is 0 on both sides.
- No other item changed its answer under any alternative reading I tried. Those readings were: last vs mean of the duplicate station rain, chirps vs station, counting or dropping a partly out-of-service well (P1B in sq-e61e414056ea gives 11.7 vs 21.9 days, both above 5), and spherical vs ellipsoidal area.

## 2. Ambiguous or under-specified text (not answer-changing here)

- **Hour/water conflict pairing.** The text «بين قراءتي نهاية يومين» does not say whether the two days must be consecutive, or how to pair readings across a gap. For example, P2A has no water reading on 01-21..01-23 while its hours keep advancing (pivot_2 items). I paired consecutive available readings, which gives 01-20→01-24; water advanced across that gap, so there is no conflict.
- **Conflict exemption days.** In «سجل حالة ... يثبت أنها خارج الخدمة في تلك الأيام», the rule does not say whether "those days" include day d1 or only d1+1..d2. No instance in the data depends on this.
- **Refill, partly out-of-service well.** The rule does not say whether such a well's measured Q still counts toward "running the wells". In sq-e61e414056ea, P1B's status is 1 on 01-13 and 0 from 01-14, so the well will not run during the refill, yet the formula counts its 130 m³/h.
- **Same meter pattern, two treatments.** Flat water with flat hours means "known zero irrigation" under the depth rule (pivot_1 P1A, 01-26→02-02: sq-02bcc1687f98 gives 0-2 mm). Under the refill rule the same pattern makes flow unknown (sq-8e4e08d4159f gives abstain). Both follow the text literally, but a solver could easily carry the depth logic into the refill item.
- **Duplicate station rain.** sq-18e00ab9e53f, sq-7f14471a79cb, sq-c6b3de759c97, sq-7b79fdecfb8c, sq-8e4e08d4159f and sq-e61e414056ea have «8.4 (23:30) / 8.2 (23:45)» on 01-18. These look like a running daily total that was corrected. The rule requires the mean (8.3), although "last valid reading" would be just as natural for a running total. The difference is 0.1 mm, so no answer changes.
- **Rain source depends on target date.** The source is re-chosen for each target date, so one field gets different histories in different items. For tihama_pivot, 07-10 rain is 14 mm (station) in the items ending 07-15 (sq-361f3c4eced8, sq-1279fb7ebfb2) but 11 mm (chirps) in the items ending on or after 07-22, because the station is missing 07-20..22. This is consistent with the rule but surprising.
- **Undefined "reasonable range".** «قيمة ضمن مداه المعقول» never gives numbers. Only the unit test (kPa) is ever triggered.
- **Undefined "period" in stress/refill.** The stress/refill rule says «تُفحص جميع قراءات العداد داخل الفترة» but never defines "الفترة". I read it as the end of the moisture day through the end of the target day.
- **Partial plan weeks.** The plan rule does not say how to handle a period that is not made of whole record-weeks. All 6 items are aligned to whole weeks.
- **Missing caveats section.** The stress/refill rule cites «(افتراض سهول؛ انظر التحفظات)», but no caveats section appears in any context.

## 3. Options that leak the answer or are never plausible

- **Refill «لا مدة تعويض محدودة …».** This option can be ruled out without any calculation in 9 of 12 items. Either the field has no well_status records (marib_pivot, pivot_2: sq-1e25025ab7a8, sq-6e5378a8657c, sq-950d55d5c31a, sq-c6b15d75c5df), or at least one well (P1A) has none (pivot_1: sq-1763acc8c6d3, sq-7b79fdecfb8c, sq-8e4e08d4159f, sq-e61e414056ea), or the only status is 1 (sq-754ea37c5b10). It can only be correct in the three tihama_pivot items with windows after 07-08.
- **Applied depth with options 0-2 / 2-4 / 4-6 mm** (sq-02bcc1687f98, sq-2b64e8152eed, sq-bdbdf489455a). Every meter is flat or missing, so 2-4 and 4-6 cannot be right under any reading. Each item reduces to "0-2 vs abstain".
- **Planted trap values.** Some distractors are exactly what you get by ignoring one rule (useful as traps, not leaks):
  - sq-16d886722aee: 132 mm → 100-150
  - sq-47035e7fea3e: 15.7 → 13-18
  - sq-543e60764cbd: 215.6 → 200-250
  - sq-d9f2d0b1ee01: 28.6 → 24-34
  - sq-119797721cd3: reset lower bound ≥139 → 110-160
  - sq-8a9cc1fff668: lower bound 30.8 → 26-36
  - sq-3f3d9a32439b: whole-T12 volume, 272 → 200-300
  - sq-7a41df82e393: 147 → 120-170
  - sq-5e19125c8ada: registered 18 ha, 87 → 80-100
  - sq-37fc8deb153e: reset lower bound ratio 0.93 → "within ±10%"
- **No position or bucket-centring leak.** Among computed depth answers, the correct bucket is ranked lowest/middle/highest 11/6/8 times.

## 4. Records a rule needs that are absent (intended abstains)

- **sq-5e19125c8ada:** no drawn boundary, only a registered area and a point.
- **sq-bdbdf489455a and sq-2582db863b2d:** no meter records and no well list.
- **sq-478ee0acf9e9:** soil_moisture_vol is recorded in kPa, so θ0 is invalid. The column name says "vol" but the unit is a tension unit, which is a contradictory record.
- **sq-0fd71a31360a and sq-ef96b39fe8b1:** P2A daily readings are missing on 01-21..23. Depth items over the same gap are still answerable from the endpoints, by «ولو غابت القراءات بينهما».
- **sq-77750d3d87a1:** there is no plan record for the week starting 07-16, and T12 is also shared with another field.
- **Reset or shared meters:** MP1 resets on 01-25 (sq-119797721cd3, sq-8a9cc1fff668, sq-37fc8deb153e, sq-0afee06d9a05, sq-db82fb2004be), and T12 is shared (sq-3f3d9a32439b, sq-7a41df82e393, sq-c955f5718df8).

## 5. Other observations

- **Registered areas disagree with drawn boundaries.** demo_tihama_2 is registered as 1200 ha against 11.3 ha drawn, and demo_pivot_2 as 50.5 ha against 50.48 ha. These are distractors only, since the rule bans registered areas.
- **Parameters match FAO-56.** I checked the stated θFC/θWP against the Table 19 midpoints (silt_loam 0.29/0.15, sandy_loam 0.23/0.11, loamy_sand 0.15/0.065, loam 0.25/0.12) and Zr/p against Table 22 (1.0 m, 0.55). All agree.
