"""api/water_twin_seed.py — تغذية Water Twin من دفتر المياه اليوميّ (v98).

المرحلة الثانية من Water Twin (``decisions/water-intelligence-direction.md``): بدل تمرير الحالة
الابتدائيّة يدويّاً، **نستثمر دفتر المياه v98** لاشتقاق:
  - **النضوب الابتدائيّ** (``Dr0``) من أحدث صفّ دفتر (``depletion_mm`` مباشرةً، أو من
    ``soil_moisture_pct`` عبر ``Dr = TAW·(1 − SM/100)``).
  - **تقدير ETc اليوميّ** للأفق الأماميّ من **متوسّط** ETc الأخيرة المسجَّلة.

صدق منهجيّ صارم (نمط الدفتر/``decision_record``):
  - **لا تخترع أرقاماً.** إن غاب مصدر الاشتقاق (لا دفتر، لا قيم) ⇒ نُعيد ``None`` مع **مصدر
    صريح** (``"unavailable"``) فيردّ الراوتر بصدق (لا حالة مُلفّقة).
  - **TAW/RAW لا يُشتقّان من الدفتر** (يحتاجان قوام التربة وعمق الجذور) — يُمرَّران صراحةً من
    المستدعي (إقرار زراعيّ)، فلا نخمّن سعة التربة.
  - **مصدر كلّ قيمة مُعلَن** (``sources``) للشفافيّة والتدقيق.

نقيّ بالكامل (بلا I/O/قاعدة) ⇒ يُختبَر بـunit؛ الراوتر يقرأ الدفتر ويستدعي هذه الدوالّ.
"""

from __future__ import annotations


def average_recent_etc(recent_rows: list[dict]) -> float | None:
    """متوسّط ``etc_mm`` غير الفارغة من صفوف الدفتر الأخيرة (None إن لا قيم — لا تلفيق)."""
    vals = [r["etc_mm"] for r in recent_rows if r.get("etc_mm") is not None]
    if not vals:
        return None
    return sum(float(v) for v in vals) / len(vals)


def seed_initial_depletion(
    latest_row: dict | None,
    taw_mm: float,
    override: float | None = None,
) -> tuple[float | None, str]:
    """يشتقّ النضوب الابتدائيّ ``Dr0`` (مم) ومصدره من أحدث صفّ دفتر.

    أولويّة: تجاوز صريح في الطلب → ``depletion_mm`` المُسجَّل → اشتقاق من
    ``soil_moisture_pct`` (``Dr = TAW·(1 − SM/100)``). غياب الكلّ ⇒ ``(None, "unavailable")``.
    يُقصَر الناتج إلى ``[0, TAW]`` (فيزيائيّ). لا تلفيق.
    """
    if override is not None:
        return _clamp(float(override), taw_mm), "request"
    if latest_row:
        dep = latest_row.get("depletion_mm")
        if dep is not None:
            return _clamp(float(dep), taw_mm), "ledger.depletion_mm"
        sm = latest_row.get("soil_moisture_pct")
        if sm is not None:
            return _clamp(taw_mm * (1.0 - float(sm) / 100.0), taw_mm), "ledger.soil_moisture_pct"
    return None, "unavailable"


def _clamp(value: float, taw_mm: float) -> float:
    return max(0.0, min(value, taw_mm))


# ─── وصلةُ الحسّاس بالدفتر — `SOIL-MOISTURE-UNIT-IDENTITY-01` ────────────────
#
# حقيقتان لرطوبة التربة كانتا لا تلتقيان: الدلوُ (الدفتر/التوأم) والحسّاسُ (RWC).
# هذه الوصلةُ **غيرُ سلطويّة**: الدفترُ يبقى البذرةَ حين يوجد؛ الحسّاسُ الطازج يهيّئ
# ``Dr`` فقط عند غيابه؛ والخلافُ الكبير يُنشَر قيداً بالقيمتين ولا يوقف المحاكاة.
# ولا اسمَ ``assimilated`` هنا — لا مُقدِّرَ يُخترَع.

#: عتبةُ الخلاف: كسرٌ من TAW بأرضيّة بالملّيمتر — مُعلَنان في المخرج لا مخفيّان.
SENSOR_CONFLICT_FRACTION_OF_TAW = 0.15
SENSOR_CONFLICT_FLOOR_MM = 10.0

LIMIT_UNIT_UNDECLARED = "soil_moisture_sensor_unit_undeclared"
LIMIT_CONVERSION_INPUTS_MISSING = "soil_moisture_sensor_conversion_inputs_missing"
LIMIT_SENSOR_STALE = "soil_moisture_sensor_reading_stale"
LIMIT_SENSOR_DISAGREES = "soil_moisture_sensor_disagrees_with_ledger"
LIMIT_SEED_FROM_SENSOR = "seed_from_single_point_sensor"
LIMIT_NO_SENSOR = "soil_moisture_sensor_unavailable"


