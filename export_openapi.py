#!/usr/bin/env python3
"""
export_openapi.py — تصدير مواصفات OpenAPI لخدمات SAHOOL (FastAPI)، بإغلاقٍ عند الفشل.

يستدعي app.openapi() لكلّ خدمة (بلا تشغيل uvicorn) ويحفظ JSON في docs/openapi/.

الاستخدام (من أيّ مكان):
    python3 export_openapi.py [--out-dir DIR] [--inventory FILE] [--timeout SEC]

مصدر قائمة الخدمات: ``service_inventory.generated.json`` (يولّده
``scripts/ci/generate_service_inventory.py`` ويحرس انجرافَه workflow
``service-inventory-drift``). لا قائمة يدويّة ثانية للخدمات هنا؛ هذا الملفّ يُعلن
التصنيف فقط:

- ``REQUIRED``: فشلُ تصديرها (استيراد أو ``openapi()``) يُنهي السكربت برمز غير صفريّ
  ويُسمّي الخدمة والخطأ.
- ``OPTIONAL``: تحتاج حزماً أو بنيةً خارج بيئة المنصّة؛ تخطّيها مسموح لكنّه يُعلَن
  في الملخّص وفي ``EXPORT_SUMMARY.json`` وفي ``INDEX.md``، لا صامتاً.
- خدمة في السجلّ بلا ``main`` (``"-"``) ليست تطبيق ASGI: تُسجَّل ``not_asgi``.
- خدمة في السجلّ لا تصنيف لها: خطأ سجلّ (رمز 2) قبل أيّ تصدير، حتى لا تدخل خدمة
  جديدة بلا قرار.

كلّ خدمة تُصدَّر في عمليّة فرعيّة مستقلّة: التحميل في عمليّة واحدة يُسرّب وحدات
``routers``/``config`` المخبّأة من خدمة إلى التالية فتُصدَّر مسارات خدمة أخرى بصمت.

رموز الخروج: 0 كلّ الإلزاميّة صُدِّرت · 1 فشلت خدمة إلزاميّة · 2 خطأ في السجلّ/التصنيف.

المخرجات:
    <out>/<service>.openapi.json   لكلّ خدمة صُدِّرت
    <out>/INDEX.md                  فهرس موحّد للمسارات + المتخطّاة والفاشلة
    <out>/EXPORT_SUMMARY.json       العدّ والتصنيف وأسباب التخطّي/الفشل
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

# صار يُشغَّل في CI (C-04)، ومخرَجُه عربيٌّ ويحمل ✓/✗/⚠: تحت `LC_ALL=C` بلا `PYTHONUTF8`
# يُرمّز `print` بـASCII فيموت بـUnicodeEncodeError — نتيجةٌ صحيحة تُقرَأ فشلاً. والعمليّةُ
# الفرعيّة لكلّ خدمة تُحمّل هذا الملفّ نفسه، فتَرِث التهيئةَ ذاتها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INVENTORY = os.path.join(ROOT, "service_inventory.generated.json")
DEFAULT_ROUTE_INVENTORY = os.path.join(ROOT, "route_inventory.generated.json")
DEFAULT_OUT_DIR = os.path.join(ROOT, "docs", "openapi")
DEFAULT_TIMEOUT = 300

EXIT_OK = 0
EXIT_REQUIRED_FAILED = 1
EXIT_REGISTRY_ERROR = 2

# الخدمات التي يجب أن تُصدَّر في بيئة المنصّة الكاملة (requirements المنصّة).
# قِيسَت في 13 نوفمبر 2026: كلّها تُستورد ويعمل app.openapi() في عمليّة مستقلّة.
REQUIRED = frozenset(
    {
        "actuator-service",
        "agriai-engine",
        "auth",
        "decision-service",
        "edge-inference",
        "field-management-service",
        "field-segmentation",
        "guardrails-engine",
        "indicators-service",
        "knowledge-graph",
        "odoo-bridge",
        "raster-service",
        "realtime-session",
        "remote-sensing-workspace-bff",
        "sahool-platform",
        "sam2-inference",
        "scout-ingest-service",
        "soil-service",
        "supervisor-agent",
        "vegetation-analysis-service",
        "video-processor",
        "weather-service",
    }
)

# خدمات يُسمح بتخطّيها، مع سبب مُعلَن (يظهر في الملخّص).
OPTIONAL = {
    "ai_agronomist": "main.py uses package-relative imports; not loadable as a file",
    "local-ai-rag": "needs langchain_community (not in platform requirements)",
    "rag-retrieval": "imports `core`, which only its container image provides",
    "raster-tiler-service": "needs titiler (not in platform requirements)",
    "realtime-agent": "worker entrypoint; main.py defines no ASGI `app`",
    "tts-service": "needs edge_tts (not in platform requirements)",
    "weather-signal-engine": "worker; imports `core` from its image and defines no `app`",
}


# خدماتٌ تكتب حالتها المحلّيّة عند الاستيراد إلى مسارٍ داخل صورتها (مثل ``/data``). في عمليّة
# التصدير لا تملك ذلك المسار (مُشغِّل CI ليس root)، فتُوجَّه متغيّراتُها المُعلَنة إلى مجلّد
# مؤقّت خاصّ بكلّ تشغيل. لا يُغيِّر هذا ما تُصدِّره: المخطّط يُشتقّ من المسارات لا من الحالة.
IMPORT_ENV_PATHS = {
    "knowledge-graph": {"KG_SQLITE_PATH": "kg.sqlite"},
}


class RegistryError(Exception):
    """السجلّ غير مقروء أو التصنيف لا يطابقه."""


def load_inventory(path: str) -> list[tuple[str, str | None]]:
    """يقرأ سجلّ الخدمات ويعيد [(service, main_path أو None)]."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise RegistryError(f"cannot read service inventory {path}: {e}") from e
    if not isinstance(data, list):
        raise RegistryError(f"service inventory {path} is not a JSON list")
    out = []
    for row in data:
        svc = row.get("service")
        main = row.get("main")
        if not svc:
            raise RegistryError(f"inventory row without a service name: {row!r}")
        out.append((svc, None if main in (None, "", "-") else main))
    return out


