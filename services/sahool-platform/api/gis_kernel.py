"""api/gis_kernel.py — دوالّ تحقّق/تطبيع GeoJSON نقيّة لنواة GIS (split/merge/buffer/topology).

نواة هندسيّة **نقيّة** (بلا I/O، بلا قاعدة، بلا shapely) قابلة للاختبار وحدويّاً.
المسؤوليّات هنا حصراً:

  ١. **التحقّق من بنية GeoJSON المُدخَلة** (نوع الهندسة، الحقول الإلزاميّة).
  ٢. **استخراج** هندسة من Feature/FeatureCollection/Geometry خام.
  ٣. **تطبيع** الهندسة إلى dict هندسة GeoJSON قياسيّ (geometry object) جاهز
     للتمرير إلى PostGIS عبر `ST_GeomFromGeoJSON` في الموجِّه.

الحساب الهندسيّ الفعليّ (ST_Buffer/ST_Union/ST_Split/ST_MakeValid) يجري في PostGIS
داخل الموجِّه — لأنّ `shapely` غير مُثبَّت. هذه الوحدة لا تستورد أيّ شيء من
`api.main` ولا تفتح اتّصالاً؛ تبقى نقيّة كي تُختبر بلا خدمات.

CRS المعياري في النظام كلّه EPSG:4326 (يطابق عمود fields.geom) — أيّ هندسة
GeoJSON تُفترَض 4326 (المعيار RFC 7946: lng,lat).
"""

from __future__ import annotations

from typing import Any

# أنواع الهندسة المدعومة من GeoJSON (RFC 7946). نقبلها جميعاً عند الاستخراج/التطبيع؛
# قيود إضافيّة (مثلاً «خطّ فقط» لشفرة القطع) تُفرَض في الدالّة الخاصّة بكلّ عمليّة.
GEOMETRY_TYPES = frozenset(
    {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }
)

# أنواع المساحات (polygonal) — مدخلات صالحة للـbuffer/union/validate كهندسة مساحة.
POLYGONAL_TYPES = frozenset({"Polygon", "MultiPolygon"})

# أنواع الخطوط — شفرة القطع (blade) في ST_Split يجب أن تكون خطّاً.
LINEAL_TYPES = frozenset({"LineString", "MultiLineString"})


class GeoJSONError(ValueError):
    """خطأ تحقّق GeoJSON نقيّ — يُحوَّل في الموجِّه إلى HTTP 422 برسالة عربيّة.

    نرفعه من دوالّ هذه الوحدة بدل HTTPException كي تبقى نقيّة (لا تبعيّة على FastAPI).
    """


def _require_mapping(obj: Any, what_ar: str) -> dict:
    """يتحقّق أنّ الكائن dict (كائن JSON) — وإلّا يرفع GeoJSONError بالعربيّة."""
    if not isinstance(obj, dict):
        raise GeoJSONError(f"{what_ar} يجب أن يكون كائن GeoJSON (JSON object).")
    return obj


def is_geometry_type(value: Any) -> bool:
    """هل القيمة اسم نوع هندسة GeoJSON معروف؟ (تحقّق نوع نقيّ، حسّاس لحالة الأحرف)."""
    return isinstance(value, str) and value in GEOMETRY_TYPES


def validate_geometry(geom: Any) -> dict:
    """يتحقّق أنّ `geom` كائن هندسة GeoJSON صالح بنيويّاً ويُعيده كما هو (dict).

    لا يتحقّق من صحّة الطوبولوجيا (تقاطع ذاتيّ…) — ذلك عمل PostGIS عبر
    ST_IsValid/ST_MakeValid في نقطة `validate`. هنا فقط: dict، حقل `type` معروف،
    وحقل المحتوى الموافق (`coordinates` للأنواع البسيطة، `geometries` للمجموعة).
    """
    g = _require_mapping(geom, "الهندسة")
    gtype = g.get("type")
    if not is_geometry_type(gtype):
        raise GeoJSONError(f"نوع هندسة غير مدعوم: {gtype!r}. المدعوم: {sorted(GEOMETRY_TYPES)}.")
    if gtype == "GeometryCollection":
        geometries = g.get("geometries")
        if not isinstance(geometries, list):
            raise GeoJSONError("GeometryCollection يتطلّب قائمة `geometries`.")
        # تحقّق متعدٍّ (recursive) من كلّ عضو — يمنع تمرير مجموعة بأعضاء فاسدة.
        for member in geometries:
            validate_geometry(member)
        return g
    coords = g.get("coordinates")
    if not isinstance(coords, list):
        raise GeoJSONError(f"هندسة {gtype} تتطلّب قائمة `coordinates`.")
    return g


