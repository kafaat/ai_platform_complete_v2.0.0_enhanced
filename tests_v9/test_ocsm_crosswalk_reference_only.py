"""حارس SEM-OCSM-01 / ADR-0034 — «مرجع لا تبنٍّ» + برهان سلبيّ.

يفرض أنّ crosswalk الـOCSM بقي **خريطة مرجعيّة** ولم يتسرّب إلى عقود runtime:
  (١) الـADR موجود، بنسخة OCSM المثبَّتة (SHA) والعناقيد الأربعة.
  (٢) لا `w3id.org/ocsm` ولا استيراد/مُسلسِل OCSM في ``shared/contracts/`` —
      برهان بنيويّ ضدّ «adoption جملة» متسلّل (القاعدة: مرجع/خوارزمية بمراجعة/adapter
      خلف عقد محايد — لا تبنٍّ جملة).
  (٣) برهان سلبيّ: كاشف التسرّب يرصد انتهاكاً مُصطنَعاً.

فحص ساكن على الملفّات — لا قاعدة/خدمات/شبكة.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ADR = _ROOT / "docs" / "adr" / "ADR-0034-sahool-ocsm-crosswalk.md"
_CONTRACTS = _ROOT / "shared" / "contracts"

# آثار تسرّب OCSM إلى عقود runtime (يجب ألّا تظهر في shared/contracts):
_LEAK_MARKERS = ("w3id.org/ocsm", "main-context.jsonld", "openagri-ocsm")
_PINNED_OCSM_SHA = "12863f1bff88311f2274e80e691c8888bcb8af00"
_CLUSTERS = ("Field/Parcel", "Season/Crop", "Irrigation", "Weather/Soil observation")


def test_adr_exists_with_pinned_ocsm_and_four_clusters() -> None:
    assert _ADR.exists(), "ADR-0034 مفقود"
    text = _ADR.read_text(encoding="utf-8")
    assert _PINNED_OCSM_SHA in text, "نسخة OCSM غير مثبَّتة بالـSHA في الـADR"
    assert "CC-BY-4.0" in text, "رخصة OCSM غير موثّقة"
    for cluster in _CLUSTERS:
        assert cluster in text, f"العنقود غائب عن الـADR: {cluster}"


def _leak_hits(root: Path) -> list[str]:
    """ملفّات عقود runtime تحمل أثر تسرّب OCSM (يجب أن تكون فارغة)."""
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in (".py", ".json"):
            continue
        try:
            body = path.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeDecodeError):
            continue
        if any(m in body for m in _LEAK_MARKERS):
            hits.append(str(path.relative_to(root)))
    return hits


def test_ocsm_did_not_leak_into_runtime_contracts() -> None:
    """العقود الحيّة خالية من أثر OCSM — الخريطة مرجع لا تبنٍّ."""
    hits = _leak_hits(_CONTRACTS)
    assert not hits, f"تسرّب OCSM إلى عقود runtime (adoption متسلّل): {hits}"


def test_negative_proof_leak_detector_flags_violation(tmp_path: Path) -> None:
    """كاشف التسرّب يجب أن يرصد ملفّ عقد يحمل مرجع OCSM حرفيّاً."""
    (tmp_path / "leaky.py").write_text(
        'CONTEXT = "https://w3id.org/ocsm/main-context.jsonld"\n', encoding="utf-8"
    )
    assert _leak_hits(tmp_path), "الكاشف فشل في رصد تسرّب مُصطنَع"
    # ومجلّد نظيف لا يُبلّغ عن تسرّب:
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "ok.py").write_text('FIELD = "field_id"\n', encoding="utf-8")
    assert not _leak_hits(clean), "الكاشف أبلغ عن تسرّب في مجلّد نظيف"
