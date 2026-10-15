# Blind check: water-records MCQ set (68 items)

Method: every item solved from `questions.jsonl` only. Python code is in `work/` (`parse.py`, `geo.py`, `solve.py`, `variants.py`, `emit.py`). Field areas come from the drawn GeoJSON. I computed them two ways: an ellipsoidal equal-area projection (WGS84) with the shoelace formula, and authalic-sphere spherical excess. The two agree to better than 1e-5. Geodesic areas (m²): pivot_1 504,795; pivot_2 504,792; flood 100,005; marib_pivot 384,535; marib_1 134,965; tihama_1 209,988; tihama_2 113,088; tihama_pivot 282,566. tihama_farm has no boundary.

All 68 items have an answer. In 7 of them the rule text allows two defensible readings that lead to different options (section 1). The other 61 have only one defensible reading. Section 4 lists outright errors (not alternative readings) that would still flip some of them.

---

## 1. Items where the rule text allows two readings

| item | my answer | other candidate | why |
|---|---|---|---|
| sq-3f3d9a32439b (applied_depth, تهامة 2) | أ (abstain) | ج 200-300 | The rule says «العداد المسجّل لأكثر من حقل لا يُقسم بينها». This can mean either "do not apportion it, so the field's share is unknown" or "do not split it, so charge the full volume to each field". The full-volume reading gives 272.4 mm, which matches option ج. The other distractors also map to misreadings: a half split gives 136.2 (ب), and pooling over both fields' area or using the registered 1200 ha gives د. The applied-depth rule never says outright that a shared meter makes the depth unknown. Only the stress rule does («أو عداده مشترك، يجعل الحالة غير معروفة»). I chose abstain to stay consistent with that rule. |
| sq-7a41df82e393 (applied_depth, تهامة 1) | ب (abstain) | ج 120-170 | Same wording. The full-volume reading gives 146.7 mm (ج). A half split (73.3) or pooling (95.3) gives أ. |
| sq-7b79fdecfb8c (refill, P1 @01-26) | ب (abstain) | ج >5 | P1B's hour meter stays at 3383 h from 01-19 to 01-26, and «عداد ساعات لم يتقدم» makes its flow unknown. The rule «تعمل الآبار معاً بمجموع تدفقها» does not say whether one unknown flow makes the sum unknown or whether the idle well is simply dropped. If P1B is dropped, the result is 46,791 m³ / (150 m³/h × 10 h) = 31.2 days, which is ج. Either reading needs Dr = 74.15 mm. |
| sq-0fd71a31360a / sq-ef96b39fe8b1 (stress, P2 @01-26 / 02-02) | د / ب (abstain) | ب / ج (no stress) | P2A has no reading on 01-21..23 (P2B does). The stress rule says «يوم بلا … قراءة عداد» makes the status unknown. However, the depth rule in the neighbouring family says the opposite for cumulative meters («ولو غابت القراءات بينهما»). An agent who carries that over and interpolates gets Dr 19.3 / 30.6 mm with no stress. It is also unclear whether "a day without a meter reading" means any meter or all of the field's meters. |
| sq-119797721cd3 (applied_depth, محور مأرب) | أ (abstain) | ج 110-160 | MP1 reset on 01-25. Summing only the known segments gives a lower bound of 138.8 mm, already inside ج. The reset day would have to exceed about 8,160 m³ to leave the bin, against a normal day of about 1,520 m³. The rule says the volume is unknown, so the answer is abstain. A careful bounding argument would still land on ج. |
| sq-37fc8deb153e (plan, محور مأرب) | ج (abstain) | أ within ±10% | Same reset. The lower-bound ratio is 0.964. "Within" stays true as long as the unknown day is at most about 7,550 m³. Same tension as the item above. |

I am confident in the other abstain answers. The rule names each of those defects explicitly.

## 2. Ambiguous or under-specified wording (answers do not change)

- **Plan period end (plan_vs_measured, all 6 items).** «الفترة من أول أسبوع إلى نهاية آخر أسبوع» together with «المقيس … بين قراءتي طرفي الفترة». Four weekly records starting 01-05 cover 01-05..02-01 inclusive, yet the question says «من 2026-01-05 إلى 2026-02-02». The start reading (end of 01-05) also leaves out 01-05's own pumping. I used the readings on 01-05 and 02-02, which is 28 days of flow and matches the question dates. Using 02-01 as the end changes no category (for example sq-135f287b53c4 moves from 1.077 to 1.039, still within).
- **Day convention differs across families.** Rain totals are «شاملةً طرفيها», counting both end days. Meter depths are differences between end-of-day readings, so the first day's pumping is excluded. Neither convention is stated as a contrast, and an agent could mix them. No answer changes here.
- **«قراءة اليوم = آخر قراءة صالحة فيه» vs «القيمة اليومية المتوسطة».** Meters use the last reading of the day and rain uses the daily mean. The context shows only one value per day, so the agent can neither apply nor check either aggregation. The rule mentions an operation the data never exercises.
- **Stress Ks wording.** «Ks = 1 إذا كان عجز بداية اليوم ≤ RAW، وإلا (TAW − Dr) ÷ …» does not say whether "Dr" here is the start-of-day deficit. I used the start-of-day deficit and that day's p, as in FAO-56. Using the previous day's p instead changes no outcome.
- **Refill wells.** The rule never states that `meter_total_X` and `pump_hours_X` belong to the same well. Matching them by suffix is implied but not written.
- **Refill boundaries.** «تُقارن بالحدّين 2 و5» does not say which side the boundary values fall on. Only the option texts settle it («2 أو أقل», «أكثر من 2 وحتى 5»). No computed value is near 2 or 5. The closest are 1.35 (sq-1e25025ab7a8) and 1.625 (sq-c6b15d75c5df).
- **CHIRPS lineage.** The context lists only `era5` as CHIRPS v3 rnl's origin. Real CHIRPS also draws on satellite and gauge data. An agent who adds a "gauge" origin to CHIRPS would see it share an origin with `station`. This changes nothing here: in sq-e9329cb5aa71 era5land is still independent and complete (0.6 mm), so the answer stays "not confirmed".
- **Corroboration option (singular).** «المصدر المستقل الأصل سجّل النافذة كاملة …» is the correct key in sq-e9329cb5aa71, where two independent sources exist (chirps 1.0, era5land 0.6). The text is slightly off but still correct.
- **Applied depth with gaps.** sq-3c064c1c5e85 has P2A missing on 01-21..23, which is fine under the cumulative rule. That item has no abstain option, which signals that the gap does not matter (see section 3).
- **GeoJSON winding.** The four pivot polygons are clockwise, while RFC 7946 expects counter-clockwise exterior rings. Signed-area code without abs() would return a negative area.
- **Agronomy, outside the rule.** A single 30 cm probe (`probe-30cm`) sets Dr0 for a 1 m root zone. The rule mandates this, so the answer is unaffected, but it is a questionable model.

