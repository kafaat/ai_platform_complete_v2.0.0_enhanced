"""api/water_ledger_compute.py — منطق نقيّ لدفتر المياه اليوميّ (Daily Water Ledger).

وحدة نقيّة (بلا I/O، بلا قاعدة) تُختبَر بـunit: تحويل صفّ↔dict + تحقّق مدخلات.
قلّدت ``_row_to_prescription`` (routers/prescriptions.py) في فلسفتها.

صدق منهجيّ صارم (نمط ``decision_record``): الدفتر **تخزين/تدقيق** لقيم تُمرَّر من
المستدعي (أو محسوبة بمحرّكات FAO-56 القائمة ``core/engines/``) — **لا تخترع أرقاماً**.
الحقول الناقصة تبقى ``None`` (⇒ ``NULL`` في القاعدة) لا تُلفَّق ولا تُصفَّر. لا نُعيد
بناء نواة الريّ هنا.
"""

from __future__ import annotations

import datetime as _dt

# الحقول الرقميّة الاختياريّة للدفتر (كلّها قد تكون None ⇒ NULL، لا تلفيق).
_NUMERIC_FIELDS = (
    "et0_mm",
    "kc",
    "etc_mm",
    "rain_mm",
    "irrigation_mm",
    "soil_moisture_pct",
    "depletion_mm",
    "deficit_mm",
    "confidence",
)

# الحقول النصّيّة الاختياريّة.
_TEXT_FIELDS = ("stage", "decision")

# أعمدة القراءة لجدول water_ledger (v98) — مطابقة لمخرَج الإدامة.
LEDGER_SELECT_COLS = (
    "field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm, irrigation_mm, "
    "soil_moisture_pct, depletion_mm, deficit_mm, stage, decision, "
    "confidence, created_by, created_at"
)


def parse_ledger_date(value) -> _dt.date:
    """يحوّل تاريخ الدفتر إلى ``datetime.date`` (يقبل date أو نصّ ISO ``YYYY-MM-DD``).

    نقيّ (لا I/O). يرفع ``ValueError`` على مدخل غير صالح (يلتقطه الراوتر ⇒ 422).
    لا اختراع تاريخ افتراضيّ — التاريخ مفتاح القيد الفريد (idempotency).
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        # ``date.fromisoformat`` يرفض الصيغ غير ``YYYY-MM-DD`` ⇒ ValueError.
        return _dt.date.fromisoformat(value.strip())
    raise ValueError("ledger_date يجب أن يكون تاريخاً أو نصّاً ISO (YYYY-MM-DD)")


def _coerce_number(value):
    """يحوّل قيمة رقميّة اختياريّة إلى float أو None (لا تلفيق).

    None/نصّ فارغ ⇒ None (⇒ NULL). قيمة غير قابلة للتحويل ⇒ ``ValueError``
    (يلتقطها الراوتر ⇒ 422) — لا نُصفّر ولا نخترع رقماً.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool نوع فرعيّ من int — نرفضه صراحةً (لا معنى عدديّ)
        raise ValueError("قيمة عدديّة غير صالحة (bool)")
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        value = s
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"قيمة عدديّة غير صالحة: {value!r}") from e


def normalize_ledger_input(payload: dict) -> dict:
    """يتحقّق ويُطبِّع مدخل قيد الدفتر اليوميّ (نقيّ، بلا I/O).

    يُرجِع dict جاهزاً للإدامة بمفاتيح أعمدة ``water_ledger``. الحقول الرقميّة
    الناقصة/الفارغة ⇒ None (⇒ NULL، لا تلفيق)؛ الحقول النصّيّة الناقصة ⇒ None.
    ``ledger_date`` إلزاميّ (مفتاح idempotency) ⇒ ``ValueError`` إن غاب أو فسد.
    يرفع ``ValueError`` على أيّ مدخل غير صالح (يلتقطه الراوتر ⇒ 422).
    """
    if "ledger_date" not in payload or payload.get("ledger_date") in (None, ""):
        raise ValueError("ledger_date إلزاميّ (مفتاح القيد اليوميّ)")
    out: dict = {"ledger_date": parse_ledger_date(payload["ledger_date"])}
    for key in _NUMERIC_FIELDS:
        out[key] = _coerce_number(payload.get(key))
    for key in _TEXT_FIELDS:
        val = payload.get(key)
        if val is None:
            out[key] = None
        elif isinstance(val, str):
            stripped = val.strip()
            out[key] = stripped or None
        else:
            raise ValueError(f"الحقل {key} يجب أن يكون نصّاً أو None")
    return out


def row_to_ledger_entry(row) -> dict:
    """يحوّل صفّ ``water_ledger`` إلى dict (نقيّ، لا I/O) — يُختبَر بـunit بلا قاعدة.

    قلّد ``_row_to_prescription``: ``ledger_date`` (date) و``created_at`` (timestamptz)
    يُنسَّقان ISO؛ نصّاً أصلاً (mock) يُمرَّران كما هما. القيم الرقميّة الناقصة تبقى
    None (⇒ لا تلفيق). لا اختراع حقول غير موجودة في الصفّ.
    """
    ledger_date = row["ledger_date"]
    date_iso = ledger_date.isoformat() if hasattr(ledger_date, "isoformat") else (ledger_date or "")
    created = row["created_at"]
    created_iso = created.isoformat() if hasattr(created, "isoformat") else (created or "")
    return {
        "field_id": row["field_id"],
        "ledger_date": date_iso,
        "et0_mm": row["et0_mm"],
        "kc": row["kc"],
        "etc_mm": row["etc_mm"],
        "rain_mm": row["rain_mm"],
        "irrigation_mm": row["irrigation_mm"],
        "soil_moisture_pct": row["soil_moisture_pct"],
        "depletion_mm": row["depletion_mm"],
        "deficit_mm": row["deficit_mm"],
        "stage": row["stage"],
        "decision": row["decision"],
        "confidence": row["confidence"],
        "created_by": row["created_by"],
        "created_at": created_iso,
    }
