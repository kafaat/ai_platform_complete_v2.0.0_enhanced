"""SCOUT-PHOTO (v260): source-level contracts for the Dart photo + offline integration.

These are NOT a replacement for ``flutter analyze`` / ``flutter test`` or a real device; the
behaviour is covered by the Dart tests named below, which need the Flutter SDK.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "mobile" / "sahool_app"


def read(part: str) -> str:
    return (M / part).read_text(encoding="utf-8")


def test_two_distinct_receipts_and_exact_photo_sha():
    api = read("lib/features/scouting/data/scouting_api.dart")
    cubit = read("lib/features/scouting/presentation/new_observation_cubit.dart")
    assert "'/api/v1/scouting-media/fields/" in api
    assert "headers: {'X-Content-SHA256': digest}" in api
    for snippet in (
        "body['persisted'] != true",
        "body['sha256'] != digest",
        "body['field_id'] != fieldId",
        "body['pin_id'] != pinId",
        "body['verification_state'] != 'bytes_verified'",
        "body['review_state'] != 'unreviewed'",
    ):
        assert snippet in api
    pin_call = cubit.index("await _api.createPin(")
    photo_call = cubit.index("await _sendPhoto(online: true);", pin_call)
    assert pin_call < photo_call
    assert "await _api.uploadPinPhoto(" in cubit
    body = cubit[
        cubit.index("Map<String, dynamic> buildBody()") : cubit.index("static bool isTransient")
    ]
    returned = body.split("return {", 1)[-1]
    assert "photo_uri" not in returned and "'photo'" not in returned


def test_offline_photo_queued_after_pin_and_replayed_as_exact_bytes():
    cubit = read("lib/features/scouting/presentation/new_observation_cubit.dart")
    api = read("lib/features/scouting/data/scouting_api.dart")
    outbox = read("lib/features/offline_sync/data/offline_sync_api.dart")
    assert "const String kObservationPhotoKind = 'observation_photo_upload';" in api
    assert "kind: 'observation_create'" in cubit
    assert "kind: kObservationPhotoKind" in cubit
    assert "body: {'field_id': field.id, 'pin_id': pinId, 'sha256': digest}" in cubit
    assert "base64Encode" not in cubit, "photo bytes never go into the Hive outbox"
    for snippet in (
        "if (op.kind == kObservationPhotoKind)",
        "await _photos.find(pinId)",
        "await _photos.read(path)",
        "crypto.sha256.convert(bytes).toString() != digest",
        "verifyScoutingPhotoReceipt(response, fieldId, pinId, digest)",
        "op.path != scoutingPhotoPath(fieldId, pinId)",
        "op.fieldId != fieldId",
        "kOwnerGuardExtra",
        "kDurableRetryExtra",
        "data: bytes,",
        "headers: {'X-Content-SHA256': digest}",
        "kind: ApiErrorKind.unavailable",
    ):
        assert snippet in outbox, snippet


def test_photo_frozen_after_commit_and_retry_never_recreates_the_pin():
    cubit = read("lib/features/scouting/presentation/new_observation_cubit.dart")
    capture = cubit[
        cubit.index("Future<void> capturePhoto(") : cubit.index("Future<void> removePhoto(")
    ]
    assert "if (state.submitting || _committed) return;" in capture
    remove = cubit[
        cubit.index("Future<void> removePhoto(") : cubit.index(
            "Map<ObservationField, String> validate()"
        )
    ]
    assert "if (state.submitting || _committed) return;" in remove
    submit = cubit[
        cubit.index("Future<void> submit() async {") : cubit.index("final errors = validate();")
    ]
    assert "if (_committed) {" in submit
    assert "_api.createPin" not in submit


def test_local_photo_paths_fenced_for_write_read_delete_and_discovery():
    source = read("lib/features/scouting/data/device_sources.dart")
    assert "RegExp(r'^[A-Za-z0-9_-]{1,100}$')" in source
    assert "if (!isValidPinId(pinId))" in source
    assert "bytes.length > maxPhotoBytes" in source
    assert "final f = await _ownedPhotoFile(path);" in source
    assert "await _ownedPhotoFile(target.path);" in source
    assert "(await _ownedPhotoFile(path)).readAsBytes()" in source
    assert "File(path).resolveSymbolicLinks()" in source
    assert "canonical.startsWith('$canonicalDir/')" in source


def test_remote_preview_is_short_lived_and_unreviewed():
    view = read("lib/features/scouting/presentation/scouting_widgets.dart")
    api = read("lib/features/scouting/data/scouting_api.dart")
    assert "deps.api" in view and ".photoForPin(pin.fieldId, pin.pinId)" in view
    assert "Image.network(" in view
    assert "غير معتمدة تشخيصياً" in view
    assert "!url.startsWith('https://')" in api


def test_pin_receipt_must_name_this_pin():
    outbox = read("lib/features/offline_sync/data/durable_offline_outbox.dart")
    assert "response['persisted'] != true" in outbox
    assert "response['pin_id'] != r.op.body['pin_id']" in outbox
    assert "(r.op.fieldId != null && response['field_id'] != r.op.fieldId)" in outbox
    assert "'observation_photo'" not in outbox, (
        "v257's pin-photo outbox kind is gone: the photo travels as observation_photo_upload to "
        "scout_photo_evidence (owner decision 2026-11-13)"
    )


def test_no_second_photo_link_on_the_pin():
    """Owner decision 2026-11-13: no documents-registry photo on the pin, on any client."""
    models = read("lib/features/scouting/data/scouting_models.dart")
    api = read("lib/features/scouting/data/scouting_api.dart")
    for src in (models, api, read("lib/features/scouting/presentation/scouting_widgets.dart")):
        assert "photoDocumentId" not in src
        assert "document_id" not in src
    assert "pinPhotoStored" not in api, (
        "v257's pin-photo receipt check is gone: scout_photo_evidence is the photo's single source"
    )


def test_crypto_is_a_direct_dependency():
    pubspec = read("pubspec.yaml")
    assert "\n  crypto: ^3.0.7\n" in pubspec
    lock = read("pubspec.lock")
    entry = lock[lock.index("\n  crypto:\n") :].split("\n  cupertino_icons:")[0]
    assert 'dependency: "direct main"' in entry


def test_dart_tests_for_this_behaviour_exist():
    for rel in (
        "test/features/offline_sync/scout_photo_outbox_api_test.dart",
        "test/features/scouting/device_photo_path_safety_test.dart",
    ):
        assert (M / rel).is_file(), rel
    cubit_test = read("test/features/scouting/new_observation_cubit_test.dart")
    assert "group('photo evidence upload (v260, scout-ingest)'" in cubit_test


def test_mobile_photo_context_never_treats_inference_as_authorization():
    """Owner phase 4: the pin sheet shows the server's evidence context, never a decision."""
    api = read("lib/features/scouting/data/scouting_api.dart")
    widgets = read("lib/features/scouting/presentation/scouting_widgets.dart")
    tests = read("test/features/scouting/scouting_api_test.dart")
    assert "Future<Map<String, dynamic>> photoEvidenceContext" in api
    assert "data['schema'] != 'sahool.scout-photo-evidence-context/v1'" in api
    assert "data['automatic_pesticide_action_authorized'] != false" in api
    assert "decision['state'] != 'not_authorized'" in api
    assert "source['field_id'] != fieldId" in api
    assert "evidence['pin_id'] != pinId" in api
    assert ".photoEvidenceContext(pin.fieldId, pin.pinId)" in widgets
    assert "لا يجيز هذا الدليل الرش تلقائياً" in widgets
    assert "group('authoritative photo context'" in tests