## 3. Leaks and option-design issues

- **Strong leak in applied_depth.** All 5 items that offer the abstain option have abstain as the answer. All 4 items without it are computable. The mere presence of the abstain option gives the answer away. rain_total shows a weaker version: the 5 items without the option are all computable.
- **Self-refuting distractor (rain_corroboration, all 11).** «مؤكَّد لأن مصدراً ثانياً سجّل مطراً في اليوم نفسه، ولو كان يشاركه الأصل» contradicts the rule's own sentence «اتفاق مصدرين من الأصل نفسه ليس تأكيداً». It can be eliminated without reading any data, so each item is effectively 3-way.
- **Letter balance.** ج 23, د 17, أ 15, ب 13. ج is over-used (5/9 in applied_depth, 6/11 in rain_total).
- **Good distractors.** Most numeric distractors match a specific misreading: registered area, missing treated as zero, shared meter split or charged in full, reset treated as zero, kPa read as %, irrigation treated as 0, idle well dropped. They are recorded per item under `key_numbers.misreading_trap` in answers.json. This is good design and should be kept.

## 4. Things a careful agent could misread

- **Registered vs drawn area.** تهامة 2 is registered at «1200 هكتار» but its drawn boundary is 11.3 ha. مزرعة تهامة has a registered area (18 ha) and no boundary, so the depth is unknown. Using the registered 18 ha gives 87.1 mm (option أ).
- **Planimetric area error.** A Web-Mercator shoelace (a common mistake) overstates area by 7-9% at 14-16°N. That flips sq-2d1a2fdd0913 from ب (65.0 mm) to ج (59.7 mm). It also flips sq-c6b15d75c5df from د (1.63 days) to ج (2.65 days), and pushes sq-1e25025ab7a8 to 1.91 days, still in أ but marginal. A spherical model with a mean radius is only off by +0.35% and flips nothing.
- **Unit trap.** In sq-478ee0acf9e9 the soil moisture is in kPa («soil_moisture_vol (kPa…)»). Reading 28 kPa as 28 % gives Dr0 = 0 and "no stress". The rule «أي وحدة أخرى لا تصلح» makes the answer abstain. The column name `soil_moisture_vol` paired with a kPa unit is a deliberately misleading label.
- **Rain-source choice in the balance.** In sq-035a63c8dcb5, sq-44afe98e95d3, sq-c11ebcc86207 and sq-a6f412c84346 the station is missing on 07-20..22, so CHIRPS must be used, but only for targets after 07-19. For sq-361f3c4eced8 (07-15) the station is still complete and must be used. sq-18e00ab9e53f is the most sensitive: with the station (correct) Ks = 0.437, severe. With era5land Ks = 0.50, moderate, right at the boundary. Without Ea it is moderate (0.56).
- **Ea omitted.** Leaving out Ea in the balance flips sq-c6b3de759c97 and sq-de5eb272251c from moderate to no stress, and sq-18e00ab9e53f from severe to moderate.
- **Refill target.** «تعويض عجز المنطقة الجذرية» refills Dr, not Dr − RAW. An agent who reasons "no stress, so 0 days" gets ≤2 wrong on sq-1763acc8c6d3 and sq-e61e414056ea, where the answer is more than 5 days (9.6 and 11.7).
- **Station gaps in rain totals.** sq-c96b4b3df0a6 and sq-008b6ed23034: treating «—» as dry gives 0 mm and 14 mm, and both values have matching options.

## 5. Items I found hard

- sq-7b79fdecfb8c (idle well and sum of flows), sq-3f3d9a32439b and sq-7a41df82e393 (shared-meter wording), sq-0fd71a31360a and sq-ef96b39fe8b1 (meter-gap policy conflicts between families): see section 1.
- sq-18e00ab9e53f: a 28-day balance with a Kc change, a rain event and a pump stopping. The answer holds under the correct rule (Ks 0.437 against 0.5), but it is the most fragile computed item.
- sq-de5eb272251c: on 01-19 the start-of-day Dr is 76.46 against RAW 76.93, so Ks switches to 1 by less than 0.5 mm. The final status (moderate, Ks 0.85) is not affected.
