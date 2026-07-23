from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile" / "sahool_app" / "lib"


def test_device_identity_is_persistent_and_not_deleted_on_logout():
    device = (MOBILE / "services" / "device_id_service.dart").read_text()
    auth = (MOBILE / "services" / "auth_service.dart").read_text()
    assert "field_forms_device_id" in device
    assert "Random.secure()" in device
    clear = auth.split("Future<void> clearAuth()", 1)[1].split("// F13", 1)[0]
    assert "deleteAll" not in clear
    assert "field_forms_device_id" not in clear


def test_submission_sends_device_header_and_coordinator_uses_shared_dio():
    api = (MOBILE / "features/field_forms/data/field_forms_api.dart").read_text()
    coord = (MOBILE / "features/field_forms/data/field_forms_coordinator.dart").read_text()
    service = (MOBILE / "services/api_service.dart").read_text()
    assert "'X-Device-Id': deviceId" in api
    assert "FieldFormsApi(ApiService.instance.dio)" in coord
    assert "Dio get dio => _dio" in service


def test_authenticated_startup_and_field_open_are_wired():
    main = (MOBILE / "main.dart").read_text()
    workspace = (MOBILE / "screens/field_workspace_screen.dart").read_text()
    assert "FieldFormsCoordinator.instance.init()" in main
    assert "FieldFormsCoordinator.instance.dispose()" in main
    assert "FieldFormsCoordinator.instance.syncField(_fieldId)" in workspace


def test_dependabot_tracks_sha_pinned_actions():
    dep = (ROOT / ".github/dependabot.yml").read_text()
    assert 'package-ecosystem: "github-actions"' in dep
    assert 'interval: "weekly"' in dep
