from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/architecture/GATEWAY_SPLIT_CONTRACT.md"


def test_gateway_split_contract_declares_extracted_domain_routes():
    text = CONTRACT.read_text(encoding="utf-8")
    for marker in (
        "frontend → gateway → raster-service",
        "frontend → gateway → weather-service",
        "frontend → gateway → decision-service",
        "frontend → gateway → sahool-platform",
    ):
        assert marker in text


def test_gateway_split_prevents_new_domain_routes_back_to_platform():
    text = CONTRACT.read_text(encoding="utf-8")
    assert (
        "must not point new raster/weather/decision domain routes back into `sahool-platform`"
        in text
    )
