from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_auth_and_feature_registry_are_extracted_from_legacy_facade():
    facade = read("frontend/src/services/api.ts")
    auth = read("frontend/src/services/api/auth.ts")
    features = read("frontend/src/services/api/features.ts")

    assert "from './api/auth'" in facade
    assert "from './api/features'" in facade
    assert "export const login" not in facade
    assert "export interface AuthResponse" not in facade
    assert "export const getFeatureRegistry" not in facade

    assert "export const login" in auth
    assert "export const register" in auth
    assert "export const logout" in auth
    assert "export function apiErrorMessage" in auth
    assert "export function isMfaRequiredError" in auth
    assert "authApi" in auth

    assert "export const getFeatureRegistry" in features
    assert "FeatureRegistryItem" in features
    assert "FeatureRegistryResponse" in features
    assert "kongApi.get<FeatureRegistryResponse>('/api/v1/features')" in features


def test_legacy_facade_still_reexports_auth_and_feature_contracts():
    facade = read("frontend/src/services/api.ts")
    assert "login," in facade
    assert "register," in facade
    assert "getCurrentUser," in facade
    assert "apiErrorMessage," in facade
    assert "AuthResponse," in facade
    assert "InviteableRole," in facade
    assert "FeatureRegistryItem" in facade
    assert "FeatureRegistryResponse" in facade


def test_auth_module_imports_only_shared_clients_and_no_direct_urls():
    auth = read("frontend/src/services/api/auth.ts")
    assert "from './client'" in auth
    assert "authApi" in auth
    assert "kongApi" in auth
    assert "axios.create" not in auth, (
        "عميلٌ خاصّ يتجاوز الاعتراضات المشتركة (توكن · تجديد · X-Tenant-Id)"
    )
    assert "localhost" not in auth, "عنوانٌ مُصلَّب يعمل على جهاز المطوّر ويكسر كلّ نشر"
    assert "127.0.0.1" not in auth, "عنوانٌ مُصلَّب يعمل على جهاز المطوّر ويكسر كلّ نشر"
