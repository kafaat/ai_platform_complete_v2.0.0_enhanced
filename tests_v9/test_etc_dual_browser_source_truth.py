"""The browser cannot silently replace the weather owner's ET0/ETc truth.

Source-level guard intentionally covers the client boundary, not agricultural
math: numeric parity of two formulas would NOT prove provenance parity.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "frontend/src/services/api.ts"
BACKEND = ROOT / "services/sahool-platform/api/routers/etc_dual.py"


def _client_source() -> str:
    return API.read_text(encoding="utf-8")


def _compute_function(text: str) -> str:
    start = "export const computeFieldEtcDual ="
    end = "// ── توزيع ماء المزرعة"
    assert text.count(start) == 1, "missing or duplicate ETc client entrypoint"
    assert end in text[text.index(start) :]
    return text[text.index(start) : text.index(end, text.index(start))]


def test_etc_dual_client_uses_single_canonical_backend() -> None:
    src = _client_source()
    body = _compute_function(src)
    assert "kongApi.post<EtcDualResult>" in body
    assert "/api/v1/fields/" in body and "/etc-dual" in body
    assert "encodeURIComponent(fieldId)" in body
    assert "catch (" not in body and ".catch(" not in body
    assert "localEtcDualFallback" not in src
    assert "client_fallback" not in src


def test_etc_dual_backend_still_uses_canonical_weather_engine() -> None:
    src = BACKEND.read_text(encoding="utf-8")
    assert "get_et0_product(" in src
    assert "et0_unavailable_http_exception" in src
    assert "fail-closed" in src
    assert "et0_override=float(et0_mm)" in src


def test_negative_control_detects_synthetic_browser_fallback() -> None:
    src = _client_source()
    mutant = src.replace(
        "// ET0/ETc are owned by the backend weather and crop engines.",
        "function localEtcDualFallback() { return { stage: 'client_fallback' }; }\n"
        "// ET0/ETc are owned by the backend weather and crop engines.",
        1,
    )
    assert mutant != src
    assert "localEtcDualFallback" in mutant
    assert "client_fallback" in mutant
    assert "localEtcDualFallback" not in src
