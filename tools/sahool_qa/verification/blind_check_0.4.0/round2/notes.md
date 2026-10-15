# Blind check notes: water question set (68 items)

Method: every item was solved in code under `work/`: `parse.py`, `geo.py`, `solve.py`, `balance.py` and `solve2.py`. Field areas come from the GeoJSON in each item and are geodesic on WGS84. pyproj and geographiclib are not installed, so I used two methods:
- an authalic-sphere spherical-excess area;
- a local ellipsoidal-radius planar check.

The two methods agree to within 0.2 m². Results:

| Field | Area (m²) |
|---|---|
| pivot_1 | 504,795 |
| pivot_2 | 504,792 |
| flood | 100,005 |
| marib_pivot | 384,535 |
| marib_1 | 134,965 |
| tihama_1 | 209,988 |
| tihama_2 | 113,088 |
| tihama_pivot | 282,566 |

All drawn polygons pass the validity checks: closed ring, no self-intersection, coordinates in range.

## 1. Rule text that is ambiguous, under-specified or contradictory

1. **Several rain records on one day, outside the rain-total family.** The pivot_1 station record for 2026-01-18 is `8.4 (23:30) / 8.2 (23:45)`.
   - The rain-total rule handles this case: «عند تعدد السجلات في اليوم تُستخدم قيمتها اليومية المتوسطة».
   - The FAO-56 balance rule and the corroboration rule say nothing about it.
   - The possible readings are: mean 8.3; last 8.2 (by analogy with «قراءة اليوم = آخر قراءة صالحة»); sum 16.6; or "conflicting records make the day invalid".
   - **sq-18e00ab9e53f (stress, pivot_1, 02-02)** changes with the reading:
     - mean, last or max → severe (Ks 0.436);
     - sum → moderate (Ks 0.507);
     - "day invalid" → station incomplete → fall back to chirps → severe, but with a thin margin (Ks 0.489).
   - **sq-c36c2341e655 (corroboration)**: under "day invalid", the station is incomplete and the answer becomes abstain instead of "confirmed".
   - The other affected items (sq-7f14471a79cb, sq-c6b3de759c97, and refill sq-e61e414056ea / sq-7b79fdecfb8c / sq-8e4e08d4159f) do not change answer.
   - Separately, the phrase «قيمتها اليومية المتوسطة» reads awkwardly: it could mean "the source's average daily value". «متوسط سجلاتها» would be clearer.

2. **«يوم … بلا قراءة لأيٍّ من عدادات الحقل»** has two grammatical readings: "any one meter has no reading" or "no meter has a reading".
   - sq-0fd71a31360a and sq-ef96b39fe8b1 depend on it: P2A is missing on 01-21..23 while P2B is present.
   - The clause «حتى لو كان مجموع العداد التراكمي عبر الفجوة معروفاً» points to the "any one" reading, which gives abstain.
   - Suggested wording: «إذا غابت قراءة أيّ عداد».

3. **The rain source depends on the target day.** The rule takes «أول مصدر سجلاته مكتملة … حتى اليوم المسؤول عنه».
   - For tihama_pivot, the deficit for the same days through 07-15 is computed from the station in sq-361f3c4eced8 (14 mm on 07-10), but from chirps in sq-035a63c8dcb5 and sq-44afe98e95d3 (11 mm).
   - So the same field-day can have two different deficits. No answer changes, but an agent that reuses one cached series will not match the key exactly.

4. **Refill items never state the start day of the moisture balance.** It has to be inferred from the only `soil_moisture_vol` value in the table. That works here, but the rule does not say so.

5. **Gaps in the refill flow rule.** It does not cover a water meter that stays flat while the hour meter advances (flow = 0, giving infinite days). That case does not occur in this set. In every stalled case here, both meters are flat.

6. **«ولو أمكن حساب حدٍّ أدنى له»** invites lower-bound reasoning.
   - In sq-119797721cd3 the lower bound is 138.8 mm. That falls only inside option ج (110-160 mm) and rules out the other two ranges. The steady-rate estimate is 142.7 mm, also inside ج.
   - The rule is explicit that the volume is unknown, so the answer is abstain. Still, ج works as a deliberate trap for anyone who reasons "the lower bound already picks the bucket".
   - In sq-37fc8deb153e the lower-bound ratio is at least 0.964, which leaves "within" and "more than" both open, so abstain is unambiguous there.

7. **Independence of origin in corroboration.** The rule lists only «أصل التوقيت اليومي». A domain-aware reader may treat CHIRPS as independent, because its totals come from satellite and gauge data, not ERA5.
   - Items that hinge on CHIRPS being counted as era5-origin: sq-105b705813dd, sq-03cc0e240038 and sq-1696982bd259 (only same-origin sources, so abstain).
   - It would help to say explicitly that origin means daily-timing origin only.

