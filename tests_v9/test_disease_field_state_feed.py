"""Stage F (تغذية آمنة) — تشخيص الأمراض يستمدّ سياقاً من الحالة القانونيّة الموحّدة.

يثبّت أنّ نقطة POST /api/v1/diagnose:
  • تستقبل field_id اختياريّاً (افتراضيّ None ⇒ السلوك الحاليّ تماماً، لا كسر).
  • عند تمرير field_id تستدعي recompute_field_state ضمن tenant_connection وترفِق
    كتلة field_state (validity/execution_mode/operational_truths) — وهو fail-safe.
  • تُضيف ملاحظة مرجعيّة عند ملوحة تربة حرجة دون تغيير قواعد/نتيجة التشخيص.
فحص تعاقُد على المصدر + تسجيل النقطة + أنّ دالّة diagnose النقيّة لم تتغيّر.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")
ROUTERS = os.path.join(CORE, "api", "routers")
# نماذج Pydantic استُخرِجت من main.py إلى platform_models.py (سلوك محفوظ، إعادة تصدير من main).
PLATFORM_MODELS = os.path.join(CORE, "api", "platform_models.py")

# أحرف bidi المحظورة (تخريب اتّجاه النصّ) — تُبنى من نقاط الترميز كي لا تظهر
# حرفيّاً في هذا المصدر (وإلّا أخفقت فحوصها على نفسها).
_BIDI = frozenset(
    chr(cp) for cp in (0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))
)


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    # المعالِج قد يكون في main.py أو في وحدات routers بعد تفكيك monolith (P0).
    # نبحث في main.py أوّلاً ثمّ في كلّ ملفّات routers — فحص التعاقُد يبقى صحيحاً
    # أينما استقرّ المعالِج.
    sources = [MAIN]
    if os.path.isdir(ROUTERS):
        sources += [
            os.path.join(ROUTERS, f) for f in sorted(os.listdir(ROUTERS)) if f.endswith(".py")
        ]
    needle = f"async def {name}("
    for path in sources:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        start = src.find(needle)
        if start == -1:
            continue
        nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
        end = (start + 1 + nxt.start()) if nxt else len(src)
        return src[start:end]
    raise AssertionError(f"لم يُعثر على المعالِج `{name}` في main.py ولا في routers/")


def test_diagnose_endpoint_feeds_canonical_state():
    """تعاقُد المصدر: النقطة تمرّ عبر الحالة الموحّدة داخل حارس field_id."""
    body = _func_src("diagnose_symptoms")
    assert "recompute_field_state" in body, "لا استدعاء لـrecompute_field_state"
    assert "tenant_connection" in body, "لا يُفتَح tenant_connection (RLS)"
    assert "field_state" in body, "لا يُرفِق كتلة field_state"

    # الاستدعاء يجب أن يقع داخل حارس `if req.field_id:` (غياب field_id ⇒ تخطٍّ).
    lines = body.splitlines()
    rc_idx = next(
        (i for i, ln in enumerate(lines) if "recompute_field_state" in ln and "import" not in ln),
        None,
    )
    assert rc_idx is not None
    rc_indent = len(lines[rc_idx]) - len(lines[rc_idx].lstrip())
    guarded = any(
        ln.strip().startswith("if req.field_id") and (len(ln) - len(ln.lstrip())) < rc_indent
        for ln in lines[:rc_idx]
    )
    assert guarded, "recompute_field_state ليس داخل حارس req.field_id"


def test_critical_salinity_adds_reference_note_only():
    """ملوحة حرجة ⇒ ملاحظة مرجعيّة فقط (لا تغيير لقواعد/نتيجة التشخيص)."""
    body = _func_src("diagnose_symptoms")
    # متسامح مع التنسيق: salinity_class ... == ... critical (مراجعة Copilot)
    assert re.search(r"salinity_class.*?==.*?critical", body), "لا فحص لملوحة حرجة"
    assert "إجهاد الملوحة" in body, "لا ملاحظة مرجعيّة عند الملوحة الحرجة"
    # التغذية best-effort: تعذّر الحالة لا يكسر التشخيص (fail-safe).
    assert "except Exception" in body, "لا حارس fail-safe حول الحالة الموحّدة"


def test_diagnose_request_has_optional_field_id():
    """field_id اختياريّ بافتراضيّ None — لا يكسر النداء الحاليّ."""
    # النموذج استُخرِج إلى platform_models.py (يُعاد تصديره من main، سلوك محفوظ).
    with open(PLATFORM_MODELS, encoding="utf-8") as f:
        src = f.read()
    start = src.index("class DiagnoseRequest(")
    block = src[start : start + 400]
    assert "field_id: str | None = None" in block, "field_id ليس اختياريّاً بافتراضيّ None"


def test_main_source_has_no_bidi_chars():
    """لا أحرف bidi خفيّة في مصدر main.py (تخريب اتّجاه/مراجعة)."""
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    bad = sorted({hex(ord(c)) for c in src if c in _BIDI})
    assert not bad, f"أحرف bidi محظورة في main.py: {bad}"


def test_diagnose_route_registered(core_on_path):
    import api.main as m

    methods = {
        meth
        for r in m.app.routes
        if getattr(r, "path", None) == "/api/v1/diagnose"
        for meth in (getattr(r, "methods", set()) or set())
    }
    assert "POST" in methods, "نقطة POST /api/v1/diagnose غير مُسجَّلة"


def test_pure_diagnose_unchanged_without_field_id(core_on_path):
    """دالّة التشخيص النقيّة (api.disease_diagnosis.diagnose) لم تتغيّر: نفس
    المرشّحين والأرقام دون أيّ مفهوم لـfield_id (قيد عدم تغيير التشخيص)."""
    from api.disease_diagnosis import DiagnosisResult, diagnose

    res = diagnose("wheat", ["orange_pustules", "leaf_yellowing"])
    assert isinstance(res, DiagnosisResult)
    d = res.to_dict()
    # صدأ القمح يتصدّر (قاعدة ثابتة) بثقة 0.8 (0.7 أساس + 0.1 دعم واحد).
    assert d["candidates"], "لا مرشّحين للأعراض المعروفة"
    assert d["candidates"][0]["issue_code"] == "wheat.rust"
    assert d["candidates"][0]["confidence"] == 0.8
    # المخرج النقيّ لا يحوي أيّ سياق حالة موحّدة (الإرفاق في النقطة فقط).
    assert "field_state" not in d
    assert "advisory_notes_ar" not in d
