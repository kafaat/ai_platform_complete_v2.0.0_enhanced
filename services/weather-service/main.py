"""
weather-service/main.py — خدمة طقس (stub رفيع صادق)

⚠ ملاحظة صدق (متّسقة مع __init__.py):
  المنطق الفعلي للطقس مُنفَّذ حالياً في sahool-platform/api/main.py
  (Open-Meteo + التخزين + الميزان المائي). هذه الخدمة حاليّاً **stub
  رفيع** يوفّر نقاط الصحّة فقط، حتّى تبني عليها compose عبر
  depends_on: service_healthy دون فشل، ولتكون نقطة توسّع مستقبليّة
  حين يُفصل منطق الطقس لخدمة مستقلّة.

  لا يدّعي تقديم بيانات طقس — يُرجع 501 لأيّ مسار طقس فعلي، بصدق،
  بدل إيهام بوظيفة غير موجودة.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="SAHOOL Weather Service (stub)", version="9.1")


@app.get("/healthz")
def healthz():
    """فحص حياة بسيط — الخدمة تعمل."""
    return {"status": "ok", "service": "weather-service", "mode": "stub"}


@app.get("/readyz")
def readyz():
    """جاهزيّة — stub جاهز دائماً (لا تبعيّات خارجيّة)."""
    return {"status": "ready", "service": "weather-service", "mode": "stub"}


@app.get("/")
def root():
    return {
        "service": "weather-service",
        "mode": "stub",
        "note_ar": (
            "منطق الطقس الفعلي في sahool-platform حاليّاً. هذه الخدمة "
            "نقطة توسّع مستقبليّة توفّر فحوص الصحّة فقط."
        ),
    }


@app.get("/contract")
def contract():
    """عقد P1: يعلن الملكية المستهدفة بدون ادعاء تنفيذ غير موجود."""
    return {
        "service": "weather-service",
        "mode": "stub",
        "ownership": "target-weather-system-of-record",
        "implemented_runtime": False,
        "target_capabilities": [
            "current-weather",
            "forecast",
            "historical-weather",
            "weather-tiles",
            "operation-windows",
            "weather-alerts",
            "weather-signals",
        ],
        "current_runtime_owner": "sahool-platform legacy facade",
    }


def _weather_not_implemented_response(path: str):
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented_here",
            "service": "weather-service",
            "mode": "stub",
            "path": path,
            "note_ar": "منطق الطقس في sahool-platform/api حالياً، لا في هذه الخدمة الرفيعة.",
        },
    )


@app.get("/weather/{path:path}")
def weather_not_implemented(path: str):
    """أيّ مسار طقس فعلي legacy → 501 بصدق."""
    return _weather_not_implemented_response(f"/weather/{path}")


@app.get("/v1/weather/{path:path}")
def v1_weather_not_implemented(path: str):
    """أيّ مسار طقس فعلي v1 → 501 بصدق حتى يكتمل الاستخراج."""
    return _weather_not_implemented_response(f"/v1/weather/{path}")
