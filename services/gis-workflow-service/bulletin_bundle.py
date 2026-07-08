"""bulletin_bundle.py — حزمة نشر النشرة الإقليميّة القابلة للتدقيق (الشريحة C، V86).

يعيد استخدام آليّة التدقيق في V85 (run_id فريد · no-overwrite · checksums · manifest) لإنتاج
حزمة نشر لشكل النشرة الإقليميّة التصنيفيّ فوق مخرَج ``build_regional_bulletin``.

**صدق حاسم:** المانيفست يُعلن ``representation='categorical_figure'`` و``geographic=False`` —
هذه **ليست خريطة choropleth** (لا حدود إداريّة في المستودع). لا مصادر خارجيّة.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from bulletin_figure import bulletin_self_checks, bulletin_to_rows
from run_bundle import _sha256, _write_json, compact_ts


def make_bulletin_run_id(ts_iso: str) -> str:
    return f"{compact_ts(ts_iso)}_regional_bulletin_publication"


def _methodology_md(bulletin: dict[str, Any], render_ok: bool) -> str:
    return (
        "# المنهجيّة\n\n"
        "- المصدر: `core.regional_bulletin.build_regional_bulletin` (تجميع NDVI على مستوى "
        "محافظة/مديريّة من مخرجات ساهول — **لا جلب خارجيّ**).\n"
        f"- التمثيل: **شكل تصنيفيّ** (حالة NDVI بالألوان) — **ليس خريطة جغرافيّة** "
        "(لا حدود إداريّة/choropleth في المستودع).\n"
        f"- الرسم: {'أُنتِج' if render_ok else '**فشل** — الحزمة failed'} عبر matplotlib Agg.\n"
        f"- أرضيّة الخصوصيّة: {bulletin.get('privacy_floor_fields')} حقل — المجموعات دونها مكتومة بلا أرقام.\n\n"
        "صدق: لا تلفيق جغرافيا؛ المكتوم يبقى «مكتوم»؛ لا ادّعاء choropleth لم يُنفَّذ.\n"
    )


def _report_md_quality(sc: dict[str, Any]) -> str:
    lines = [
        f"# تقرير الجودة\n\nالجودة: **{sc['quality']}** · نجح: {sc['passed']}\n",
        "| الفحص | الأهمّية | النتيجة | التفصيل |",
        "|---|---|---|---|",
    ]
    for c in sc["checks"]:
        mark = "✅" if c["passed"] else ("⏭️" if c["passed"] is None else "❌")
        lines.append(f"| {c['name']} | {c['severity']} | {mark} | {c['detail']} |")
    return "\n".join(lines) + "\n"


def run_bulletin_bundle(
    bulletin: dict[str, Any],
    *,
    root: str | Path,
    ts_iso: str,
    title: str = "النشرة الإقليميّة — حالة NDVI",
    render_fn: Callable[..., bytes] | None = None,
    evidence_writer: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """يُنتِج حزمة نشر للنشرة (لا-تُكتَب-فوقها) ويُعيد ``{status, run_id, run_dir, ...}``.

    ``run_id`` موجود ⇒ ``FileExistsError``. فشل الرسم ⇒ ``status='failed'`` دون كسر الحزمة.
    ``status``: completed / degraded (فشل quality) / failed (فشل required أو الرسم).
    """
    if not isinstance(bulletin, dict) or bulletin.get("schema") != "sahool.regional_bulletin/1":
        raise ValueError("bulletin must be a build_regional_bulletin output (schema mismatch)")

    run_id = make_bulletin_run_id(ts_iso)
    run_dir = Path(root) / "gis-workflows" / "regional_bulletin" / run_id
    if run_dir.exists():
        raise FileExistsError(f"run already exists (no-overwrite): {run_dir}")
    for sub in ("maps", "data", "reports", "scripts", "provenance"):
        (run_dir / sub).mkdir(parents=True)

    rows = bulletin_to_rows(bulletin)
    sc = bulletin_self_checks(bulletin)

    render_ok, render_error = False, None
    try:
        renderer = render_fn or _default_bulletin_renderer()
        caption = f"الفترة: {bulletin.get('period') or 'غير متاح'} · أرضيّة الخصوصيّة: {bulletin.get('privacy_floor_fields')}"
        png = renderer(rows, title=title, caption=caption)
        (run_dir / "maps" / "regional_bulletin_publication.png").write_bytes(png)
        render_ok = True
    except Exception as exc:  # noqa: BLE001 — فشل الرسم ⇒ failed، لا كسر النظام.
        render_error = str(exc)

    _write_json(run_dir / "data" / "summary.json", bulletin)
    _write_json(run_dir / "scripts" / "figure_rows.json", rows)
    (run_dir / "reports" / "methodology.md").write_text(
        _methodology_md(bulletin, render_ok), "utf-8"
    )
    (run_dir / "reports" / "quality_report.md").write_text(_report_md_quality(sc), "utf-8")
    (run_dir / "reports" / "self_check.md").write_text(_report_md_quality(sc), "utf-8")

    status = (
        "failed"
        if (not render_ok or not sc["passed"])
        else ("degraded" if sc["quality"] == "degraded" else "completed")
    )

    _write_json(
        run_dir / "provenance" / "sources.json",
        {"source": "core.regional_bulletin", "external_fetch": False, "geographic": False},
    )
    checksums = {
        str(p.relative_to(run_dir)): _sha256(p) for p in sorted(run_dir.rglob("*")) if p.is_file()
    }
    _write_json(run_dir / "provenance" / "checksums.json", checksums)

    manifest = {
        "workflow_id": "regional_bulletin_publication",
        "run_id": run_id,
        "created_at": ts_iso,
        "status": status,
        "representation": "categorical_figure",
        "geographic": False,
        "geographic_blocker": "no_admin_boundaries_in_repo",
        "external_fetch": False,
        "period": bulletin.get("period"),
        "governorate_count": bulletin.get("governorate_count"),
        "published_governorates": bulletin.get("published_governorates"),
        "suppressed_governorates": bulletin.get("suppressed_governorates"),
        "privacy_floor_fields": bulletin.get("privacy_floor_fields"),
        "self_check": {"passed": sc["passed"], "quality": sc["quality"], "checks": sc["checks"]},
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


def _default_bulletin_renderer() -> Callable[..., bytes]:
    from bulletin_render import render_bulletin_figure_png  # noqa: PLC0415

    return render_bulletin_figure_png
