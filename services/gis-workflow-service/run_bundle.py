"""run_bundle.py — حزمة تشغيل الـWorkflow القابلة للتدقيق (الشريحة B، V85).

طبقة **تشغيل/تدقيق/تغليف** فوق رِندرِر V84 ومخرجات raster-service الحاليّة — **لا محرّك
بيانات جديد**. لكلّ تشغيل ``run_id`` فريد وحزمة كاملة (maps/data/reports/scripts/provenance)
**لا تُكتَب فوق تشغيل سابق أبداً**، مع فحوص ذاتيّة حقيقيّة وchecksums ومانيفست نَسَب.

**حظر الشريحة B:** لا مصادر خارجيّة (GEE/earthaccess/WaPOR/WorldCereal/HLS) — يعمل فقط على
مصفوفة قيم راستريّة مُمرَّرة (من COG/أصل راستر ساهول). الرِندرِر يُحقَن (افتراضه V84).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from self_checks import run_self_checks
from workflow_spec import resolve_spec, validate_spec

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _slug(value: Any, fallback: str = "x") -> str:
    s = _SAFE.sub("_", str(value or "")).strip("_")
    return s or fallback


def compact_ts(ts_iso: str) -> str:
    """``2026-07-08T15:30:22Z`` ⇒ ``20260708T153022Z`` (يُمرَّر الوقت — لا ساعة داخليّة)."""
    return _SAFE.sub("", ts_iso.replace("-", "").replace(":", ""))


def make_run_id(spec: dict[str, Any], ts_iso: str) -> str:
    """معرّف تشغيل فريد: ``{ts}_{target}_{index}_publication`` (يمنع التصادم زمنيّاً)."""
    target = spec.get("target") or {}
    tgt = target.get("field_id") if target.get("type") == "field" else target.get("aoi")
    idx = (spec.get("analysis") or {}).get("index", "idx")
    return f"{compact_ts(ts_iso)}_{_slug(tgt, 'target')}_{_slug(idx, 'index')}_publication"


def array_stats(values: Any) -> dict[str, Any]:
    """إحصاءات المصفوفة (min/max/nodata_ratio/valid_pixel_ratio/shape) — nodata = NaN.

    يتطلّب numpy؛ غيابه/فشله ⇒ dict فارغ (الفحوص تتخطّى ما لا يُقاس، لا تلفيق).
    """
    try:
        import numpy as np  # noqa: PLC0415

        arr = np.asarray(values, dtype="float64")
        if arr.ndim != 2 or arr.size == 0:
            return {}
        total = int(arr.size)
        nodata = int(np.count_nonzero(np.isnan(arr)))
        valid = total - nodata
        finite = arr[np.isfinite(arr)]
        out: dict[str, Any] = {
            "shape": [int(arr.shape[0]), int(arr.shape[1])],
            "nodata_ratio": nodata / total if total else None,
            "valid_pixel_ratio": valid / total if total else None,
        }
        if finite.size:
            out["min"] = float(finite.min())
            out["max"] = float(finite.max())
        return out
    except Exception:  # noqa: BLE001 — بلا numpy: تُتخطّى الفحوص المعتمِدة على الإحصاء.
        return {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _checks_md(sc: dict[str, Any]) -> str:
    lines = [
        "# فحص ذاتيّ (self-check)",
        "",
        f"الحالة: **{sc['quality']}** · نجح: {sc['passed']}",
        "",
    ]
    lines.append("| الفحص | الأهمّية | النتيجة | التفصيل |")
    lines.append("|---|---|---|---|")
    for c in sc["checks"]:
        mark = "✅" if c["passed"] else ("⏭️" if c["passed"] is None else "❌")
        lines.append(f"| {c['name']} | {c['severity']} | {mark} | {c['detail']} |")
    return "\n".join(lines) + "\n"


def _quality_md(sc: dict[str, Any], meta: dict[str, Any]) -> str:
    missing = [c["name"] for c in sc["checks"] if c["passed"] is None]
    lines = [
        "# تقرير الجودة",
        "",
        f"الجودة الإجماليّة: **{sc['quality']}**",
        f"- فحوص required فاشلة: {sc['n_failed_required']}",
        f"- فحوص quality فاشلة: {sc['n_failed_quality']}",
        f"- فحوص متخطّاة (بيانات غائبة): {', '.join(missing) if missing else 'لا شيء'}",
        "",
        "البيانات الوصفيّة المُستخدَمة (الناقص يُخفِّض الجودة صراحةً):",
    ]
    for k in (
        "provider",
        "scene_id",
        "acquisition_date",
        "crs",
        "resolution_m",
        "valid_pixel_ratio",
    ):
        lines.append(f"- {k}: {meta.get(k, 'غير متاح')}")
    return "\n".join(lines) + "\n"


def _methodology_md(spec: dict[str, Any], render_ok: bool) -> str:
    a = spec.get("analysis") or {}
    return (
        "# المنهجيّة\n\n"
        f"- المؤشّر: {a.get('index')}\n"
        f"- المصدر: {a.get('source')} (مخرجات ساهول الحاليّة — **لا جلب خارجيّ**)\n"
        "- الرسم: رِندرِر خرائط النشر V84 (matplotlib Agg).\n"
        f"- خريطة النشر: {'أُنتِجت' if render_ok else '**فشل الرسم** — الحزمة failed'}\n\n"
        "صدق: هذه الحزمة طبقة تشغيل/تدقيق فوق أصل راستر موجود؛ لا تدّعي تحليلاً أو مصدراً "
        "لم يُنفَّذ. لا GEE/earthaccess/WaPOR/WorldCereal/HLS في هذه الشريحة.\n"
    )


def run_workflow_bundle(
    spec: Any,
    values: Any,
    meta: dict[str, Any],
    *,
    root: str | Path,
    ts_iso: str,
    stats: dict[str, Any] | None = None,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    render_fn: Callable[..., bytes] | None = None,
    evidence_writer: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """يُنتِج حزمة تشغيل كاملة لا-تُكتَب-فوقها ويُعيد ``{status, run_id, run_dir, ...}``.

    ``spec`` شاذّ ⇒ ``ValueError`` بسبب. ``run_id`` موجود مسبقاً ⇒ ``FileExistsError`` (لا
    overwrite). فشل الرِندرِر ⇒ ``status='failed'`` دون كسر بقيّة الحزمة (تُكتَب التقارير
    والنَّسَب). ``status``: completed / degraded (فشل quality) / failed (فشل required أو الرسم).
    """
    ok, reason = validate_spec(spec)
    if not ok:
        raise ValueError(f"invalid workflow spec: {reason}")
    resolved = resolve_spec(spec)
    meta = meta if isinstance(meta, dict) else {}

    run_id = make_run_id(resolved, ts_iso)
    run_dir = Path(root) / "gis-workflows" / _slug(resolved["workflow_id"], "wf") / run_id
    if run_dir.exists():
        raise FileExistsError(f"run already exists (no-overwrite): {run_dir}")
    for sub in ("maps", "data", "reports", "scripts", "provenance"):
        (run_dir / sub).mkdir(parents=True)

    if stats is None:
        stats = array_stats(values)
    sc = run_self_checks(resolved, meta, stats)

    # الرسم عبر رِندرِر V84 (يُحقَن أو الافتراضيّ) — فشله لا يكسر الحزمة.
    render_ok, render_error, map_rel = False, None, None
    try:
        renderer = render_fn or _default_renderer()
        from map_layout import build_map_layout  # noqa: PLC0415

        ncols = (stats.get("shape") or [0, 0])[1]
        res = meta.get("resolution_m")
        width_m = (float(res) * ncols) if (res and ncols) else None
        layout = build_map_layout(
            {
                "title": resolved["workflow_id"],
                "map_width_m": width_m,
                "classes": resolved.get("outputs", {}).get("classes"),
                "meta": {**meta, "index": resolved["analysis"]["index"]},
            }
        )
        png = renderer(values, layout, cmap=cmap, vmin=vmin, vmax=vmax)
        map_rel = f"maps/{_slug(resolved['analysis']['index'], 'index')}_publication.png"
        (run_dir / map_rel).write_bytes(png)
        render_ok = True
    except Exception as exc:  # noqa: BLE001 — فشل الرسم ⇒ failed، لا كسر النظام.
        render_error = str(exc)

    # data + scripts + reports.
    _write_json(
        run_dir / "data" / "summary.json",
        {"index": resolved["analysis"]["index"], "stats": stats, "target": resolved["target"]},
    )
    _write_json(run_dir / "scripts" / "resolved_spec.json", resolved)
    (run_dir / "reports" / "methodology.md").write_text(
        _methodology_md(resolved, render_ok), "utf-8"
    )
    (run_dir / "reports" / "quality_report.md").write_text(_quality_md(sc, meta), "utf-8")
    (run_dir / "reports" / "self_check.md").write_text(_checks_md(sc), "utf-8")

    status = (
        "failed"
        if (not render_ok or not sc["passed"])
        else ("degraded" if sc["quality"] == "degraded" else "completed")
    )

    # provenance: المصادر + checksums + المانيفست الكامل.
    _write_json(
        run_dir / "provenance" / "sources.json",
        {
            "source": resolved["analysis"]["source"],
            "external_fetch": False,
            "provider": meta.get("provider"),
            "scene_id": meta.get("scene_id"),
            "cog_uri": meta.get("cog_uri"),
        },
    )
    checksums = {
        str(p.relative_to(run_dir)): _sha256(p) for p in sorted(run_dir.rglob("*")) if p.is_file()
    }
    _write_json(run_dir / "provenance" / "checksums.json", checksums)

    manifest = {
        "workflow_id": resolved["workflow_id"],
        "run_id": run_id,
        "created_at": ts_iso,
        "status": status,
        "target": resolved["target"],
        "index": resolved["analysis"]["index"],
        "source": resolved["analysis"]["source"],
        "external_fetch": False,
        "provider": meta.get("provider"),
        "scene_id": meta.get("scene_id"),
        "acquisition_date": meta.get("acquisition_date"),
        "crs": meta.get("crs"),
        "resolution_m": meta.get("resolution_m"),
        "valid_pixel_ratio": meta.get("valid_pixel_ratio"),
        "self_check": {
            "passed": sc["passed"],
            "quality": sc["quality"],
            "checks": sc["checks"],
        },
        "render_ok": render_ok,
        "render_error": render_error,
        "outputs": sorted(checksums.keys()),
    }
    _write_json(run_dir / "provenance" / "run_manifest.json", manifest)

    if evidence_writer is not None:
        try:
            evidence_writer(manifest)
        except Exception:  # noqa: BLE001 — ربط الأدلّة اختياريّ fail-soft.
            pass

    return {
        "status": status,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "render_ok": render_ok,
        "self_check": sc,
        "outputs": sorted(checksums.keys()),
    }


def _default_renderer() -> Callable[..., bytes]:
    from publication_map import render_publication_png  # noqa: PLC0415

    return render_publication_png