def classify(inventory: list[tuple[str, str | None]]) -> dict[str, str]:
    """يعيد {service: required|optional|not_asgi} أو يرفع RegistryError."""
    names = {svc for svc, _ in inventory}
    problems = []
    for svc in sorted((REQUIRED | set(OPTIONAL)) - names):
        problems.append(f"{svc}: classified but absent from the service inventory")
    for svc in sorted(REQUIRED & set(OPTIONAL)):
        problems.append(f"{svc}: listed as both REQUIRED and OPTIONAL")
    result = {}
    for svc, main in inventory:
        if svc in REQUIRED:
            if main is None:
                problems.append(f"{svc}: REQUIRED but the inventory has no main for it")
            result[svc] = "required"
        elif svc in OPTIONAL:
            result[svc] = "optional"
        elif main is None:
            result[svc] = "not_asgi"
        else:
            problems.append(f"{svc}: has {main} but is neither REQUIRED nor OPTIONAL")
    if problems:
        raise RegistryError("; ".join(problems))
    return result


def static_route_counts(path: str) -> dict[str, int]:
    """عدد المسارات الساكنة لكلّ خدمة (للمقارنة في الملخّص فقط)."""
    try:
        with open(path, encoding="utf-8") as f:
            return dict(Counter(r.get("service") for r in json.load(f)))
    except (OSError, ValueError, AttributeError):
        return {}


def load_app(service: str, main_path: str):
    """يحمّل كائن app من main_path بلا تشغيل الخادم (داخل العمليّة الحاليّة)."""
    abs_main = os.path.join(ROOT, main_path)
    if not os.path.exists(abs_main):
        return None, f"{main_path} not found"
    svc_dir = os.path.dirname(abs_main)
    sys.path.insert(0, svc_dir)
    sys.path.insert(0, ROOT)
    mod_name = f"_svc_{service.replace('-', '_')}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, abs_main)
        mod = importlib.util.module_from_spec(spec)
        # pydantic/dataclasses تحلّ المراجع الأماميّة عبر sys.modules[__module__].
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        app = getattr(mod, "app", None)
        if app is None:
            return None, "module defines no `app`"
        return app, None
    except BaseException as e:  # noqa: BLE001 — SystemExit من استيراد خدمة فشلٌ أيضاً
        return None, f"{type(e).__name__}: {e}"
    finally:
        for p in (svc_dir, ROOT):
            if p in sys.path:
                sys.path.remove(p)


