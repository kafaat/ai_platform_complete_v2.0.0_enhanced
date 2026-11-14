"""Guard the web client's ET0/ETc source-of-truth boundary.

A numerical match between independent formulas does not prove provenance parity.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "frontend/src/services/api.ts"
BACKEND = ROOT / "services/sahool-platform/api/routers/etc_dual.py"
LEGACY_LOCAL_FUNCTION = "".join(("local", "Etc", "Dual", "Fallback"))
LEGACY_STAGE = "".join(("client", "_fall", "back"))


def _client_source() -> str:
    return API.read_text(encoding="utf-8")


def _compute_function(text: str) -> str:
    start = "export const computeFieldEtcDual ="
    end = "// ── توزيع ماء المزرعة"
    assert text.count(start) == 1, "missing or duplicate ETc client entrypoint"
    assert end in text[text.index(start) :]
    return text[text.index(start) : text.index(end, text.index(start))]


def _assert_canonical_client(text: str) -> None:
    body = _compute_function(text)
    assert "kongApi.post<EtcDualResult>" in body
    assert "/api/v1/fields/" in body and "/etc-dual" in body
    assert "encodeURIComponent(fieldId)" in body
    assert "catch (" not in body and ".catch(" not in body
    assert LEGACY_LOCAL_FUNCTION not in text
    assert LEGACY_STAGE not in text


def test_etc_dual_client_uses_single_canonical_backend() -> None:
    _assert_canonical_client(_client_source())


def test_etc_dual_backend_still_uses_canonical_weather_engine() -> None:
    src = BACKEND.read_text(encoding="utf-8")
    assert "get_et0_product(" in src
    assert "et0_unavailable_http_exception" in src
    assert "fail-closed" in src
    assert "et0_override=float(et0_mm)" in src


def test_negative_control_detects_synthetic_browser_fallback() -> None:
    src = _client_source()
    anchor = "// ET0/ETc are owned by the backend weather and crop engines."
    assert anchor in src
    injected = (
        "function "
        + LEGACY_LOCAL_FUNCTION
        + "() { return {stage: '"
        + LEGACY_STAGE
        + "'}; }\n"
    )
    mutant = src.replace(anchor, injected + anchor, 1)
    assert mutant != src
    with pytest.raises(AssertionError):
        _assert_canonical_client(mutant)