8. **Items with more than one abstain trigger have little diagnostic value**, because they cannot show which rule the agent applied:
   - sq-77750d3d87a1: a plan week is missing (07-16..22) **and** meter T12 is shared;
   - sq-8e4e08d4159f: both hour meters stalled;
   - sq-a6f412c84346 and sq-c11ebcc86207: both hour meters stalled (the balance itself is computable);
   - sq-0afee06d9a05 and sq-db82fb2004be: meter reset (one cause each, fine).

9. **Registered-area traps that do not discriminate.**
   - pivot_2: registered 50.5 ha vs drawn 50.48 ha, so using the registered area cannot be detected.
   - tihama_2: registered 1200 ha vs drawn 11.3 ha, but the item abstains anyway because of the shared meter.
   - Only sq-5e19125c8ada (no boundary, 18 ha registered → 87.1 mm → option أ) actually tests this trap.

## 2. Options that leak the answer or can be eliminated without the data

- **Range sets with a gap.** In two of the three gapped sets, the isolated range is the correct answer, so a "pick the odd range" heuristic gets 2 of 3:
  - sq-2d1a2fdd0913: 0-20, 20-40, **60-80** (the gap is 40-60);
  - sq-11bf8d2cddcc: 0-5, 5-10, **15-20**.
  - In sq-5e19125c8ada the isolated range 80-100 is the registered-area trap.
- **The correct range is always roughly centred on the true value**, and the non-round bounds expose how the ranges were built:
  - sq-871b2b4c43b2: 6.8-8.8 for a true value of 7.9;
  - sq-a3e0a756e6b8: 36-46 for 40.6.
- **sq-bdbdf489455a: the option «0 مم: لم يُروَ الحقل» appears only in the item with no meter**, which signals that it is the trap.
- **Abstain is the key in 26 of 68 items (38%):**

  | Family | Abstain keys |
  |---|---|
  | applied_depth | 5 of 9 |
  | corroboration | 5 of 11 |
  | refill | 5 of 12 |
  | stress | 7 of 19 |
  | rain_total | 2 of 11 |
  | plan | 2 of 6 |

  Always answering abstain scores 38%, and 56% on applied_depth. The abstain option's letter is well spread (أ20 ب20 ج17 د11).

## 3. Easy misreadings (each one maps to a distractor)

- **Ignoring Ea** (Ea = 1) flips:
  - sq-18e00ab9e53f: severe → moderate;
  - sq-c6b3de759c97: moderate → none;
  - sq-de5eb272251c: moderate → none;
  - refill sq-6e5378a8657c: the status changes, but the days stay above 5.
- **Using era5land instead of the station** in sq-18e00ab9e53f gives moderate (Ks 0.503).
- **Stalled wells in refill.** Dropping the stalled well P1B in sq-7b79fdecfb8c gives 31 days (ج). The rule forbids dropping a well.
- **Days missing from the station series:**
  - sq-c96b4b3df0a6: summing what is there gives 0 → "0-2";
  - sq-008b6ed23034: summing what is there gives 14 → "11-16".
- **The shared meter T12:**
  - tihama_2 alone → 272 mm (ج);
  - tihama_2 with its registered area → 2.6 mm (د);
  - tihama_1 alone → 146.7 mm (ج);
  - half the volume each → 73 mm (أ).
- **sq-478ee0acf9e9: the moisture value is in kPa.** Reading 28 kPa as 28% makes θ larger than field capacity, so Dr0 = 0 and the result is no stress (ج).
- **sq-035a63c8dcb5 and sq-44afe98e95d3: the station is missing 07-20..22.** The rule says to fall back to chirps, which is complete, so the answer is computable. An agent that keeps the station as the preferred source and then sees the gap would wrongly abstain.
- **Day boundaries.** Starting the volume from the reading at the end of the first day instead of the day before (off by one day) changes no answer: sq-135f287b53c4 ratio 1.077 → 1.039, still within ±10%.
- **sq-a3e0a756e6b8: the two readings on 07-05** (`53520 (06:00) / 54360 (21:00)`) are increasing, so there is no drop. The last valid reading, 54360, is the one to use.

## 4. Thin margins (all resolved, listed for the key reviewer)

- sq-18e00ab9e53f: Ks 0.436 under the intended reading. It is 0.489 or 0.507 under the alternative readings in note 1.
- Every other computed status is at least 7.5 mm from RAW or at least 0.11 from Ks = 0.5.
- Refill run-days: 1.35, 1.63, 3.18, 9.6, 11.7, 13.3 and 15.0 — none near the 2 or 5 boundaries.
