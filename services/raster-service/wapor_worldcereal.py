"""wapor_worldcereal.py — محوّلا WaPOR v3 (إنتاجيّة المياه) وWorldCereal (أولويّة المحاصيل).

**صدق صارم (شرط المستخدم): لا parser بالتخمين.** يُبنى فقط على ما تحقّق من الوثائق:
  • WaPOR v3 **بلا مفتاح** (لا token). كتالوج mapsets: GET
    ``https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets``
    يعيد عناصر تحمل ``code`` + ``caption`` (موثّق). قيم البكسل تُقرأ من COG عبر GDAL
    ``/vsicurl/`` (لا نقطة قيمة JSON). (المصادر: تعليم FAO WaPOR v3 API + fao.org/wapor-data-access.)
  • **غير مُتحقَّق هنا** (مضيفو FAO/ESA محجوبون بوكيل الشبكة 403): غلاف الاستجابة الكامل،
    حقول عنصر الـraster، وواجهة WorldCereal. لذا لا نكتب parser لها (لا تخمين).

كلاهما يبقى ``active=False`` + ``live_verified=False`` حتّى التشغيل على بيئة ذات وصول حيّ
+ عيّنة عقد حقيقيّة (fixture) لقفل الغلاف + تحقّق AOI يمنيّ. منطق الكشف نقيّ؛ الجلب آمن الفشل.
"""

from __future__ import annotations

from typing import Any

WAPOR3_MAPSETS_URL = "https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets"


def parse_wapor_mapsets(data: Any) -> list[dict[str, str]] | None:
    """يستخرج mapsets الموثّقة (``code`` + ``caption``) من ردّ WaPOR v3 — **بلا افتراض غلاف**.

    صدق: نبحث تكراريّاً عن عناصر تحمل الحقلَين الموثّقَين فقط (``code`` نصّ + ``caption``)؛
    غلاف الاستجابة غير مُتحقَّق من الوثائق ⇒ لا نفترض مفتاحاً بعينه (envelope-agnostic).
    لا عناصر مطابقة ⇒ ``None`` (لا تلفيق).
    """
    found: list[dict[str, str]] = []

    def _walk(x: Any) -> None:
        if isinstance(x, dict):
            code = x.get("code")
            if isinstance(code, str) and "caption" in x:
                found.append({"code": code, "caption": str(x.get("caption") or "")})
            for v in x.values():
                _walk(v)
        elif isinstance(x, list):
            for v in x:
                _walk(v)

    _walk(data)
    return found or None


def fetch_wapor_mapsets(*, timeout_s: float = 30.0) -> list[dict[str, str]] | None:
    """يجلب كتالوج WaPOR v3 mapsets (keyless) — ``None`` عند أيّ تعذّر (صدق، لا اختراع)."""
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(WAPOR3_MAPSETS_URL, params={"page": 1, "pageSize": 100})
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل ⇒ متعذّر
        return None
    return parse_wapor_mapsets(data)


def wapor_readiness() -> dict[str, Any]:
    """جاهزيّة محوّل WaPOR v3 (صادق): مُتحقَّق من الوثائق، غير مُتحقَّق حيّاً بعد."""
    return {
        "source": "wapor",
        "active": False,
        "live_verified": False,
        "schema_verified_from_docs": True,  # endpoint keyless + عناصر code/caption موثّقة.
        "provides": ["evapotranspiration", "biomass", "water_productivity"],
        "access": "gismgr_v2_catalog + gdal_cog_pixel_read",
        "reason_code": "live_not_verified",
        "activation_blockers": [
            "live FAO request (data.apps.fao.org محجوب بوكيل هذه البيئة — 403)",
            "contract fixture from real response (لقفل الغلاف/حقول raster)",
            "raster pixel-read verification (قيم AETI/NPP/WPGB عبر GDAL)",
            "Yemen AOI sample validation",
        ],
    }


def worldcereal_readiness() -> dict[str, Any]:
    """جاهزيّة محوّل WorldCereal (صادق): **لم تُتحقَّق الواجهة من مصدر موثوق في هذه البيئة**."""
    return {
        "source": "worldcereal",
        "active": False,
        "live_verified": False,
        # صدق: لم أتمكّن من التحقّق من واجهة WorldCereal من وثيقة موثوقة هنا (ESA محجوب) —
        # لا أدّعي schema_verified_from_docs. لا parser يُكتَب بلا مخطّط مُتحقَّق.
        "schema_verified_from_docs": False,
        "provides": ["crop_type_prior", "irrigation_prior", "confidence"],
        "reason_code": "schema_not_verified",
        "activation_blockers": [
            "verify WorldCereal product access schema from authoritative docs (ESA محجوب هنا)",
            "live ESA/WorldCereal sample (CC-BY partition only)",
            "contract fixture from real response",
            "Yemen AOI validation + local threshold tuning",
        ],
    }
