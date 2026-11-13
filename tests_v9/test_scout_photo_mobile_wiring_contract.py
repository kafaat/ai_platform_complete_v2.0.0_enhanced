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
    assert "base64Encode" not in cubit  # bytes never go into the Hive outbox
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
    assert "'observation_photo'" not in outbox


def test_no_second_photo_link_on_the_pin():
    """Owner decision 2026-11-13: no documents-registry photo on the pin, on any client."""
    models = read("lib/features/scouting/data/scouting_models.dart")
    api = read("lib/features/scouting/data/scouting_api.dart")
    for src in (models, api, read("lib/features/scouting/presentation/scouting_widgets.dart")):
        assert "photoDocumentId" not in src
        assert "document_id" not in src
    assert "pinPhotoStored" not in api


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
