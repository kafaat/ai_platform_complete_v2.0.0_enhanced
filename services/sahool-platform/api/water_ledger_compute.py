"""api/water_ledger_compute.py — منطق نقيّ لدفتر المياه اليوميّ (Daily Water Ledger).

وحدة نقيّة (بلا I/O، بلا قاعدة) تُختبَر بـunit: تحويل صفّ↔dict + تحقّق مدخلات.
قلّدت ``_row_to_prescription`` (routers/prescriptions.py) في فلسفتها.

صدق منهجيّ صارم (نمط ``decision_record``): الدفتر **تخزين/تدقيق** لقيم تُمرَّر من
المستدعي (أو محسوبة بمحرّكات FAO-56 القائمة ``core/engines/``) — **لا تخترع أرقاماً**.
الحقول الناقصة تبقى ``None`` (⇒ ``NULL`` في القاعدة) لا تُلفَّق ولا تُصفَّر. لا نُعيد
بناء نواة الريّ هنا.

Exception, named here so the label stays honest: ``project_farm_water_to_ledger`` (W1-13) runs
two statements on the caller's connection, inside the caller's transaction. It sits next to
``LEDGER_UPSERT_SQL`` because it writes the same table under the same report semantics.
"""

from __future__ import annotations

import datetime as _dt
import math
import os

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
    "confidence, created_by, created_at, irrigation_reported_by, irrigation_source"
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
#
# A worker row with no decision is a day the worker has not computed (it always writes one). Such
# a row is opened by a report (W0-13) or the farm-ledger projection (W1-13), and the projection
# may later clear its figure and reporter (a record of unknown volume arrived), so "uncomputed"
# rests on the decision alone, not on a reporter being present.
_UNCOMPUTED_REPORT_DAY = f"({_WORKER_DAY} AND water_ledger.decision IS NULL)"
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
    # v284 (W1-13): a figure written here is the caller's, not the farm ledger's projection.
    " irrigation_source = CASE WHEN 'irrigation_mm' = ANY($17::text[]) THEN NULL"
    " ELSE water_ledger.irrigation_source END,"
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
        # v284 (W1-13): 'farm_ledger' when irrigation_mm is the projection of the day's measured
        # farm_water_records; None for the row writer's own figure.
        "irrigation_source": _optional(row, "irrigation_source"),
    }


def _optional(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


# ─── W1-13 (finding water-5, manual part): measured farm water → the daily ledger ──────────────
#
# Water a farmer measured in the farm operations ledger (``farm_water_records.water_volume_m3``
# on a completed operation for a field) never reached ``water_ledger``, so the balance read the
# day as "no irrigation recorded" and recommended watering a watered field. The day's measured
# volume is now projected onto ``irrigation_mm`` as a declared source.

#: ``water_ledger.irrigation_source`` for a figure projected from the farm ledger (v284).
IRRIGATION_SOURCE_FARM_LEDGER = "farm_ledger"


def irrigation_mm_from_volume(volume_m3, area_ha) -> float | None:
    """Applied depth in mm of ``volume_m3`` spread over ``area_ha``: m3 / ha / 10.

    1 mm over 1 ha is 10 m3, so 500 m3 on 1 ha is 50 mm. An unknown or non-positive area gives
    ``None``: no depth is invented from a field whose size is not recorded.
    """
    if volume_m3 is None or area_ha is None:
        return None
    volume = float(volume_m3)
    area = float(area_ha)
    if not (math.isfinite(volume) and math.isfinite(area)) or area <= 0 or volume < 0:
        return None
    return volume / area / 10.0


#: Serializes the projections of one (tenant, field, day). The projection reads the day's sum
#: and then overwrites ``irrigation_mm`` with it; without a lock taken *before* the sum, two
#: overlapping operation POSTs for the same field and day each sum only their own uncommitted
#: record (READ COMMITTED) and the later upsert replaces the earlier figure with its partial
#: sum, losing water. The lock is held to the end of the caller's transaction, and the sum runs
#: as a later statement, so under READ COMMITTED it sees every record committed by a projection
#: that held the lock before it.
FARM_WATER_DAY_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))"


