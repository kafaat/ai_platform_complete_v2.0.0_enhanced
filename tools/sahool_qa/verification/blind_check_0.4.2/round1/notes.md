# blind_042 checker notes

I solved all 72 items independently with `work/solve.py`. Areas come from `work/geo.py`, which maps WGS84 to the authalic sphere (exactly equal-area) and applies spherical excess on densified edges. A local ellipsoidal tangent-plane check agrees to better than 1e-6. The areas are:

| Field | Area |
|---|---|
| strip | 31,444.2 m² |
| pivot_1 | 504,795.3 m² |
| pivot_2 | 504,792.2 m² |
| tihama_pivot | 282,566.2 m² |
| marib_pivot | 384,535.0 m² |
| marib_1 | 134,965.3 m² |
| orchard | 63,016.0 m² |
| flood | 100,005.4 m² |
| tihama_1 | 209,987.6 m² |
| tihama_2 | 113,088.3 m² |

No answered value sits within about 6% of a bin edge, so the choice of area method cannot change any answer.

## 1. Rule text that is ambiguous, under-specified or open to two readings

1. **Idle well in the refill flow window.** The rule says «غياب طرف من العدادين أو نزوله أو عدم تقدم الساعات يجعل التدفق غير معروف؛ لا تُسقط البئر» and «التدفق الصفري لا يُستنتج من العدادات وحدها».
   - Read literally, a well whose water meter and hour meter are both flat for the whole window has unknown flow, so the answer is abstain.
   - **sq-7b79fdecfb8c** is where two readings diverge most:
     - P1A was measured at 150 m³/h.
     - P1B is flat (106770 m³ / 3383 h) for the whole 01-19→01-26 window.
     - Under the strict reading the answer is abstain (ج).
     - A reader who drops the idle well gets 46,843 m³ ÷ 1,500 = 31.2 d, which is ">5" (ب).
     - Reusing P1B's earlier 130 m³/h gives 16.7 d, also ب.
   - The same strict reading makes these abstain because every well is flat:
     - sq-1279fb7ebfb2, sq-a6f412c84346, sq-c11ebcc86207 (TP1 and TP2);
     - sq-8e4e08d4159f (P1A and P1B).
   - In those four items, the option «لا مدة تعويض محدودة» is the trap.
2. **Intra-day reading compared with daily hours.**
   - TP1 on 2026-07-05 reads «53520 (06:00) / 54360 (21:00)»; the 06:00 value equals the previous day's end value. TP1's hour meter is daily (3031→3038).
   - «إذا تقدم عداد ساعات البئر ساعة أو أكثر بين قراءتين بينما لم يتقدم عداد مائها» does not say whether the two meters' readings must be simultaneous.
   - Pairing the 07-05 hour value with the 06:00 water value creates a false conflict. That reading would give abstain in sq-754ea37c5b10, where I answered ج (3.19 d), and in the stress and refill balances that cover 07-05.
   - I treated end of day against end of day, which gives no conflict.
3. **Flat meter with no hour-meter column in applied-depth contexts.**
   - The rule says «عداد قُرئ ولم يتقدم فريّه صفر معروف، ما لم يتقدم عداد ساعات البئر نفسها», but no applied-depth context includes pump_hours.
   - I took a flat meter as a known zero:
     - sq-02bcc1687f98 → أ 0-2;
     - sq-2b64e8152eed → د 0-2;
     - the P1B part of sq-e93353553494 and sq-62c39f25f9f2.
   - The refill contexts for the same wells show the hours flat as well, so the data are consistent.
   - An agent that demands hour evidence before accepting a zero would abstain on these items.
4. **Which day's p sets the end-of-day RAW** in «لا إجهاد إذا لم يتجاوز عجز نهايته الماء الميسّر». p changes daily with ETc. I used the target day's p. The closest case is sq-55ef41ddd20c (Dr_end 84.3 against RAW 76.8; RAW anywhere in the window is 74.9–76.8), so no answer flips.
5. **Whether the anchor-to-first-reading step counts in «إذا نزلت قراءة عن سابقتها بين طرفي الفترة».**
   - In sq-8a9cc1fff668 (a = 01-24), the drop runs from the end-of-01-24 anchor (261790) to the 01-25 reading (12).
   - The readings strictly inside the period are monotonic. I counted the drop because the pumping day 01-25 is inside the period.
6. **Different gap rules across families, by design.**
   - P2A has no readings on 01-21..01-23.
   - The depth rule allows this («ولو غابت القراءات بينهما»), so sq-3c064c1c5e85 = 106.8 mm, sq-4ad26cb78901 = 25.2 mm, and sq-1f408933b540 has ratio 1.335.
   - The stress rule makes any day with a missing meter unknown, so sq-0fd71a31360a and sq-ef96b39fe8b1 are abstain.
   - An agent that carries the stress-rule strictness into depth items will wrongly abstain on those depth items.
