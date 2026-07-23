"""تلخيص التغيّر الزمنيّ لمؤشّر حقل — منطق نقيّ (بلا إطار/شبكة).

يُستهلَك من أداة MCP ``analyze_field_change`` (المسار 1: MCP فوق CDSE). الأداة
تقرأ السلسلة الزمنيّة الحقيقيّة من raster-service (النقطة القانونيّة
``GET /v1/fields/{id}/timeseries``) ثمّ تُمرّر نقاطها هنا للمقارنة.

صدق صارم — يطابق فلسفة سهول:
  * لا يحسب طيفيّاً ولا يخترع قيمة؛ يقارن فقط ما جاء من raster-service.
  * النقاط بلا ``mean`` أو بسحاب مقيس > 30% (أو غير مقيس) تُستبعَد — كقاعدة
    المُركِّب القانونيّة (طبقة بلا سحاب مقيس ⇒ غير مؤهّلة، لا سحاب مختلَق).
  * أقلّ من مشاهدتَين مؤهّلتَين ⇒ ``InsufficientObservations`` (تُترجَم إلى 424
    عند الحافّة) — لا مقارنة مُلفّقة.
  * ``delta`` قياسٌ لا تفسير؛ التفسير الزراعيّ مسؤوليّة decision-service، لا هنا.
"""

from __future__ import annotations

from typing import Any

# عتبة NDVI صغيرة تفصل «تحسّن/تراجع» عن «مستقرّ» (تغيّر أقلّ منها ضِمن الضجيج).
STABLE_BAND = 0.02
# حدّ السحاب المقيس للمشاهدة المؤهّلة (نفس قاعدة المُركِّب القانونيّة).
MAX_CLOUD_PCT = 30.0


class InsufficientObservations(ValueError):
    """أقلّ من مشاهدتَين حقيقيّتَين مؤهّلتَين للمقارنة."""


def _qualified(points: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in points:
        mean = p.get("mean")
        if mean is None:
            continue
        cloud = p.get("cloud_pct")
        # سحاب غير مقيس (None) ⇒ غير مؤهّل (لا نفترض سماءً صافيةً).
        if cloud is None or float(cloud) > MAX_CLOUD_PCT:
            continue
        date = str(p.get("datetime") or p.get("date") or "")[:10]
        if not date:
            continue
        if since and date < str(since)[:10]:
            continue
        out.append({"date": date, "mean": float(mean)})
    out.sort(key=lambda r: r["date"])
    return out


def summarize_field_change(
    points: list[dict[str, Any]],
    *,
    field_id: str,
    tenant_id: str,
    index: str = "ndvi",
    since: str | None = None,
) -> dict[str, Any]:
    """يقارن أوّل وآخر مشاهدة مؤهّلة ويعيد ملخّص التغيّر. يرفع
    ``InsufficientObservations`` إن قلّت المشاهدات المؤهّلة عن اثنتين."""
    real = _qualified(points, since)
    if len(real) < 2:
        raise InsufficientObservations(
            f"insufficient authoritative observations for {field_id}/{index} "
            f"(qualified={len(real)}, since={since or 'all'})"
        )
    first, last = real[0], real[-1]
    delta = round(last["mean"] - first["mean"], 4)
    if delta > STABLE_BAND:
        direction = "improving"
    elif delta < -STABLE_BAND:
        direction = "declining"
    else:
        direction = "stable"
    return {
        "field_id": field_id,
        "tenant_id": tenant_id,
        "index": index,
        "from": first,
        "to": last,
        "delta": delta,
        "direction": direction,
        "observations_used": len(real),
        "source": "raster-service",
        "real_data": True,
        # لا تفسير زراعيّ هنا — delta قياسٌ فقط؛ التفسير في decision-service.
    }
