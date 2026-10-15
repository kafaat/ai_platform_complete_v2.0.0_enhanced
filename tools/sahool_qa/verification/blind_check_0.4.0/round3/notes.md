# Blind checker 3 — notes on the water question set (88 items)

All 88 items were solved by my own code in `work/` (`rain.py`, `depth.py`, `plan.py`, `balance.py`, plus the shared `common.py` and `meters.py`). For field areas I used an exact ellipsoidal equal-area method: Lambert cylindrical equal-area on the WGS84 authalic q-function, with densified edges. A second method (the authalic sphere with the tangent formula) gives the same area to within 0.1 m² for every field. The spherical-excess formula on geodetic latitudes gives areas about 0.35% larger, and that changes no answer. The areas are:

| field | area (m²) |
|---|---|
| pivot_1 | 504,795 |
| pivot_2 | 504,792 |
| flood | 100,005 |
| marib_1 | 134,965 |
| marib_pivot | 384,535 |
| tihama_pivot | 282,566 |
| tihama_2 | 113,088 |
| tihama_1 | 209,988 |

None of my answers depends on a close call. For every numeric answer, the computed value sits at least 0.8 mm (rain) or 1.48 mm (depth) inside its bucket. The one exception is a 0.0 mm depth that lands on the lower edge of "0-2", and no other bucket competes with it. Among the status items, the Ks value nearest to the 0.5 threshold is 0.436 (sq-18e00ab9e53f). I re-ran the analysis under four alternative readings: Kc taking effect the day after its record date, the spherical area, the last reading instead of the mean, and summing duplicate rain records. Only summing duplicates changes an answer (see "Duplicate rain records" in section B).

## A. Rule text that is ambiguous, under-specified or inconsistent

**A1. Bucket edges are not defined as inclusive or exclusive (all range families).** Adjacent options share endpoints, for example «10-15 مم» and «15-20 مم». This matters only for 0.0 mm, which falls on the lower edge of «0-2 مم». That happens in four items: sq-02bcc1687f98, sq-297637e378e6, sq-2b64e8152eed and sq-e688bbe21fb6. No other bucket competes there, so these items are safe. Still, the rule should say "lo ≤ x < hi".

**A2. «إذا نزلت قراءة عن سابقتها … فالحجم للفترة غير معروف» does not define the scope of «للفترة» (water.applied_depth).** I treated only drops between day a and day b as making the volume unknown.
- sq-dfbfc43d3375 (marib pivot, 01-31 → 02-07) shows only post-reset MP1 readings (9132 → 19772). The 01-25 reset is invisible in that item, so it is computed as 35.68 mm (أ).
- sq-10b76e6b5d36 (01-17 → 01-24) ends before the reset and is computed as 35.68 mm (أ).
- An agent that knows from other items that MP1 was reset or replaced could argue the meter is unreliable and abstain. The rule does not settle this.

**A3. «آخر قراءة صالحة» does not define what makes a reading valid.** Only the multi-reading cell «53520 (06:00) / 54360 (21:00)» (TP1, 07-05) is affected. It is an interior day in the depth items, and taking the last reading gives a consistent daily series in the balance items, so no answer depends on it.

**A4. The rules for meter gaps differ between families. This looks deliberate, but it is easy to carry over the wrong rule.**
- The depth and plan rules say «ولو غابت القراءات بينهما» (a gap is fine if both endpoints exist).
- The balance rule says «يوم غابت فيه قراءة عداد … حتى لو كان مجموع العداد التراكمي عبر الفجوة معروفاً … غير معروفة» (a gap makes the result unknown).
- The same P2A gap (01-21..01-23) is therefore computed in sq-3c064c1c5e85, sq-4ad26cb78901 and sq-1f408933b540, but must be abstained in sq-0fd71a31360a and sq-ef96b39fe8b1.

**A5. plan_vs_measured does not say what to do with a plan week that only partly overlaps the asked window.** The options would be to pro-rate it or to treat the plan as unknown. The rule also does not cover overlapping plan records. Neither case occurs: in all six items the plan records fall exactly on d1, d1+7, d1+14 and d1+21. The rule is untested on misaligned windows.

**A6. rain_corroboration: «ولا يتأكد إذا سجّلت المصادر المستقلة المكتملة كلها أقل من ذلك».** This says "not confirmed" even when another independent source is incomplete and might have recorded the rain. A stricter reading would answer "cannot judge" in that case. No item has a mix of complete and incomplete independent sources, so the gap is untested.

**A7. Refill rule and balance unknowns.** «قاعدة التعويض» does not restate that the balance's unknown conditions also apply. I assumed they carry over. No refill item turns on this: all five refill abstentions come from flow, not from the balance.

**A8. The refill rule makes an idle well's flow unknown and forbids dropping that well: «عداد ساعات لم يتقدم … غير معروف … لا يُسقط البئر».**
- The rule is explicit, so the answers are unambiguous. The consequence is counter-intuitive, though: the platform refuses exactly when the wells have been off and the deficit is growing, even though the wells' flow is known from earlier weeks (P1A 150, P1B 130, TP1 120, TP2 100 m³/h).
- This decides 5 of the 12 refill items, all of which should be abstained: sq-7b79fdecfb8c (only P1B idle), sq-8e4e08d4159f, sq-1279fb7ebfb2, sq-a6f412c84346 and sq-c11ebcc86207.
- An agent that drops the idle well, or uses the previous week's flow, would answer ">5" in every one of these.

**A9. Kc effective date.** «ساري من تاريخ سجله» is read as inclusive. The exclusive reading changes no answer.

## B. Traps and distractors a careful agent could fall into

These look intended; the trap value lands inside a numeric option in each case.