def farm_water_day_lock_key(tenant_id: str, field_id: str, day) -> str:
    return f"water-ledger:farm-projection:{tenant_id}:{field_id}:{day.isoformat()}"


#: The ledger's local day comes from ``WATER_LEDGER_TIMEZONE`` (the water-balance worker's own
#: setting), not the database's ``CURRENT_DATE`` (UTC): a completed operation recorded in the
#: first local hours after midnight is today's work in the ledger, not future work.
def ledger_timezone() -> str:
    return os.getenv("WATER_LEDGER_TIMEZONE", "Asia/Aden")


#: The day's farm water on one field, actual work only (the farm ledger's definition of an
#: actual operation: completed and not dated after today, today being the ledger's local day).
#: ``measured`` counts the records that carry a volume; a record with hours but no volume is
#: water applied in an unknown amount. ``local_today`` is the ledger's local day.
FARM_WATER_DAY_SQL = (
    "SELECT (SELECT f.area_ha FROM fields f WHERE f.field_id = $2 AND f.tenant_id = $1::uuid)"
    " AS area_ha,"
    " (now() AT TIME ZONE $4)::date AS local_today,"
    " COUNT(w.water_record_id) AS records,"
    " COUNT(w.water_volume_m3) AS measured,"
    " SUM(w.water_volume_m3) AS volume_m3"
    " FROM farm_water_records w"
    " JOIN farm_operation_ledger o"
    " ON o.operation_id = w.operation_id AND o.tenant_id = w.tenant_id"
    " WHERE w.tenant_id = $1::uuid AND w.field_id = $2 AND w.record_date = $3"
    " AND o.status = 'completed' AND o.operation_date <= (now() AT TIME ZONE $4)::date"
)

# The W0-13 report semantics, for the farm ledger: only irrigation_mm is written, the reporter
# goes in irrigation_reported_by so the water-balance worker keeps the figure and recomputes the
# balance around it, and the day stays the worker's. The WHERE leaves any other writer's day
# alone (a person's full entry, an as-applied reconciliation): their figure is the authority for
# that day and the projection reports that it did not write. A re-projection of the same day
# replaces the figure (the day's sum, not an increment), so a retried or repeated projection
# never counts the same water twice.
FARM_LEDGER_IRRIGATION_UPSERT_SQL = (
    "INSERT INTO water_ledger"
    " (tenant_id, field_id, ledger_date, irrigation_mm, created_by, irrigation_reported_by,"
    " irrigation_source, created_at, updated_at)"
    " VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, now(), now())"
    " ON CONFLICT (field_id, ledger_date) DO UPDATE SET"
    " irrigation_mm = EXCLUDED.irrigation_mm,"
    " irrigation_reported_by = EXCLUDED.irrigation_reported_by,"
    " irrigation_source = EXCLUDED.irrigation_source,"
    " updated_at = now()"
    " WHERE water_ledger.created_by = EXCLUDED.created_by"
    " AND (water_ledger.irrigation_reported_by IS NULL"
    " OR water_ledger.irrigation_source IS NOT DISTINCT FROM EXCLUDED.irrigation_source)"
    " RETURNING 1"
)

#: Why the upsert above wrote nothing: another writer owns the day, or a person reported the
#: day's applied water (W0-13, ``irrigation_reported_by`` without the farm-ledger source). A
#: person's report is their own measurement of the day; the projection neither replaces it nor
#: takes the reporter column away from them.
FARM_LEDGER_DAY_OWNER_SQL = (
    "SELECT created_by, irrigation_reported_by, irrigation_source FROM water_ledger"
    " WHERE tenant_id = $1::uuid AND field_id = $2 AND ledger_date = $3"
)

#: A record of unknown volume makes the day's measured sum an understatement. A figure an earlier
#: projection wrote from the measured records alone would stay in the ledger as the day's
#: measured total, and the worker would keep it (it carries a reporter). It is withdrawn: the
#: figure, its reporter and its source are cleared, so the worker goes back to the
#: ``irrigation_runs`` evidence for that day (and says it is unobserved when there is none). Only
#: a farm-ledger figure on the worker's day is touched; a person's report or entry is left alone.
FARM_LEDGER_PROJECTION_WITHDRAW_SQL = (
    "UPDATE water_ledger SET irrigation_mm = NULL, irrigation_reported_by = NULL,"
    " irrigation_source = NULL, updated_at = now()"
    " WHERE tenant_id = $1::uuid AND field_id = $2 AND ledger_date = $3"
    " AND created_by = $4 AND irrigation_source = $5"
    " RETURNING 1"
)


