"""P3.5 — weather direct-wiring final sweep guard.

Scans ``services/sahool-platform/api/**/*.py`` and asserts that every file which really
wires itself to the Open-Meteo provider adapter — by **importing** ``api.connectors.openmeteo``
or by **using** one of its provider-touching fetchers — is either:
  - a legitimate home (the Open-Meteo provider adapter or the weather-service transport), or
  - a documented cross-domain residual in ``weather_direct_wiring_allowlist.json``.

Any new offender fails the guard, preventing direct Open-Meteo wiring from re-spreading
through unrelated platform modules after the P3.4 facade extraction.

**الكشفُ بنيويٌّ لا نصّيّ — وسببُه مقيس.** كان الفحصُ بحثاً عن سلاسلَ نصّيّة في
كامل الملفّ، فأخطأ في الاتّجاهين معاً:

* **يتّهم النثر:** تعليقٌ يشرح *لماذا* هُجِر الموصّلُ يذكر اسمَه، فيبقى الملفُّ
  «مخالفاً» بعد أن نُزِع منه آخرُ استيراد. أي أنّ توثيقَ الإصلاح كان يُبطِله.
* **ويُفلِت التهرّب:** ``from api.connectors import openmeteo`` **لا يحوي**
  السلسلة ``connectors.openmeteo`` إطلاقاً. ومع ``fetch_bundle`` — وهو يبلغ
  المزوّدَ عبر ``fetch_current``/``fetch_daily_forecast`` داخليّاً وكان **خارج**
  قائمة العلامات — يمرّ ملفٌّ يخرج إلى المزوّد بلا أن يُطابِق علامةً واحدة.
  مقيسٌ بالتنفيذ على مقطعٍ مُصطنَع: **صفرُ مطابقات**.

فالعلاماتُ تُقرأ الآن من شجرة البناء (``ast``): استيرادُ الوحدة بأيّ إملاء، أو
ذكرُ أحدِ جالبيها في **كود** لا في تعليق. والنثرُ حرّ، والتهرّبُ بالإملاء مُغلَق.

ويحمل الملفُّ **راتشِتاً** فوق ذلك: عددُ المتبقّيات المُوثَّقة سقفٌ ينزل ولا يصعد.
انظر ``test_the_documented_residuals_only_ever_shrink``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
API_DIR = PLATFORM / "api"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "weather_direct_wiring_allowlist.json"
CONTRACT_PATH = ROOT / "docs" / "architecture" / "WEATHER_DIRECT_WIRING_FINAL_SWEEP_CONTRACT.md"

# علامةُ الوحدة: استيرادُ موصّل المزوّد نفسِه، بأيّ إملاء.
MODULE_MARKER = "connectors.openmeteo"
CONNECTOR_MODULE = "api.connectors.openmeteo"

# جالباتُ الموصّل التي تبلغ المزوّد — مُشتقّةٌ من سطحه العامّ لا مُخمَّنة.
# ``fetch_bundle`` و``fetch_current_batch`` مُدرَجان صراحةً: الأوّل كان غائباً عن
# القائمة النصّيّة رأساً، والثاني كان يُطابَق بالمصادفة (يحوي ``fetch_current``).
FETCHER_MARKERS = (
    "fetch_current",
    "fetch_current_batch",
    "fetch_daily_forecast",
    "fetch_historical",
    "fetch_bundle",
    "fetch_weather_tile_data",
)

DIRECT_WIRING_MARKERS = (MODULE_MARKER, *FETCHER_MARKERS)


def _load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    return path.relative_to(PLATFORM).as_posix()


def _api_py_files() -> list[Path]:
    return sorted(
        p
        for p in API_DIR.rglob("*.py")
        if "/tests/" not in p.as_posix() and "__pycache__" not in p.as_posix()
    )


def _imports_the_connector(node: ast.AST) -> bool:
    """``import api.connectors.openmeteo`` · ``from api.connectors.openmeteo import …``
    · ``from api.connectors import openmeteo`` — الإملاءاتُ الثلاثة سواء."""
    if isinstance(node, ast.Import):
        return any(
            alias.name == CONNECTOR_MODULE or alias.name.startswith(CONNECTOR_MODULE + ".")
            for alias in node.names
        )
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == CONNECTOR_MODULE or module.startswith(CONNECTOR_MODULE + "."):
            return True
        if module.endswith("connectors") or module.endswith("api.connectors"):
            return any(alias.name == "openmeteo" for alias in node.names)
    return False


def markers_in_source(source: str) -> list[str]:
    """العلاماتُ الحقيقيّةُ في الكود — لا في نثره.

    تُعيد قائمةً مرتّبةً كترتيب ``DIRECT_WIRING_MARKERS``. ملفٌّ يذكر الموصّلَ في
    تعليقٍ أو سلسلةٍ نصّيّة **لا يُعدّ مخالفاً**، وملفٌّ يستوردُه بأيّ إملاء يُعدّ.
    """
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if _imports_the_connector(node):
            found.add(MODULE_MARKER)
        elif isinstance(node, ast.Name) and node.id in FETCHER_MARKERS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FETCHER_MARKERS:
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom | ast.Import):
            for alias in node.names:
                if alias.name in FETCHER_MARKERS:
                    found.add(alias.name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in (
            FETCHER_MARKERS
        ):
            # الموصّلُ نفسُه يُعرّفها — فيبقى «بيتاً مشروعاً» يحمل علاماتِه.
            found.add(node.name)
    return [m for m in DIRECT_WIRING_MARKERS if m in found]


def _offending_files() -> dict[str, list[str]]:
    return {
        rel: markers
        for rel, markers in (
            (_rel(p), markers_in_source(p.read_text(encoding="utf-8", errors="ignore")))
            for p in _api_py_files()
        )
        if markers
    }


def test_allowlist_markers_match_the_guard():
    allow = _load_allowlist()
    assert set(allow["direct_wiring_markers"]) == set(DIRECT_WIRING_MARKERS)


def test_the_detector_reads_code_not_prose():
    """يُغلَق الفحصُ على نفسه: لو صار الكشفُ نصّيّاً ثانيةً لاحمرّ هذا السطر.

    الحالةُ الأولى هي التي أوقعتني: تعليقٌ يشرح هجرَ الموصّل كان يُبقي الملفَّ
    مخالفاً. والثانيةُ هي الثقب المقيس: إملاءٌ آخرُ للاستيراد لا يُطابِق أيّ سلسلة.
    """
    prose_only = '# نستورد api.connectors.openmeteo? لا — هُجِر.\nX = "fetch_current"\n'
    assert markers_in_source(prose_only) == []

    aliased_import = "from api.connectors import openmeteo\n\n\nasync def f(a, b):\n    return await openmeteo.fetch_bundle(a, b)\n"
    assert markers_in_source(aliased_import) == [MODULE_MARKER, "fetch_bundle"]


def test_every_direct_openmeteo_reference_is_a_home_or_documented_residual():
    allow = _load_allowlist()
    allowed = set(allow.get("legitimate_homes", {})) | set(
        allow.get("composite_residuals_pending_p4", {})
    )

    offenders = [
        f"{rel}: {markers}" for rel, markers in _offending_files().items() if rel not in allowed
    ]
    assert not offenders, (
        "New direct Open-Meteo wiring must go through weather-service "
        "(api/weather_service_client.py) or the provider adapter "
        "(api/connectors/openmeteo.py), or be documented as a residual in "
        "weather_direct_wiring_allowlist.json: " + repr(offenders[:20])
    )


def test_allowlist_residuals_and_homes_are_not_stale():
    """Every allowlisted file must exist and actually still reference a marker (no dead
    entries that would hide a future regression)."""
    allow = _load_allowlist()
    listed = set(allow.get("legitimate_homes", {})) | set(
        allow.get("composite_residuals_pending_p4", {})
    )
    stale: list[str] = []
    for rel in listed:
        path = PLATFORM / rel
        if not path.exists():
            stale.append(f"{rel}: missing file")
            continue
        # weather_service_client.py is a sanctioned home that does not import the openmeteo
        # markers (it speaks to weather-service), so it is exempt from the "must reference a
        # marker" check.
        if rel == "api/weather_service_client.py":
            continue
        if not markers_in_source(path.read_text(encoding="utf-8", errors="ignore")):
            stale.append(f"{rel}: no longer references any direct marker (remove from allowlist)")
    assert not stale, repr(stale)


def test_legitimate_homes_are_exactly_the_two_sanctioned_files():
    allow = _load_allowlist()
    assert set(allow.get("legitimate_homes", {})) == {
        "api/connectors/openmeteo.py",
        "api/weather_service_client.py",
    }


def test_the_documented_residuals_only_ever_shrink():
    """**قائمةُ الإعفاء صارت راتشِتاً ينزل ولا يصعد.**

    العطلُ الذي يعالجه هذا الفحص ليس في المُعفَين بل في **الإعفاء نفسِه**: كانت
    القائمةُ تمنع مخالفاً *جديداً* ولا تقيس شيئاً عن القائمين. فكلُّ متبقٍّ موسومٌ
    «pending P4» منذ الكنسِ الأوّل، ولا سطرَ في الشجرة كلِّها يحمرّ إن بقي كما هو
    إلى الأبد. إعفاءٌ بلا سقفٍ نازل **ليس ديناً مؤجَّلاً بل شطبٌ صامت**.

    والسقفُ يُخفَض مع كلِّ نقلٍ فعليّ (هذه الشريحة: ١٠ ⇒ ٩ بنقل
    ``field_workspace_weather.py`` خلف ``weather_service_client``). ورفعُه يتطلّب
    تعديلَ هذا الرقم صراحةً — فيُرى في المراجعة بدل أن يمرّ.
    """
    allow = _load_allowlist()
    ceiling = allow["composite_residuals_ceiling"]
    residuals = allow.get("composite_residuals_pending_p4", {})
    assert len(residuals) <= ceiling, (
        f"المتبقّياتُ {len(residuals)} فوق السقف {ceiling} — الإعفاءُ يتوسّع لا ينحسر: "
        f"{sorted(residuals)}"
    )
    assert len(residuals) == ceiling, (
        f"السقفُ {ceiling} والمقيسُ {len(residuals)} — أُغلِق متبقٍّ ولم يُخفَض السقفُ معه، "
        "فالراتشِتُ يسمح بعودته صامتاً. اخفض `composite_residuals_ceiling`."
    )


def test_final_sweep_contract_is_documented():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "P3.5" in text
    assert "Weather Direct Wiring Final Sweep" in text
    assert "api/weather_service_client.py" in text
    assert "api/connectors/openmeteo.py" in text
    status = _load_allowlist().get("final_sweep_status", "")
    assert "P3.5" in status