**Registered area used instead of drawn boundaries**
- sq-5e19125c8ada has no boundary and a registered area of 18 ha. That would give 15,680 m³ / 18 ha = 87.1 mm, which is option أ «80-100 مم». The correct answer is ج (abstain).
- sq-3f3d9a32439b has a registered area of «1200 هكتار» against a drawn 11.31 ha (a 100× inconsistency), and its meter is shared. The drawn-area depth would be 272 mm, option ج «200-300». The correct answer is أ (abstain).
- sq-7a41df82e393 has the same shared meter T12. The drawn-area depth would be 146.7 mm, option ج «120-170». The correct answer is ب (abstain).

**Lower bound after a meter reset**
- sq-119797721cd3: the lower bound is about 53,360 m³, or 138.8 mm, option ج «110-160». The correct answer is أ (abstain).
- sq-8a9cc1fff668: the lower bound is about 31.7 mm, option أ «26-36». The correct answer is ج (abstain).
- sq-37fc8deb153e: the lower bound of 138.8 mm against a plan of 144 mm gives a ratio of 0.96, option أ «ضمن ±10%». The correct answer is ج (abstain).

**Missing rain day counted as dry**
- sq-c96b4b3df0a6: the only rain days (01-17/18) are «—» in the station series. The partial sum of 0 points to «0-2». The correct answer is د (abstain).
- sq-008b6ed23034: three station days are missing. The partial sum of 14 points to «11-16». The correct answer is أ (abstain).

**Same-origin corroboration**
- In sq-03cc0e240038, sq-105b705813dd and sq-1696982bd259 the field has no station column at all. CHIRPS-v3 rnl agrees with the event (7.5, 9.1 and 11 mm), but its daily timing comes from ERA5, which is the same origin as the event. These items must be abstained, not answered as "confirmed".
- In sq-dc60d50a7422 and sq-e8af394046ca the station is incomplete in the event window, so these are also abstained.

**Duplicate rain records**
- Station 01-18 has two records: «8.4 (23:30) / 8.2 (23:45)». The mean is 8.3; the last reading (8.2) gives the same bucket.
- Summing them to 16.6 mm flips sq-18e00ab9e53f from severe (Ks 0.436, option د) to moderate (Ks 0.507, option أ).
- In sq-70568f4515bb the sum (16.6) falls outside every option.

**Non-volumetric moisture unit**
- sq-478ee0acf9e9 reports moisture in kPa (28). Misread as 28%, it gives θ0 = 0.28, above FC (0.25), so Dr0 = 0 and the answer would be no stress (ج). The correct answer is أ (abstain).

**Balance must stop at an unknown day**
- sq-0afee06d9a05 and sq-db82fb2004be: MP1 resets on 01-25, so the correct answer is abstain (أ for both).
- sq-0fd71a31360a and sq-ef96b39fe8b1: the P2A gap makes the result unknown (see A4).
- sq-2582db863b2d: the flood basin has no meter. Treating irrigation as 0 gives no stress (د); the correct answer is ب (abstain).
- sq-c955f5718df8: the meter is shared. Computing anyway gives no stress (أ); the correct answer is ج (abstain).

**Rain-source selection**
- For the Tihama pivot, the station series is missing 07-20..07-22. Targets on 07-22 and 07-29 must therefore use CHIRPS for every day of the run, including 07-10, where CHIRPS has 11 mm and the station 14.
- Mixing sources day by day (station where present, CHIRPS otherwise) changes no answer: sq-035a63c8dcb5 stays moderate and sq-44afe98e95d3 stays severe.

**Dr0 above RAW at the start**
- In the Marib pivot items, θ0 = 13% gives Dr0 = 100 mm against RAW ≈ 75, so Ks < 1 from the first day. An agent that assumes Ks = 1 at the start will over-deplete.
- The answers still come out moderate in sq-55ef41ddd20c and sq-de5eb272251c (Ks 0.83–0.85).

## C. Option leakage and items answerable without the data

**C1. Bucket position.** In applied_depth the correct numeric bucket is the lowest of the three numeric options in 13 of 23 items, the middle one in 3 and the highest in 7. This is a mild skew, partly from the four 0-mm items, whose options are always 0-2, 2-4 and 4-6. The bias is weak and not exploitable on its own.

**C2. Plan items.** The ratio options use fixed labels with thresholds that match the rule (0.9 and 1.1). Nothing leaks.

**C3. Status, refill and corroboration options.** These use a fixed set of 3–4 labels, and the abstain option is worded identically every time with a varying position. Nothing leaks. The abstain rate is high: 27 of 88 answers (6 depth, 2 plan, 5 corroboration, 2 rain_total, 5 refill, 7 status). A policy of always abstaining would score about 31%.

**C4. Repeated values.** Several items repeat a value across different windows: pivot_2 has 27.18 mm in four separate 7-day windows, and marib_1 has 28.01 mm in four. Getting one right effectively gets the others right, so these items are not independent tests.

## D. Answer summary by family

| family | items | abstain | other answers |
|---|---|---|---|
| rain_total | 11 | 2 (missing station days) | 9 numeric |
| rain_corroboration | 11 | 5 | 4 confirmed, 2 not confirmed |
| applied_depth | 29 | 6 (no meter; 2 reset; 2 shared meter; no boundary) | 23 numeric |
| plan_vs_measured | 6 | 2 (reset; plan week missing + shared meter) | 2 below plan, 1 above, 1 within |
| stress_status | 19 | 7 | 6 no stress, 4 moderate, 2 severe |
| refill_feasibility | 12 | 5 (all idle-well flow) | 2 ≤2 days, 1 >2 and ≤5 days, 4 >5 days |
