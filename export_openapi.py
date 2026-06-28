#!/usr/bin/env python3
"""
export_openapi.py — تصدير مواصفات OpenAPI لكلّ خدمات SAHOOL (FastAPI).

يستدعي app.openapi() لكلّ خدمة (بلا تشغيل uvicorn) ويحفظ JSON في docs/openapi/.
تشغّله في بيئتك حيث fastapi/pydantic مثبّتتان.

الاستخدام (من جذر المشروع):
    python3 export_openapi.py

المخرجات:
    docs/openapi/<service>.openapi.json   لكلّ خدمة
    docs/openapi/INDEX.md                  فهرس موحّد للمسارات

ملاحظة: بعض الخدمات تستورد حزماً ثقيلة (rasterio/redis...) — لو فشل استيراد
خدمة، يتخطّاها بأمان ويسجّل السبب (لا يتوقّف).
"""
import importlib.util
import json
import os
import sys

# الخدمات وملفّات main الخاصّة بها (المسار النسبي من جذر المشروع)
SERVICES = [
    "actuator-service", "agriai-engine", "auth", "edge-inference",
    "guardrails-engine", "local-ai-rag", "odoo-bridge", "raster-service",
    "soil-service", "supervisor-agent", "tts-service",
    "vegetation-analysis-service", "video-processor", "weather-service",
]

OUT_DIR = os.path.join("docs", "openapi")


def load_app(service: str):
    """يحمّل كائن app من services/<service>/main.py بلا تشغيل الخادم."""
    main_path = os.path.join("services", service, "main.py")
    if not os.path.exists(main_path):
        return None, "main.py غير موجود"
    svc_dir = os.path.join("services", service)
    # أضِف مجلّد الخدمة + الجذر للمسار (للاستيرادات المحليّة + shared)
    sys.path.insert(0, os.path.abspath(svc_dir))
    sys.path.insert(0, os.path.abspath("."))
    try:
        spec = importlib.util.spec_from_file_location(
            f"_svc_{service.replace('-', '_')}", main_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        app = getattr(mod, "app", None)
        if app is None:
            return None, "لا كائن app"
        return app, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    finally:
        # نظّف المسار لتجنّب تعارض الاستيرادات بين الخدمات
        for p in (os.path.abspath(svc_dir), os.path.abspath(".")):
            if p in sys.path:
                sys.path.remove(p)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    exported, skipped = [], []
    index_lines = ["# فهرس OpenAPI لخدمات SAHOOL\n"]

    for svc in SERVICES:
        app, err = load_app(svc)
        if app is None:
            skipped.append((svc, err))
            print(f"  ⚠ {svc}: تخطٍّ ({err})")
            continue
        try:
            spec = app.openapi()
        except Exception as e:  # noqa: BLE001
            skipped.append((svc, f"openapi() فشل: {e}"))
            print(f"  ⚠ {svc}: openapi() فشل")
            continue

        out_path = os.path.join(OUT_DIR, f"{svc}.openapi.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

        paths = spec.get("paths", {})
        exported.append((svc, len(paths)))
        print(f"  ✓ {svc}: {len(paths)} مسار → {out_path}")

        # أضِف للفهرس
        index_lines.append(f"\n## {svc} ({len(paths)} مسار)")
        for path, methods in sorted(paths.items()):
            verbs = ",".join(m.upper() for m in methods if m != "parameters")
            index_lines.append(f"- `{verbs} {path}`")

    # اكتب الفهرس
    with open(os.path.join(OUT_DIR, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))

    print(f"\n{'='*50}")
    print(f"  صُدِّر: {len(exported)} خدمة")
    print(f"  تُخطّي: {len(skipped)} خدمة")
    if skipped:
        print("  أسباب التخطّي (غالباً حزم ناقصة — ثبّتها وأعد المحاولة):")
        for svc, err in skipped:
            print(f"    • {svc}: {err}")
    print(f"  المخرجات في: {OUT_DIR}/")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
