from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_api_client_core_is_split_from_legacy_facade():
    facade = read("frontend/src/services/api.ts")
    client = read("frontend/src/services/api/client.ts")

    assert "from './api/client'" in facade
    assert "export {" in facade and "kongApi" in facade and "authApi" in facade
    assert "axios.create" not in facade
    assert "function makeClient" not in facade
    assert "import axios" in client
    assert "function makeClient" in client
    assert "export const kongApi" in client
    assert "export const authApi" in client
    assert "export async function tryReal" in client


def test_api_client_preserves_gateway_and_auth_guards():
    client = read("frontend/src/services/api/client.ts")
    assert "ENDPOINTS.kong" in client
    assert "ENDPOINTS.auth" in client
    assert "getAccessToken" in client
    assert "isAccessTokenExpired" in client
    assert "X-Tenant-ID" in client
    assert "sahool:auth:unauthorized" in client
    assert "استجابة غير صالحة من الخادم" in client


def test_legacy_api_facade_keeps_existing_call_sites_stable():
    facade = read("frontend/src/services/api.ts")
    # Phase 1 must not force all frontend imports to change in one PR.
    assert "login" in facade and "from './api/auth'" in facade
    assert "AuthResponse" in facade and "export type" in facade
    assert "apiErrorMessage" in facade
    assert "getFeatureRegistry" in facade and "from './api/features'" in facade
