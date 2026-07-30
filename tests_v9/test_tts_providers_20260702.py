"""test_tts_providers_20260702.py — وحدات: تجريد مزوّدي TTS + التطبيع العربيّ.
================================================================================
اختبارات منطق صرف (marker=unit، بلا خدمات/شبكة) تغطّي الميزات المُضافة إلى
tts-service:

  • ``ArabicTextNormalizer`` — تجريد التطويل، توحيد الألف (وضع on/off)، تطبيع
    الأرقام باتّجاهين، توسيع الوحدات/الرموز، وطيّ المسافات — تأكيداتٌ حتميّة.
  • ``select_provider`` — طلب متاح⇒يُختار، طلب غير متاح/مجهول⇒سقوط إلى edge،
    لا طلب⇒الافتراضيّ — بمزوّدين وهميّين يتحكّمون بـ``available()``.
  • ``EdgeTTSProvider`` متاح؛ ``PiperProvider``/``XTTSProvider`` غير متاحين حين
    تغيب المكتبة/العلم (يُرقَّع عبر البيئة).
  • مُعالِج ``/v1/tts/status`` (importorskip fastapi) — شكل الخرج يُعدّد المزوّدين
    مع is_default.

تُحمَّل الوحدتان النقيّتان (providers/arabic_normalizer) مباشرةً من مجلّد الخدمة
دون fastapi. اختبار المُعالِج وحده يتطلّب fastapi (importorskip).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# مجلّد الخدمة على sys.path كي تُستورَد الوحدتان النقيّتان (كما يفعل حارس التفكيك).
_SVC_DIR = Path(__file__).resolve().parents[1] / "services" / "tts-service"
if str(_SVC_DIR) not in sys.path:
    sys.path.insert(0, str(_SVC_DIR))

from arabic_normalizer import ArabicTextNormalizer  # noqa: E402
from providers import (  # noqa: E402
    DEFAULT_PROVIDER_NAME,
    EdgeTTSProvider,
    PiperProvider,
    XTTSProvider,
    build_registry,
    select_provider,
)


# ── مزوّد وهميّ يتحكّم بتوفّره (لاختبار select_provider نقيّاً) ─────────────────
class _FakeProvider:
    def __init__(self, name: str, available: bool) -> None:
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    async def synthesize(self, text, voice, rate, pitch, volume) -> bytes:  # pragma: no cover
        return b"fake-audio"


def _registry(edge_ok=True, piper_ok=False, xtts_ok=False):
    return [
        _FakeProvider("edge_tts", edge_ok),
        _FakeProvider("piper", piper_ok),
        _FakeProvider("xtts", xtts_ok),
    ]


# ── ArabicTextNormalizer ──────────────────────────────────────────────────────
class TestArabicNormalizer:
    def test_strip_tatweel(self):
        n = ArabicTextNormalizer()
        assert n.normalize("مـــرحبـا") == "مرحبا"

    def test_tatweel_kept_when_disabled(self):
        n = ArabicTextNormalizer(strip_tatweel=False, expand_symbols=False)
        assert "ـ" in n.normalize("مـرحبا")

    def test_alef_unify_off_by_default_faithful(self):
        n = ArabicTextNormalizer()  # unify_alef=False
        out = n.normalize("أحمد إلى آفاق")
        assert "أ" in out and "إ" in out and "آ" in out

    def test_alef_unify_on(self):
        n = ArabicTextNormalizer(unify_alef=True)
        out = n.normalize("أحمد إلى آفاق")
        assert "أ" not in out and "إ" not in out and "آ" not in out
        assert out == "احمد الى افاق"

    def test_digits_to_ascii(self):
        n = ArabicTextNormalizer(digits="ascii")
        assert n.normalize("القيمة ٠١٢٣٤٥٦٧٨٩") == "القيمة 0123456789"

    def test_digits_to_arabic(self):
        n = ArabicTextNormalizer(digits="arabic")
        assert n.normalize("القيمة 0123456789") == "القيمة ٠١٢٣٤٥٦٧٨٩"

    def test_digits_keep_default(self):
        n = ArabicTextNormalizer()
        assert "٥" in n.normalize("عدد ٥") and "5" not in n.normalize("عدد ٥")

    def test_percent_expansion(self):
        n = ArabicTextNormalizer()
        assert "بالمئة" in n.normalize("رطوبة 50%")

    def test_celsius_expansion(self):
        n = ArabicTextNormalizer()
        assert "درجة مئويّة" in n.normalize("الحرارة 25°C")

    def test_unit_expansion_mm_ha(self):
        n = ArabicTextNormalizer()
        assert "مليمتر" in n.normalize("هطول 5mm")
        assert "هكتار" in n.normalize("المساحة 3 ha")

    def test_unit_not_matched_inside_word(self):
        # «mm» داخل كلمة لاتينيّة لا يُوسَّع (حدود لا-حرفيّة).
        n = ArabicTextNormalizer()
        assert "مليمتر" not in n.normalize("hammer")

    def test_collapse_whitespace(self):
        n = ArabicTextNormalizer()
        assert n.normalize("كلمة    ثانية\n\tثالثة") == "كلمة ثانية ثالثة"

    def test_empty_text_passthrough(self):
        assert ArabicTextNormalizer().normalize("") == ""

    def test_deterministic(self):
        n = ArabicTextNormalizer(unify_alef=True, digits="ascii")
        txt = "أرض ٧ ha رطوبة 20%"
        assert n.normalize(txt) == n.normalize(txt)

    def test_invalid_digits_flag_rejected(self):
        with pytest.raises(ValueError):
            ArabicTextNormalizer(digits="bogus")


# ── select_provider ───────────────────────────────────────────────────────────
class TestSelectProvider:
    def test_explicit_available_is_chosen(self):
        reg = _registry(piper_ok=True)
        assert select_provider("piper", reg).name == "piper"

    def test_explicit_unavailable_falls_back_to_edge(self):
        reg = _registry(piper_ok=False)
        assert select_provider("piper", reg).name == DEFAULT_PROVIDER_NAME

    def test_explicit_unknown_falls_back_to_edge(self):
        reg = _registry()
        assert select_provider("does-not-exist", reg).name == DEFAULT_PROVIDER_NAME

    def test_none_returns_default(self):
        reg = _registry()
        assert select_provider(None, reg).name == DEFAULT_PROVIDER_NAME

    def test_empty_string_returns_default(self):
        reg = _registry()
        assert select_provider("", reg).name == DEFAULT_PROVIDER_NAME

    def test_never_silently_picks_unavailable(self):
        # edge غير متاح (افتراضيّاً محال في الخدمة، لكن نتحقّق من عدم اختيار غير متاح).
        reg = _registry(edge_ok=False, xtts_ok=True)
        # طلب xtts المتاح ⇒ يُختار هو (لا يُجبَر على edge غير المتاح).
        assert select_provider("xtts", reg).name == "xtts"


# ── توفّر المزوّدين الفعليّين ───────────────────────────────────────────────────
class TestProviderAvailability:
    def test_edge_available(self):
        # edge_tts مثبّت في **بيئة الخدمة** لكنّه غائب/كعبٌ في طبقة الوحدات الدنيا لـCI
        # ⇒ نتخطّى حينها (available() تُرجِع False بصدق)؛ التأكيد على True مشروط بمكتبة حقيقيّة.
        _require_real_edge_tts()
        assert EdgeTTSProvider().available() is True

    def test_piper_unavailable_without_lib_or_model(self, monkeypatch):
        # المكتبة غائبة في طبقة الوحدات ⇒ غير متاح حتّى لو ضُبِط مسار وهميّ.
        monkeypatch.setenv("PIPER_VOICE_PATH", "/nonexistent/voice.onnx")
        assert PiperProvider().available() is False

    def test_xtts_unavailable_without_lib_even_if_flag(self, monkeypatch):
        monkeypatch.setenv("XTTS_ENABLE", "1")
        assert XTTSProvider().available() is False
        monkeypatch.setenv("TTS_GPU_PROVIDER", "xtts")
        assert XTTSProvider().available() is False

    def test_registry_has_edge_default(self):
        reg = build_registry()
        names = [p.name for p in reg]
        assert DEFAULT_PROVIDER_NAME in names
        assert reg[0].name == DEFAULT_PROVIDER_NAME


# ── مُعالِج /v1/tts/status و/v1/tts/voices (يتطلّبان fastapi) ─────────────────────────
# نمرّر توكن JWT حقيقيّاً (aud=sahool، مُصدِر مسموح) عبر رأس Bearer بدل تجاوز
# التبعيّة: راوترات الخدمة تُضمَّن بتمديد app.routes مباشرةً (تسطيح) فلا يُضبَط
# dependency_overrides_provider عليها ⇒ التجاوز لا يُستشار. التوكن الحقيقيّ أمتن.
def _bearer(main_mod) -> dict:
    from jose import jwt

    token = jwt.encode(
        {"sub": "tester", "iss": "sahool-auth", "aud": "sahool", "tenant_id": "t1"},
        main_mod.JWT_SECRET,
        algorithm=main_mod._JWT_ALG,
    )
    return {"Authorization": f"Bearer {token}"}


def _require_real_edge_tts():
    """تخطَّ إن لم تتوفّر مكتبة edge_tts **الحقيقيّة** (كعبٌ محقون أو غائبة).

    ``importorskip('edge_tts')`` وحده لا يكفي لحالتَي الاختبار على المُعالِج: ملفّ
    شقيق (test_tts_notification_service_auth) يحقن كعباً دائماً في ``sys.modules``،
    فيمرّ importorskip فوقه بينما يبقى ``providers._EDGE_AVAILABLE`` مُجمَّداً على False
    (و``_load_main`` قد يعيد استعمال نسخة tts محمّلة بهذا التجميد) ⇒ فيفشل تأكيد
    available=True. الكعب بلا ``__file__`` — نتحقّق من مكتبة حقيقيّة وإلّا نتخطّى.
    """
    et = pytest.importorskip("edge_tts")
    if getattr(et, "__file__", None) is None:
        pytest.skip("edge_tts كعبٌ محقون/غائب — لا مكتبة حقيقيّة لتأكيد available=True")


def _load_main():
    """يعيد وحدة tts الرئيسة **مُعيداً استعمال** أيّ نسخة محمّلة مسبقاً.

    prometheus يرفض تكرار تسجيل المقاييس: تحميل ``main`` مرّتين (تحت اسمين مختلفين
    مثل ``main`` و``sahool_tts_main`` في ملفّات اختبار أخرى) يرمي «Duplicated
    timeseries». لذا نعيد استعمال أيّ نسخة موجودة في ``sys.modules`` (بأيّ من
    الاسمين) قبل الاستيراد الطازج — فلا نُطلِق تسجيلاً ثانياً.
    """

    def _is_tts_main_with_status(mod) -> bool:
        # ليست أيّ نسخة tts تكفي: يجب أن تحمل مسار ``/v1/tts/status`` الجديد (نسخة قديمة
        # حمّلها اختبار آخر قد لا تملكه إن سبق تسجيل راوترها). نتحقّق من المسار فعليّاً.
        from conftest import registered_paths

        if mod is None or not hasattr(mod, "app") or not hasattr(mod, "VOICES"):
            return False
        return "/v1/tts/status" in registered_paths(mod.app)

    # أعِد استعمال نسخة tts محمّلة **تملك المسار** (تُميَّز بـ``VOICES`` — لا تخلطها مع
    # ``main`` خدمة أخرى مثل video-processor في التشغيل الكامل للسويت).
    for name in ("sahool_tts_main", "main"):
        mod = sys.modules.get(name)
        if _is_tts_main_with_status(mod):
            return mod
    # تحميل نظيف: صدّر مجلّد tts على sys.path، وأخلِ الوحدات الشقيقة المُخزَّنة (main +
    # router_registry + routers.* + الوحدات النقيّة) — سواء لخدمة أخرى بالاسم نفسه أو
    # لنسخة tts سابقة رُبِطت راوتراتها بتطبيق قديم — كي تُعاد ربطها بالتطبيق الطازج
    # فيُسجَّل ``/v1/tts/status``. المقاييس idempotent (``_metric`` في main) فلا تكرار prometheus.
    while str(_SVC_DIR) in sys.path:
        sys.path.remove(str(_SVC_DIR))
    sys.path.insert(0, str(_SVC_DIR))
    for name in (
        "main",
        "router_registry",
        "routers",
        "routers.tts",
        "routers.health",
        "providers",
        "arabic_normalizer",
    ):
        sys.modules.pop(name, None)
    import main

    from conftest import registered_paths

    assert hasattr(main, "VOICES"), "استُورِد ``main`` خدمة أخرى بدل tts (تصادم اسم الوحدة)"
    assert "/v1/tts/status" in registered_paths(main.app), (
        "لم يُسجَّل مسار /v1/tts/status على التطبيق الطازج (راوترات شقيقة مُخزَّنة قديمة)"
    )
    return main


def test_status_endpoint_shape():
    pytest.importorskip("fastapi")
    _require_real_edge_tts()  # يؤكّد available=True ⇒ يلزم edge_tts حقيقيّ (لا كعب/غياب)
    main = _load_main()
    if not main.JWT_SECRET:  # بيئة بلا سرّ مضبوط ⇒ لا يمكن سكّ توكن اختباريّ.
        pytest.skip("JWT_SECRET غير مضبوط في هذه البيئة")
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    resp = client.get("/v1/tts/status", headers=_bearer(main))
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "edge_tts"
    provs = body["providers"]
    assert isinstance(provs, list) and len(provs) >= 1
    by_name = {p["name"]: p for p in provs}
    assert "edge_tts" in by_name
    assert by_name["edge_tts"]["is_default"] is True
    assert by_name["edge_tts"]["available"] is True
    for p in provs:
        assert {"name", "available", "is_default"} <= set(p.keys())
    # مزوّد افتراضيّ واحد بالضبط.
    assert sum(1 for p in provs if p["is_default"]) == 1


def test_voices_endpoint_includes_providers():
    pytest.importorskip("fastapi")
    _require_real_edge_tts()  # يؤكّد available=True ⇒ يلزم edge_tts حقيقيّ (لا كعب/غياب)
    main = _load_main()
    if not main.JWT_SECRET:
        pytest.skip("JWT_SECRET غير مضبوط في هذه البيئة")
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    resp = client.get("/v1/tts/voices", headers=_bearer(main))
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == main.DEFAULT_VOICE
    assert "voices" in body and body["voices"]
    assert any(p["name"] == "edge_tts" for p in body["providers"])