def sensor_depletion_mm(
    *,
    value_pct: float,
    unit_kind: str,
    taw_mm: float,
    root_depth_m: float | None,
    theta_fc: float | None,
) -> tuple[float | None, str | None]:
    """نضوبُ منطقة الجذور (مم) من قراءة حسّاس **بوحدتها المُعلَنة** — أو ``None`` بسبب.

    - ``available_pct`` (نسبة الماء المتاح): ``Dr = TAW·(1 − p/100)``.
    - ``vwc_pct`` (رطوبة حجميّة): ``Dr = (θFC − θ)·Zr·1000`` — يحتاج عمقَ الجذور وθFC؛
      **لا** ``TAW·(1 − p/100)``: هذه كانت تُقرأ 25٪ VWC نضوباً 75 مم وهو هراء فيزيائيّ.
    - ``undeclared``: لا تحويلَ بلا وحدة — ``None`` وقيدٌ مسمًّى.
    """
    if unit_kind == "available_pct":
        return _clamp(taw_mm * (1.0 - float(value_pct) / 100.0), taw_mm), None
    if unit_kind == "vwc_pct":
        if root_depth_m is None or theta_fc is None or root_depth_m <= 0:
            return None, LIMIT_CONVERSION_INPUTS_MISSING
        theta = float(value_pct) / 100.0
        return _clamp((float(theta_fc) - theta) * float(root_depth_m) * 1000.0, taw_mm), None
    return None, LIMIT_UNIT_UNDECLARED


def join_sensor_with_ledger_seed(
    *,
    ledger_depletion_mm: float | None,
    ledger_source: str,
    sensor: dict | None,
    sensor_depletion: float | None,
    sensor_limitation: str | None,
    sensor_age_s: float | None,
    max_reading_age_s: float | None,
    taw_mm: float,
) -> dict:
    """يقارن بذرةَ الدفتر بقراءة الحسّاس ويُرجِع بذرةً واحدة **بمصدرها وقيودها**.

    القواعد، بترتيبها: قراءةٌ بائتة لا تُستعمل ولا تُقارَن (قيد) · بذرةُ الدفتر تبقى
    وإن خالفها الحسّاس (الخلافُ الكبير قيدٌ بالقيمتين والعتبة) · لا دفترَ + حسّاسٌ
    طازجٌ قابلٌ للتحويل ⇒ بذرةٌ من الحسّاس بقيد «نقطةٌ واحدة» · لا شيء ⇒ ``None``.
    """
    limitations: list[str] = []
    threshold = max(SENSOR_CONFLICT_FLOOR_MM, SENSOR_CONFLICT_FRACTION_OF_TAW * float(taw_mm))
    stale = (
        sensor_age_s is not None
        and max_reading_age_s is not None
        and sensor_age_s > max_reading_age_s
    )
    usable = sensor is not None and sensor_depletion is not None and not stale
    if sensor is None:
        limitations.append(LIMIT_NO_SENSOR)
    else:
        if stale:
            limitations.append(LIMIT_SENSOR_STALE)
        if sensor_limitation is not None:
            limitations.append(sensor_limitation)

    delta_mm: float | None = None
    if ledger_depletion_mm is not None:
        depletion, source = float(ledger_depletion_mm), ledger_source
        if usable:
            delta_mm = round(float(sensor_depletion) - depletion, 2)
            if abs(delta_mm) > threshold:
                limitations.append(LIMIT_SENSOR_DISAGREES)
    elif usable:
        depletion, source = float(sensor_depletion), f"sensor.{sensor['unit_kind']}"
        limitations.append(LIMIT_SEED_FROM_SENSOR)
    else:
        depletion, source = None, "unavailable"

    return {
        "depletion_mm": None if depletion is None else round(depletion, 2),
        "source": source,
        "ledger_depletion_mm": None
        if ledger_depletion_mm is None
        else round(float(ledger_depletion_mm), 2),
        "sensor": None
        if sensor is None
        else {
            **sensor,
            "age_s": None if sensor_age_s is None else round(float(sensor_age_s), 1),
            "stale": stale,
            "depletion_mm": None if sensor_depletion is None else round(float(sensor_depletion), 2),
        },
        "delta_mm": delta_mm,
        "conflict_threshold_mm": round(threshold, 2),
        "limitations": limitations,
    }


def seed_daily_etc(
    recent_rows: list[dict],
    override: float | None = None,
) -> tuple[float | None, str]:
    """يشتقّ تقدير ETc اليوميّ ومصدره: تجاوز صريح → متوسّط الدفتر الأخير → ``(None,"unavailable")``."""
    if override is not None:
        if override < 0:
            raise ValueError("daily_etc_mm يجب ألّا يكون سالباً.")
        return float(override), "request"
    avg = average_recent_etc(recent_rows)
    if avg is None:
        return None, "unavailable"
    return avg, "ledger.recent_etc_avg"
