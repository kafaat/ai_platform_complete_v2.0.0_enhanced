"""RECOMMENDATION-CROP-PICKER-UNRESOLVABLE-ENTRY-01 — كلّ خيار في منتقيات المحاصيل يُحلّ إلى بطاقة.

**العطل:** منتقي المحاصيل في الويب (``RecommendationPage`` وإضافة/تعديل الحقل وخطوة الموسم
وإضافة الموسم) والموبايل (``kEngineCrops`` ومعالج إنشاء الحقل) عرض «خضروات» (والموبايل
``vegetables``/``fruits``/``other``) — قيمٌ لا تُحلّ إلى أيّ بطاقة محصول. وبعد ربط مستهلك دفتر
العناصر بالمعرّف القانونيّ (``api/agronomic_state_consumers._crop_identity_limitation``) صار
اختيارها يحجب نصيحة العناصر دائماً بـ``NUTRIENT_LEDGER_CROP_UNRESOLVED`` بلا طريقٍ للإصلاح.

**ما يُثبته هذا الملفّ (offline، قراءة مصدر فقط):** القوائم تُقرأ من مصادرها الحقيقيّة
(``frontend/src/lib/cropOptions.ts`` + ملفّا Dart) وتُمرَّر عبر المحلِّل القانونيّ نفسه
``core.season_phenology.resolve_crop_id`` وسجلّ البطاقات ``core.crop_cards.loader`` — لا
بالعين. ولا تبقى قائمة محاصيل حرفيّة محلّيّة في الويب خارج القاموس المشترك.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sahool_platform_path import ensure_platform_path

pytestmark = pytest.mark.unit
ensure_platform_path()

from core.crop_cards.loader import load_crop_card  # noqa: E402
from core.season_phenology import resolve_crop_id  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB_OPTIONS = ROOT / "frontend" / "src" / "lib" / "cropOptions.ts"
WEB_SRC = ROOT / "frontend" / "src"
MOBILE_ADVISOR = (
    ROOT
    / "mobile"
    / "sahool_app"
    / "lib"
    / "features"
    / "advisor"
    / "presentation"
    / "recommendations_screen.dart"
)
MOBILE_WIZARD = (
    ROOT
    / "mobile"
    / "sahool_app"
    / "lib"
    / "features"
    / "fields"
    / "presentation"
    / "field_create_wizard.dart"
)


def _block(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i + len(start) : j]


def _quoted(block: str) -> list[str]:
    return re.findall(r"'([^']*)'", block)


def _web_options() -> list[tuple[str, str]]:
    block = _block(WEB_OPTIONS.read_text(encoding="utf-8"), "CROP_OPTIONS", "];")
    return re.findall(r"\{\s*id:\s*'([^']+)',\s*label:\s*'([^']+)'", block)


def _web_legacy() -> list[str]:
    text = WEB_OPTIONS.read_text(encoding="utf-8")
    return _quoted(_block(text, "LEGACY_GENERIC_CROP_VALUES: readonly string[] = [", "];"))


def _mobile_engine_crops() -> list[str]:
    text = MOBILE_ADVISOR.read_text(encoding="utf-8")
    return _quoted(_block(text, "const List<String> kEngineCrops = [", "];"))


def _mobile_legacy() -> list[str]:
    text = MOBILE_ADVISOR.read_text(encoding="utf-8")
    return _quoted(_block(text, "const Set<String> kLegacyGenericCrops = {", "};"))


def _mobile_wizard_crops() -> list[tuple[str, str]]:
    text = MOBILE_WIZARD.read_text(encoding="utf-8")
    block = _block(text, "static const _crops = {", "};")
    return re.findall(r"'([^']+)':\s*'([^']+)'", block)


def test_sources_parse_to_non_empty_lists() -> None:
    # حارس الحارس: محلِّلٌ لا يجد شيئاً كان سيُمرّر كلّ تأكيد بعده فارغاً.
    assert len(_web_options()) >= 8
    assert len(_mobile_engine_crops()) >= 8
    assert len(_mobile_wizard_crops()) >= 8
    assert "خضروات" in _web_legacy()
    assert "خضروات" in _mobile_legacy()


def test_every_web_option_is_a_card_and_its_label_resolves_to_it() -> None:
    options = _web_options()
    ids = [i for i, _ in options]
    labels = [label for _, label in options]
    assert len(set(ids)) == len(ids), "duplicate crop id in CROP_OPTIONS"
    assert len(set(labels)) == len(labels), "duplicate label in CROP_OPTIONS"
    bad = {
        label: (crop_id, resolve_crop_id(label))
        for crop_id, label in options
        if load_crop_card(crop_id) is None or resolve_crop_id(label) != crop_id
    }
    assert not bad, f"web crop options that do not resolve to their card: {bad}"


def test_mobile_engine_crops_mirror_web_and_resolve() -> None:
    labels = [label for _, label in _web_options()]
    assert _mobile_engine_crops() == labels, "kEngineCrops drifted from web CROP_OPTIONS"
    bad = [c for c in _mobile_engine_crops() if resolve_crop_id(c) is None]
    assert not bad, f"mobile engine crops with no crop card: {bad}"


def test_mobile_wizard_keys_are_canonical_card_ids_and_labels_agree() -> None:
    bad = {
        key: (label, resolve_crop_id(key), resolve_crop_id(label))
        for key, label in _mobile_wizard_crops()
        if load_crop_card(key) is None
        or resolve_crop_id(key) != key
        or resolve_crop_id(label) != key
    }
    assert not bad, f"mobile wizard crop entries not bound to a card: {bad}"


def test_legacy_generic_values_are_mirrored_and_really_unresolvable() -> None:
    # القيم التي تُعرَض «غير محدَّد — اختر المحصول» يجب ألّا تُحلّ فعلاً، وإلّا كانت الواجهة
    # تخفي محصولاً صالحاً؛ ولا تُعرَض أيٌّ منها كخيار.
    web, mobile = _web_legacy(), _mobile_legacy()
    assert sorted(web) == sorted(mobile)
    resolving = {v: resolve_crop_id(v) for v in web if resolve_crop_id(v) is not None}
    assert not resolving, f"legacy 'unspecified' values that do resolve: {resolving}"
    offered = (
        {label for _, label in _web_options()}
        | set(_mobile_engine_crops())
        | {k for k, _ in _mobile_wizard_crops()}
        | {v for _, v in _mobile_wizard_crops()}
    )
    assert not offered & set(web)


def test_no_local_crop_literal_list_in_web_pickers() -> None:
    # منتقي محصول جديد يقرأ من lib/cropOptions؛ قائمة حرفيّة محلّيّة تتجاوز هذا الحارس.
    literal = re.compile(r"\bconst\s+CROPS\s*=\s*\[")
    offenders = sorted(
        str(p.relative_to(ROOT))
        for p in WEB_SRC.rglob("*.ts*")
        if ".test." not in p.name and literal.search(p.read_text(encoding="utf-8"))
    )
    assert not offenders, f"local crop literal lists outside lib/cropOptions.ts: {offenders}"