def test_mobile_season_event_api_validates_receipt_and_shows_distinct_statuses():
    """Owner phase 5 (v262): an explicit link event, its receipt checked against the request."""
    api = read("lib/features/scouting/data/scouting_api.dart")
    widgets = read("lib/features/scouting/presentation/scouting_widgets.dart")
    tests = read("test/features/scouting/scouting_api_test.dart")
    assert "Future<Map<String, dynamic>> appendPhotoSeasonLinkEvent" in api
    assert "r['event_id'] != eventId" in api
    assert "season['link_event_id'] != eventId" in api
    assert "r['automatic_pesticide_action_authorized'] != false" in api
    assert "verifyScoutingPhotoSeasonContext(asJsonMap(r['season']))" in api
    assert "kScoutPhotoSeasonLinkProof = 'scout_photo_season_link_events:v262'" in api
    for state in ("linked_accepted", "linked_not_accepted", "revoked", "explicit_link_required"):
        assert state in api
    assert "الموسم مرتبط صراحةً" in widgets
    assert "رابط الموسم موجود لكن سجله غير معتمد" in widgets
    assert "أُلغي رابط الموسم" in widgets
    assert "group('human photo-season link event POST'" in tests


def test_mobile_season_link_proof_matches_the_server():
    import sys

    service = str(ROOT / "services" / "scout-ingest-service")
    if service not in sys.path:
        sys.path.insert(0, service)
    import media_api

    api = read("lib/features/scouting/data/scouting_api.dart")
    assert f"kScoutPhotoSeasonLinkProof = '{media_api.SEASON_LINK_PROOF}'" in api


def test_a_refused_field_grant_is_not_queued_as_offline():
    """Owner phase 6 (v263): a 403 is a missing field grant, not a network failure."""
    cubit = read("lib/features/scouting/presentation/new_observation_cubit.dart")
    at = cubit.index("if (!isTransient(err)) {")
    branch = cubit[at : cubit.index("OutboxReceipt receipt;", at)]
    assert "err.statusCode == 403" in branch and "return _photoState(" in branch
    assert "لغياب تفويض هذا الحقل" in branch