async def project_farm_water_to_ledger(
    conn, *, tenant_id: str, field_id: str, record_date, reporter: str, auto_created_by: str
) -> dict:
    """Project the day's measured farm water on ``field_id`` onto ``water_ledger.irrigation_mm``.

    Runs on the caller's connection, inside its transaction (the farm operation and its ledger
    figure commit or roll back together). Writes nothing, and says why, when the day has no
    completed water record, when any record that day has no volume (the sum would understate the
    water and the worker would take it as the measured total; a figure an earlier projection
    wrote for that day is withdrawn), when the field has no area, when another writer owns the
    day, or when a person reported the day's applied water. Otherwise writes
    ``volume / area / 10`` mm with ``irrigation_source='farm_ledger'``.

    A day with no ledger row gets a row that carries the figure and no balance (the worker
    computes only its own today). The worker reads such an uncomputed row as a skipped day, not
    as the prior balance (``run_water_ledger_once``), so it never breaks the depletion chain.

    Projections of the same (tenant, field, day) are serialized by a transaction-scoped
    advisory lock taken before the day's sum, so concurrent operations never lose water.

    A day before the ledger's local today gets its figure, but the worker has already computed
    that day's balance and does not recompute it: the result carries
    ``balance_recomputed: False`` so the caller is not told the balance chain reflects it.
    """
    day = parse_ledger_date(record_date)
    await conn.execute(FARM_WATER_DAY_LOCK_SQL, farm_water_day_lock_key(tenant_id, field_id, day))
    row = await conn.fetchrow(FARM_WATER_DAY_SQL, tenant_id, field_id, day, ledger_timezone())
    base = {"ledger_date": day.isoformat(), "source": IRRIGATION_SOURCE_FARM_LEDGER}
    records = int(row["records"] or 0) if row else 0
    if not records:
        return {**base, "status": "skipped", "reason": "no_completed_water_record"}
    if int(row["measured"] or 0) < records:
        withdrawn = await conn.fetchval(
            FARM_LEDGER_PROJECTION_WITHDRAW_SQL,
            tenant_id,
            field_id,
            day,
            auto_created_by,
            IRRIGATION_SOURCE_FARM_LEDGER,
        )
        out = {**base, "status": "skipped", "reason": "unmeasured_water_record"}
        return {**out, "withdrawn_projection": True} if withdrawn else out
    volume = float(row["volume_m3"])
    area = None if row["area_ha"] is None else float(row["area_ha"])
    irrigation_mm = irrigation_mm_from_volume(volume, area)
    if irrigation_mm is None:
        return {**base, "status": "skipped", "reason": "field_area_unknown", "volume_m3": volume}
    stored = await conn.fetchval(
        FARM_LEDGER_IRRIGATION_UPSERT_SQL,
        tenant_id,
        field_id,
        day,
        irrigation_mm,
        auto_created_by,
        reporter,
        IRRIGATION_SOURCE_FARM_LEDGER,
    )
    out = {**base, "volume_m3": volume, "area_ha": area, "irrigation_mm": irrigation_mm}
    if stored is None:
        owner = await conn.fetchrow(FARM_LEDGER_DAY_OWNER_SQL, tenant_id, field_id, day)
        reason = (
            "day_reported_by_person"
            if owner is not None and owner["created_by"] == auto_created_by
            else "day_owned_by_another_writer"
        )
        return {**out, "status": "skipped", "reason": reason}
    local_today = row["local_today"]
    if local_today is not None and day < local_today:
        # W0-13 known limit: a past day's depletion is not recomputed, so later days' balance
        # does not yet reflect this water. Said, not hidden.
        return {
            **out,
            "status": "projected",
            "balance_recomputed": False,
            "reason": "past_day_balance_not_recomputed",
        }
    return {**out, "status": "projected"}
