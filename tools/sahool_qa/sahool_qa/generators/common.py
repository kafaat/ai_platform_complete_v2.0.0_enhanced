"""Context cards and evidence references.

`Cards` renders the raw records an agent would retrieve (never derived values)
and remembers which fields own them. make_item turns that — plus every
evidence record — into the item's dependency set, so a record from a held-out
field can never sit in a training item's context or evidence (F03/F04).
"""

from __future__ import annotations

import json
from collections import defaultdict

from ..arabic import quote
from ..facts import Field, Indicator, SoilSample

NA = "غير مسجّل"


def v(x, nd: int | None = None, unit: str = "") -> str:
    if x is None:
        return NA
    s = (
        f"{x:.{nd}f}"
        if nd is not None and isinstance(x, float)
        else (f"{x:g}" if isinstance(x, float) else str(x))
    )
    return f"{s} {unit}".strip()


def _qc_or(val, rec, attr, unit=""):
    if val is None and attr in rec.qc:
        return f"مرفوض بفحص الجودة (القيمة الخام {rec.qc[attr]['raw']})"
    return v(val, None, unit)


def field_card(f: Field, with_geom: bool = False) -> str:
    parts = [
        f"حقل {quote(f.display)} [field_id={f.id}]",
        f"المستأجر: {v(f.tenant)}",
        f"المحافظة: {v(f.governorate)}",
        f"المحصول: {v(f.crop)}",
        f"المساحة المسجّلة: {v(f.area_ha_stored, None, 'هكتار')}",
    ]
    if f.lat is not None and f.lon is not None:
        parts.append(f"نقطة الموقع (lon, lat): {f.lon}, {f.lat}")
    line = " — ".join(parts)
    if with_geom:
        if f.geom is not None:
            line += "\nالحدود المرسومة (GeoJSON، WGS84): " + json.dumps(
                f.geom.to_geojson(6), ensure_ascii=False, separators=(",", ":")
            )
        elif f.geom_raw is not None:
            line += "\nالحدود المرسومة: مرفوضة بفحص الهندسة (" + "؛ ".join(f.geom_problems) + ")"
        else:
            line += "\nالحدود المرسومة: لا توجد"
    return line


def sample_card(s: SoilSample) -> str:
    loc = f"{s.point[0]:.6f}, {s.point[1]:.6f}" if s.point else NA
    ts = s.recorded_ts.isoformat(sep=" ") if s.recorded_ts else NA
    return (
        f"عينة تربة {s.sample_id} [field_id={s.field_id}] — المستأجر: {v(s.tenant)}؛ الوقت: {ts}؛ العمق: {_qc_or(s.depth_cm, s, 'depth_cm', 'سم')}؛ "
        f"pH: {_qc_or(s.ph, s, 'ph')}؛ EC: {_qc_or(s.ec, s, 'ec', 'dS/m')}؛ N: {_qc_or(s.n, s, 'n', 'mg/kg')}؛ "
        f"P: {_qc_or(s.p, s, 'p', 'mg/kg')}؛ K: {_qc_or(s.k, s, 'k', 'mg/kg')}؛ مادة عضوية: {_qc_or(s.om, s, 'om', '%')}؛ "
        f"المصدر: {v(s.source)}؛ الإحداثيات (lon, lat): {loc}"
    )


def indicator_card(i: Indicator) -> str:
    loc = f"{i.point[0]:.6f}, {i.point[1]:.6f}" if i.point else NA
    ts = i.recorded_ts.isoformat(sep=" ") if i.recorded_ts else NA
    val = _qc_or(i.value, i, "value", i.unit or "")
    return (
        f"مؤشر {i.indicator_id} [field_id={i.field_id}] — المستأجر: {v(i.tenant)}؛ الفئة: {v(i.category)}؛ القيمة: {val}؛ "
        f"الوقت: {ts}؛ المصدر: {v(i.source)}؛ الإحداثيات: {loc}"
    )


class Cards:
    """Context builder that tracks the owning field of every rendered record."""

    def __init__(self):
        self.lines: list[str] = []
        self.keys: set[str] = set()

    def field(self, f: Field, geom: bool = False) -> Cards:
        self.lines.append(field_card(f, geom))
        self.keys.add(f.key)
        return self

    def fields(self, fs, geom: bool = False) -> Cards:
        for f in fs:
            self.field(f, geom)
        return self

    def samples(self, ss) -> Cards:
        for s in sorted(ss, key=lambda s: s.key):
            self.lines.append(sample_card(s))
            self.keys.add(s.field_key)
        return self

    def indicators(self, inds) -> Cards:
        for i in sorted(inds, key=lambda i: i.key):
            self.lines.append(indicator_card(i))
            self.keys.add(i.field_key)
        return self

    def text(self, t: str) -> Cards:
        self.lines.append(t)
        return self

    def table(self, t: str, recs) -> Cards:
        """A compact rendering of raw records (e.g. a daily table); their owners become dependencies."""
        self.lines.append(t)
        for r in recs:
            self.keys.add(r.field_key)
        return self

    def render(self) -> str:
        return "\n".join(self.lines)


def sample_ref(s: SoilSample) -> dict:
    return {
        "table": "soil_readings",
        "field_key": s.field_key,
        "field_id": s.field_id,
        "sample_id": s.sample_id,
        "recorded_at": s.recorded_ts.isoformat() if s.recorded_ts else None,
        "record_id": s.record_id,
    }


def indicator_ref(i: Indicator) -> dict:
    return {
        "table": "field_indicators",
        "field_key": i.field_key,
        "field_id": i.field_id,
        "indicator_id": i.indicator_id,
        "recorded_at": i.recorded_ts.isoformat() if i.recorded_ts else None,
        "record_id": i.record_id,
    }


def field_ref(f: Field) -> dict:
    return {"table": "field_boundaries", "field_key": f.key, "field_id": f.id}


def by_year(pairs: list[tuple[SoilSample, str]]) -> dict[int, list[SoilSample]]:
    out: dict[int, dict[str, SoilSample]] = defaultdict(dict)
    for s, _ in pairs:
        if s.year is not None:
            out[s.year][s.key] = s
    return {y: sorted(d.values(), key=lambda s: s.key) for y, d in out.items()}


def methods(pairs) -> list[str]:
    return sorted({m for _, m in pairs})


def method_note(ms: list[str]) -> str:
    notes = {
        "spatial": "ربط مكاني: نقطة العينة داخل حدود الحقل (ST_Contains) وعلى بعد متر على الأقل من الحد",
        "field_id": "ربط بالمعرّف: العينة مسجّلة بنفس (tenant_id، field_id)",
    }
    return "؛ ".join(notes[m] for m in ms)


EC_CAVEAT = (
    "طريقة استخلاص EC غير مسجّلة في المخطط (عجينة مشبعة ECe أم 1:1 / 1:5)؛ "
    "العتبات تفترض ECe كما في FAO 29 Rev.1 القسم 2.4"
)