7. **Plan weeks** are defined only by their record date. «أسبوع بلا سجل» assumes the records tile the question window. They do in every item here. sq-77750d3d87a1 is missing the 07-16 week and also uses a shared meter, so abstain is reached two independent ways.
8. **Multiple rain records on 01-18** (station «8.4 (23:30) / 8.2 (23:45)») are averaged to 8.3, as the rule says. «آخر قراءة» applies only to water meters, and an agent could mix the two up. This does not change any answer.
9. **Rain source changes with the target date.** For tihama_pivot the station has no records on 07-20..07-22, so CHIRPS applies only to targets on or after 07-20 (sq-035a63c8dcb5, sq-44afe98e95d3, sq-a6f412c84346, sq-c11ebcc86207). Earlier targets use the station, whose 07-10 value is 14 against CHIRPS 11. The rule is clear, but this is easy to miss.
10. **Endpoint-only flow.** In sq-e61e414056ea, P1B ran only on 01-13 (1170 m³ / 9 h) and was idle afterwards. The endpoint formula gives 130 m³/h, which counts in Q_total. The answer is ">5" either way (11.7 d, or 21.9 d with P1A alone).

## 2. Options that leak the answer, or can be eliminated without the data

- **No positional leak.** Correct numeric bins are spread low/mid/high 11/8/10. Answer letters are أ 19, ب 12, ج 24, د 17, and هـ 0.
- **Abstain items have numeric bins built around the trap value**, so the bins confirm the trap rather than reveal the answer:

  | Item | Trap | Trap value | Bin it lands in |
  |---|---|---|---|
  | sq-3f3d9a32439b | ignore the shared meter | 272.4 mm | 200-300 |
  | sq-7a41df82e393 | ignore the shared meter | 146.7 mm | 120-170 |
  | sq-5e19125c8ada | use the registered 18 ha (no boundary) | 87.1 mm | 80-100 |
  | sq-119797721cd3 | lower bound across the meter reset | 139.2 mm | 110-160 |
  | sq-8a9cc1fff668 | lower bound across the meter reset | 30.7 mm | 26-36 |
  | sq-37fc8deb153e | lower bound across the meter reset | ratio 0.966 | "within ±10%" |
  | sq-bdbdf489455a | treat "no meter" as zero | 0 | 0-2 |

- **Bin edges hint at the generator's centred value.** Off-grid bins (52-72, 22-32, 26-36, 36-46, 24-34, 13-18) suggest the bins were centred on that value. This is only a weak hint and does not identify the answer.

## 3. Options never plausibly correct

- **Refill «لا مدة تعويض محدودة: كل آبار الحقل خارج الخدمة بسجل حالة طوال نافذة التدفق»** can never be correct in any of the 12 refill items. No context in the set has a well_status_X column. The well_status clause and the clause on the hour meter disagreeing with the water meter are also never triggered: no well anywhere has hours rising by 1 h or more while its water meter stays flat. That part of the brief is not tested by this set.
- No other option is structurally dead.

## 4. Easy misreads (where a careful agent could slip)

- **Registered area against drawn boundary.** pivot_2 is registered at 50.5 ha (immaterial). tihama_2 is registered at 1,200 ha against a geodesic 11.3 ha, and its meter is shared anyway.
- **Point location but no boundary:** tihama_farm.
- **Invalid moisture unit:** marib_1 records moisture in kPa (sq-478ee0acf9e9), which the rule does not accept, so abstain. That table also has no station column, which does not matter.
- **Meter reset** on MP1 on 01-25 (261790 → 12):
  - makes the answer abstain for every period that contains 01-25: sq-119797721cd3, sq-8a9cc1fff668, sq-37fc8deb153e, sq-0afee06d9a05, sq-db82fb2004be;
  - does not affect periods that end on 01-24 or start on 01-31 or later: sq-10b76e6b5d36, sq-dfbfc43d3375, sq-de5eb272251c, sq-6e5378a8657c.
- **Initial deficit above RAW.** sq-55ef41ddd20c starts with Dr0 = 100 > RAW, so Ks on day 1 is 0.45 (severe), but by 01-17 it has recovered to moderate (Ks_end 0.83). An agent that judges from Dr0 or Ks_start will pick severe.
- **Refill uses the whole deficit, not only the part above RAW.** sq-1763acc8c6d3 and sq-e61e414056ea show no stress, yet need more than 5 pumping days.