def _child(service: str, main_path: str, out_file: str) -> int:
    """مدخل العمليّة الفرعيّة: يحمّل الخدمة ويكتب app.openapi() إلى out_file."""
    app, err = load_app(service, main_path)
    if app is None:
        sys.stderr.write(f"EXPORT-ERROR import: {err}\n")
        return 3
    try:
        spec = app.openapi()
    except BaseException as e:  # noqa: BLE001
        sys.stderr.write(f"EXPORT-ERROR openapi(): {type(e).__name__}: {e}\n")
        return 4
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    return 0


def export_one(service: str, main_path: str, timeout: int = DEFAULT_TIMEOUT):
    """يصدّر خدمة واحدة في عمليّة فرعيّة. يعيد (spec, None) أو (None, error)."""
    fd, tmp = tempfile.mkstemp(suffix=".openapi.json")
    os.close(fd)
    state_dir = tempfile.mkdtemp(prefix=f"openapi-{service}-")
    env = dict(os.environ)
    for var, name in IMPORT_ENV_PATHS.get(service, {}).items():
        env[var] = os.path.join(state_dir, name)
    try:
        try:
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--child", service, main_path, tmp],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, f"timed out after {timeout}s"
        if proc.returncode != 0:
            lines = [ln for ln in proc.stderr.splitlines() if ln.startswith("EXPORT-ERROR")]
            tail = lines[-1] if lines else " | ".join(proc.stderr.strip().splitlines()[-3:])
            return None, f"exit {proc.returncode}: {tail or 'no error output'}"
        with open(tmp, encoding="utf-8") as f:
            return json.load(f), None
    finally:
        os.unlink(tmp)
        shutil.rmtree(state_dir, ignore_errors=True)


