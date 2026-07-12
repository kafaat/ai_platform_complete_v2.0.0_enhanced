from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_does_not_present_contract_service_as_compute_owner():
    files = [
        ROOT / "frontend/src/sections/DashboardPage.tsx",
        ROOT / "frontend/src/sections/SettingsPage.tsx",
        ROOT / "frontend/src/services/api/client.ts",
    ]
    text = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert "33 مؤشر + WOFOST" not in text
    assert "جارٍ تحميل البيانات من indicators-service" not in text
    assert "ownership/catalog contract only" in text


def test_legacy_direct_sentinel_path_is_removed_and_fail_closed():
    text = (ROOT / "sentinel_hub/vegetation_real.py").read_text(encoding="utf-8")
    assert "LEGACY_DIRECT_SENTINEL_ENABLED = False" in text
    assert "raster-service is the production owner" in text
    assert "EVALSCRIPT_ALL_INDICES" not in text
    assert "evaluatePixel" not in text
    assert "services.sentinel-hub.com" not in text
    assert "direct Sentinel-Hub computation was removed" in text