def extract_geometry(obj: Any) -> dict:
    """يستخرج كائن الهندسة من GeoJSON خام: Geometry أو Feature أو FeatureCollection.

    قواعد الاستخراج (نقيّة):
      • Geometry (type ضمن GEOMETRY_TYPES) ⇒ يُعاد كما هو (بعد تحقّق بنيويّ).
      • Feature ⇒ يُستخرَج `geometry` (يجب ألّا يكون null).
      • FeatureCollection بعنصر واحد ⇒ يُستخرَج geometry ذلك العنصر.
      • FeatureCollection بعدّة عناصر ⇒ خطأ (الغموض مرفوض؛ استعمل union صراحةً).

    يرفع GeoJSONError لأيّ شكل آخر.
    """
    o = _require_mapping(obj, "المُدخَل")
    otype = o.get("type")
    if is_geometry_type(otype):
        return validate_geometry(o)
    if otype == "Feature":
        geom = o.get("geometry")
        if geom is None:
            raise GeoJSONError("Feature بلا هندسة (geometry=null) غير مقبول.")
        return validate_geometry(geom)
    if otype == "FeatureCollection":
        features = o.get("features")
        if not isinstance(features, list) or not features:
            raise GeoJSONError("FeatureCollection فارغ أو بلا `features`.")
        if len(features) != 1:
            raise GeoJSONError(
                "FeatureCollection بعدّة معالم غامض هنا — مرّر هندسة واحدة "
                "أو استعمل نقطة union للدمج صراحةً."
            )
        return extract_geometry(features[0])
    raise GeoJSONError(
        f"نوع GeoJSON غير مدعوم للاستخراج: {otype!r}. "
        "المتوقَّع: Geometry أو Feature أو FeatureCollection بعنصر واحد."
    )


def normalize_geometry(obj: Any) -> dict:
    """يستخرج ويُطبّع هندسة GeoJSON إلى dict هندسة قياسيّ جاهز لـ`ST_GeomFromGeoJSON`.

    التطبيع هنا = استخراج الهندسة (من أيّ غلاف Feature/FC) + تجريدها إلى الحقول
    الهندسيّة فقط (`type` + `coordinates`/`geometries`) — يُسقِط `properties`/`bbox`/
    أيّ مفاتيح غير هندسيّة كي يكون المُمرَّر إلى PostGIS هندسة نقيّة لا غلافاً.
    """
    geom = extract_geometry(obj)
    gtype = geom["type"]
    if gtype == "GeometryCollection":
        return {
            "type": gtype,
            "geometries": [normalize_geometry(m) for m in geom["geometries"]],
        }
    return {"type": gtype, "coordinates": geom["coordinates"]}


def require_lineal_blade(obj: Any) -> dict:
    """يطبّع شفرة القطع (blade) لـST_Split ويتحقّق أنّها خطّيّة (Line/MultiLine).

    ST_Split يقطع هندسة بخطّ؛ تمرير مساحة كشفرة لا معنى له. نفرض النوع هنا (نقيّاً)
    كي يَفشل المُدخَل الخاطئ مبكِّراً بـ422 واضح بدل خطأ PostGIS غامض.
    """
    geom = normalize_geometry(obj)
    if geom["type"] not in LINEAL_TYPES:
        raise GeoJSONError(
            f"شفرة القطع يجب أن تكون خطّاً (LineString/MultiLineString)، لا {geom['type']}."
        )
    return geom


def require_polygonal(obj: Any, *, what_ar: str = "الهندسة") -> dict:
    """يطبّع هندسة ويتحقّق أنّها مساحيّة (Polygon/MultiPolygon) — لمدخلات تتطلّب مساحة."""
    geom = normalize_geometry(obj)
    if geom["type"] not in POLYGONAL_TYPES:
        raise GeoJSONError(
            f"{what_ar} يجب أن تكون مساحة (Polygon/MultiPolygon)، لا {geom['type']}."
        )
    return geom


def validate_distance_m(value: Any) -> float:
    """يتحقّق أنّ مسافة الـbuffer رقم منتهٍ (قد يكون سالباً لـinward buffer) ويُعيده float.

    لا نفرض حدّاً أعلى هنا (سياسة المجال تتطوّر) — فقط رقم حقيقيّ منتهٍ غير NaN.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GeoJSONError("distance_m يجب أن يكون رقماً (متراً).")
    f = float(value)
    if f != f or f in (float("inf"), float("-inf")):  # NaN أو لانهاية
        raise GeoJSONError("distance_m يجب أن يكون رقماً منتهياً (لا NaN/لا ∞).")
    return f