def run_export(inventory, classes, out_dir, timeout, static_counts):
    """يصدّر كلّ خدمة ASGI ويعيد الملخّص (dict)."""
    exported, optional_skipped, required_failed, not_asgi = [], [], [], []
    for svc, main in inventory:
        cls = classes[svc]
        if cls == "not_asgi":
            not_asgi.append({"service": svc, "static_routes": static_counts.get(svc, 0)})
            continue
        spec, err = export_one(svc, main, timeout)
        if spec is None:
            entry = {"service": svc, "error": err, "static_routes": static_counts.get(svc, 0)}
            if cls == "required":
                required_failed.append(entry)
                print(f"  ✗ {svc} (REQUIRED): {err}")
            else:
                entry["reason"] = OPTIONAL[svc]
                optional_skipped.append(entry)
                print(f"  ⚠ {svc} (optional): skipped ({err})")
            continue
        out_path = os.path.join(out_dir, f"{svc}.openapi.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        paths = spec.get("paths", {})
        exported.append(
            {
                "service": svc,
                "class": cls,
                "paths": len(paths),
                "operations": sum(1 for m in paths.values() for k in m if k != "parameters"),
                "static_routes": static_counts.get(svc, 0),
                "_spec_paths": paths,
            }
        )
        print(f"  ✓ {svc}: {len(paths)} paths → {out_path}")
    return build_summary(classes, exported, optional_skipped, required_failed, not_asgi)


def build_summary(classes, exported, optional_skipped, required_failed, not_asgi):
    counts = Counter(classes.values())
    return {
        "status": "failed" if required_failed else "ok",
        "inventory_source": "service_inventory.generated.json",
        "counts": {
            "inventory_services": len(classes),
            "required": counts.get("required", 0),
            "optional": counts.get("optional", 0),
            "not_asgi": counts.get("not_asgi", 0),
            "exported": len(exported),
            "exported_required": sum(1 for e in exported if e["class"] == "required"),
            "exported_optional": sum(1 for e in exported if e["class"] == "optional"),
            "optional_skipped": len(optional_skipped),
            "required_failed": len(required_failed),
            "exported_paths": sum(e["paths"] for e in exported),
            "exported_operations": sum(e["operations"] for e in exported),
        },
        "exported": exported,
        "optional_skipped": optional_skipped,
        "required_failed": required_failed,
        "not_asgi": not_asgi,
    }


def write_outputs(summary, out_dir):
    c = summary["counts"]
    lines = [
        "# فهرس OpenAPI لخدمات SAHOOL\n",
        f"- الحالة: **{summary['status']}** · المصدر: `{summary['inventory_source']}`",
        f"- صُدِّر: {c['exported']} خدمة ({c['exported_paths']} مسار، "
        f"{c['exported_operations']} عمليّة) من {c['required'] + c['optional']} خدمة ASGI",
        f"- إلزاميّة فشلت: {c['required_failed']} · اختياريّة تُخطّيت: {c['optional_skipped']}"
        f" · بلا تطبيق ASGI: {c['not_asgi']}",
    ]
    for title, key in (("إلزاميّة فشلت", "required_failed"), ("اختياريّة تُخطّيت", "optional_skipped")):
        if summary[key]:
            lines.append(f"\n## {title}")
            for e in summary[key]:
                why = f" — {e['reason']}" if "reason" in e else ""
                lines.append(
                    f"- `{e['service']}` ({e['static_routes']} مسار ساكن غير مُغطّى){why}: {e['error']}"
                )
    if summary["not_asgi"]:
        lines.append("\n## بلا تطبيق ASGI (لا main في السجلّ)")
        for e in summary["not_asgi"]:
            lines.append(f"- `{e['service']}` ({e['static_routes']} مسار ساكن)")
    for e in summary["exported"]:
        paths = e["_spec_paths"]
        lines.append(f"\n## {e['service']} ({len(paths)} مسار)")
        for path, methods in sorted(paths.items()):
            verbs = ",".join(m.upper() for m in methods if m != "parameters")
            lines.append(f"- `{verbs} {path}`")
    with open(os.path.join(out_dir, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    public = dict(summary)
    public["exported"] = [
        {k: v for k, v in e.items() if k != "_spec_paths"} for e in summary["exported"]
    ]
    with open(os.path.join(out_dir, "EXPORT_SUMMARY.json"), "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=2)
        f.write("\n")


def print_summary(summary, out_dir):
    c = summary["counts"]
    print(f"\n{'=' * 50}")
    print(f"  exported: {c['exported']} ({c['exported_paths']} paths)")
    print(f"  optional skipped: {c['optional_skipped']}")
    for e in summary["optional_skipped"]:
        print(f"    • {e['service']}: {e['reason']} [{e['error']}]")
    print(f"  not ASGI: {c['not_asgi']}")
    print(f"  REQUIRED failed: {c['required_failed']}")
    for e in summary["required_failed"]:
        print(f"    ✗ {e['service']}: {e['error']}")
    print(f"  outputs: {out_dir}/")
    print(f"{'=' * 50}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--inventory", default=DEFAULT_INVENTORY)
    ap.add_argument("--route-inventory", default=DEFAULT_ROUTE_INVENTORY)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = ap.parse_args(argv)

    try:
        inventory = load_inventory(args.inventory)
        classes = classify(inventory)
    except RegistryError as e:
        print(f"  ✗ registry error: {e}", file=sys.stderr)
        return EXIT_REGISTRY_ERROR

    os.makedirs(args.out_dir, exist_ok=True)
    summary = run_export(
        inventory, classes, args.out_dir, args.timeout, static_route_counts(args.route_inventory)
    )
    write_outputs(summary, args.out_dir)
    print_summary(summary, args.out_dir)
    if summary["required_failed"]:
        names = ", ".join(e["service"] for e in summary["required_failed"])
        print(f"  ✗ required services failed to export: {names}", file=sys.stderr)
        return EXIT_REQUIRED_FAILED
    return EXIT_OK


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        sys.exit(_child(sys.argv[2], sys.argv[3], sys.argv[4]))
    sys.exit(main())
