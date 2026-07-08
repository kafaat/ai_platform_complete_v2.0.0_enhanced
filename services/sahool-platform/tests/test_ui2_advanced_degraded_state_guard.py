"""Guard: advanced UI pages must use one shared degraded/feature-disabled contract.

This prevents the old pattern where every advanced page invented its own 404/503
handling, causing pages to collapse differently when a backend service is disabled or
temporarily unavailable. Feature-disabled (404) remains explicit. Availability failures
(502/503/504) become degraded mode. Auth failures (401/403) remain hard errors.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_shared_advanced_service_state_contract_exists():
    src = read("frontend/src/components/product/AdvancedServiceState.tsx")
    assert "AVAILABILITY_STATUS_CODES = [502, 503, 504]" in src
    assert "PERMISSION_STATUS_CODES = [401, 403]" in src
    assert "isFeatureDisabledError" in src
    assert "isAvailabilityError" in src
    assert "isPermissionError" in src
    assert "<FeatureDisabledState page={page}" in src
    assert "<DegradedState" in src
    assert "لا تملك صلاحيّة عرض هذه البيانات" in src
    assert "لا تُعرَض أرقام مُلفَّقة" in src


def test_critical_advanced_pages_use_shared_state_contract():
    pages = {
        "frontend/src/sections/DecisionConfidencePage.tsx": "decision-confidence",
        "frontend/src/sections/ExecutionFeedbackPage.tsx": "execution-feedback",
        "frontend/src/sections/EvidenceMapPage.tsx": "evidence-map",
        "frontend/src/sections/ReplayMapPage.tsx": "replay-map",
        "frontend/src/sections/AgronomicTimelinePage.tsx": "agronomic-timeline",
    }
    for rel, page_id in pages.items():
        src = read(rel)
        assert "AdvancedServiceState" in src, rel
        assert f'page="{page_id}"' in src, rel
        # The old ad-hoc featureOff branches should not reappear in these pages.
        assert "const featureOff" not in src, rel
        assert "asApiError(query.error).response?.status === 404" not in src, rel


def test_gis_expert_degrades_when_any_catalog_source_is_unavailable():
    src = read("frontend/src/sections/GisExpertPage.tsx")
    assert "isAvailabilityError" in src
    assert "serviceDegraded" in src
    assert "كتالوج GIS يعمل في وضع متدهور" in src
    assert "لا تُستبدل القيم الناقصة بأرقام مُخترعة" in src
    assert "landingQ.refetch()" in src
    assert "cacheQ.refetch()" in src
