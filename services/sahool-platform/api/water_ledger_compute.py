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
    "confidence, created_by, created_at, irrigation_reported_by"
)

#: Columns a POST may write, in INSERT order. ``ledger_date`` is the key, not a column to write.
LEDGER_WRITABLE_COLUMNS = (*_NUMERIC_FIELDS[:-1], *_TEXT_FIELDS, "confidence")


def ledger_write_columns(fields_set) -> tuple[str, ...]:
    """The columns the caller actually sent (W0-13, finding mobile-3).

    The upsert used to replace every column of the day, so a body without ``et0_mm`` wrote
    NULL over the value the water-balance worker had computed. Only the columns present in
    the request are written on conflict now; an omitted column keeps its stored value, and
    an explicit ``null`` still clears it.
    """
    sent = set(fields_set)
    return tuple(c for c in LEDGER_WRITABLE_COLUMNS if c in sent)


# W0-13 (finding mobile-3): partial semantics. Each column is written on conflict only when the
# caller sent it ($17 lists the sent columns), so a body of {ledger_date, irrigation_mm} replayed
# from the mobile outbox no longer writes NULL over the ET0, depletion and confidence that the
# water-balance worker computed.
#
# Who owns the day stays in created_by alone, which is all the worker reads to decide whether to
# compute it (manual_entry_takes_precedence) and all its upsert guards on. irrigation_reported_by
# (v280) only says that a person reported the applied water on a day the worker owns, so the
# worker keeps that figure and recomputes the balance around it.
#
# Parameters: $15 created_by and $16 irrigation_reported_by for a new row (a report: the worker
# and the reporter; any other write: the author and NULL), $17 the sent columns, $18 the worker's
# created_by, $19 the author. On conflict:
#   * a report ($16 set) on a worker day records the reporter; on any other day (a manual entry,
#     an as-applied reconciliation) it writes the figure and leaves the owner alone;
#   * any other write onto a day a report opened and the worker has not computed yet (worker row,
#     a reporter, no decision: the worker always writes one) takes the day for its author, as it
#     would have taken a new day;
#   * any other write that sends irrigation_mm onto a worker day records its author as reporter
#     when it carries a figure, and clears the reporter when it clears the figure, so the stored
#     irrigation_mm is always the one the worker's balance uses.
_WORKER_DAY = "water_ledger.created_by = $18"
_UNCOMPUTED_REPORT_DAY = (
    f"({_WORKER_DAY} AND water_ledger.irrigation_reported_by IS NOT NULL"
    " AND water_ledger.decision IS NULL)"
)
LEDGER_UPSERT_SQL = (
    "INSERT INTO water_ledger "
    "(tenant_id, field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm, "
    " irrigation_mm, soil_moisture_pct, depletion_mm, deficit_mm, "
    " stage, decision, confidence, created_by, irrigation_reported_by, created_at, updated_at) "
    "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
    " $13, $14, $15, $16, now(), now()) "
    "ON CONFLICT (field_id, ledger_date) DO UPDATE SET "
    " et0_mm = CASE WHEN 'et0_mm' = ANY($17::text[]) THEN EXCLUDED.et0_mm ELSE water_ledger.et0_mm END,"
    " kc = CASE WHEN 'kc' = ANY($17::text[]) THEN EXCLUDED.kc ELSE water_ledger.kc END,"
    " etc_mm = CASE WHEN 'etc_mm' = ANY($17::text[]) THEN EXCLUDED.etc_mm ELSE water_ledger.etc_mm END,"
    " rain_mm = CASE WHEN 'rain_mm' = ANY($17::text[]) THEN EXCLUDED.rain_mm ELSE water_ledger.rain_mm END,"
    " irrigation_mm = CASE WHEN 'irrigation_mm' = ANY($17::text[]) THEN EXCLUDED.irrigation_mm ELSE water_ledger.irrigation_mm END,"
    " soil_moisture_pct = CASE WHEN 'soil_moisture_pct' = ANY($17::text[]) THEN EXCLUDED.soil_moisture_pct ELSE water_ledger.soil_moisture_pct END,"
    " depletion_mm = CASE WHEN 'depletion_mm' = ANY($17::text[]) THEN EXCLUDED.depletion_mm ELSE water_ledger.depletion_mm END,"
    " deficit_mm = CASE WHEN 'deficit_mm' = ANY($17::text[]) THEN EXCLUDED.deficit_mm ELSE water_ledger.deficit_mm END,"
    " stage = CASE WHEN 'stage' = ANY($17::text[]) THEN EXCLUDED.stage ELSE water_ledger.stage END,"
    " decision = CASE WHEN 'decision' = ANY($17::text[]) THEN EXCLUDED.decision ELSE water_ledger.decision END,"
    " confidence = CASE WHEN 'confidence' = ANY($17::text[]) THEN EXCLUDED.confidence ELSE water_ledger.confidence END,"
    # v279 provenance (W0-10) describes the worker's own values: a manual write that replaces
    # ET0, rain or the balance clears the matching provenance; an irrigation-only report keeps it.
    " et0_method = CASE WHEN 'et0_mm' = ANY($17::text[]) THEN NULL ELSE water_ledger.et0_method END,"
    " et0_quality = CASE WHEN 'et0_mm' = ANY($17::text[]) THEN NULL ELSE water_ledger.et0_quality END,"
    " weather_snapshot_id = CASE WHEN 'et0_mm' = ANY($17::text[]) THEN NULL"
    " ELSE water_ledger.weather_snapshot_id END,"
    " rain_source = CASE WHEN 'rain_mm' = ANY($17::text[]) THEN NULL ELSE water_ledger.rain_source END,"
    " taw_mm = CASE WHEN 'depletion_mm' = ANY($17::text[]) THEN NULL ELSE water_ledger.taw_mm END,"
    " raw_mm = CASE WHEN 'depletion_mm' = ANY($17::text[]) THEN NULL ELSE water_ledger.raw_mm END,"
    " created_by = CASE WHEN $16::text IS NULL AND "
    + _UNCOMPUTED_REPORT_DAY
    + " THEN $19 ELSE water_ledger.created_by END,"
    " irrigation_reported_by = CASE"
    f" WHEN $16::text IS NOT NULL AND {_WORKER_DAY} THEN $16"
    " WHEN $16::text IS NOT NULL THEN water_ledger.irrigation_reported_by"
    f" WHEN {_UNCOMPUTED_REPORT_DAY} THEN NULL"
    f" WHEN 'irrigation_mm' = ANY($17::text[]) AND {_WORKER_DAY}"
    " THEN CASE WHEN EXCLUDED.irrigation_mm IS NULL THEN NULL ELSE $19 END"
    " ELSE water_ledger.irrigation_reported_by END,"
    " updated_at = now()"
)


def is_irrigation_report(columns) -> bool:
    """A person reporting the water they applied, and nothing else.

    Such a write never takes the day away from the worker: on a new day it opens a row owned by
    the worker (``created_by``) with the reporter in ``irrigation_reported_by``, and on a worker
    row it changes the applied water only.
    """
    return tuple(columns) == ("irrigation_mm",)


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
        # v280: who reported irrigation_mm on a worker-computed day (None for the worker's own
        # figure or a full manual entry). A row read before v280, or a stub, has no such key.
        "irrigation_reported_by": _optional(row, "irrigation_reported_by"),
    }


def _optional(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None
