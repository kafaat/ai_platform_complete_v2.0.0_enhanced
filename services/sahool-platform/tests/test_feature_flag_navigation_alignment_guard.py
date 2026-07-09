from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_backend_exposes_runtime_feature_registry_endpoint():
    router = read("services/sahool-platform/api/routers/features.py")
    registry = read("services/sahool-platform/api/feature_registry.py")
    assert '@router.get("/api/v1/features")' in router
    assert "FEATURE_FLAGS" in router
    assert "is_enabled(name, os.getenv(name))" in router
    assert "FEATURE_DECISION_CONFIDENCE" in router
    assert "FEATURE_LEARNING_DASHBOARD" in router
    assert "FEATURE_DECISION_CONFIDENCE" in registry


def test_frontend_nav_uses_backend_runtime_feature_registry():
    hook = read("frontend/src/hooks/useFeatureRegistry.ts")
    nav = read("frontend/src/components/shell/NavRail.tsx")
    app = read("frontend/src/App.tsx")
    api = read("frontend/src/services/api.ts")
    features = read("frontend/src/services/api/features.ts")
    assert "getFeatureRegistry" in api
    assert "from './api/features'" in api
    assert "'/api/v1/features'" in features
    assert "useFeatureRegistry" in hook
    assert "isRuntimePageEnabled" in hook
    assert "advancedFeatureForPage" in hook
    assert "useFeatureRegistry" in nav
    assert "isRuntimePageEnabled(r.id, featureRegistry)" in nav
    assert "FeatureDisabledState page={page}" in app


def test_runtime_registry_is_fail_open_but_hides_explicit_disabled_pages_after_load():
    hook = read("frontend/src/hooks/useFeatureRegistry.ts")
    assert "if (!registry.loaded || registry.unavailable) return true" in hook
    assert "registry.flags[feature.backendFlag]" in hook
    assert "byBackend === false" in hook
    assert "pages[item.page] = Boolean(item.enabled)" in hook
