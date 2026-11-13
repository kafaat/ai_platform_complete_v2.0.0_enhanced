"""Source-level contracts for Dart photo + offline integration.

These are NOT a replacement for `flutter analyze`/`flutter test` or running devices.
"""
from pathlib import Path
import re
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
M = ROOT / 'mobile' / 'sahool_app'


def read(part):
    return (M / part).read_text(encoding='utf-8')


def test_two_distinct_receipts_and_exact_photo_sha():
    api = read('lib/features/scouting/data/scouting_api.dart')
    cubit = read('lib/features/scouting/presentation/new_observation_cubit.dart')
    assert "'X-Content-SHA256': digest" in api
    assert "response['persisted']" not in api  # actually body used via asJsonMap
    for snippet in ("body['persisted'] != true", "body['sha256'] != digest",
                    "body['field_id'] != fieldId", "body['pin_id'] != pinId",
                    "body['review_state'] != 'unreviewed'"):
        assert snippet in api
    assert 'await _api.createPin(' in cubit
    assert 'await _uploadPhotoOrQueue();' in cubit
    assert cubit.index('await _api.createPin(') < cubit.index('await _uploadPhotoOrQueue();', cubit.index('await _api.createPin('))
    assert 'photo_uri' not in cubit[cubit.index('Map<String, dynamic> buildBody()'):cubit.index('static bool isTransient')].split('return {', 1)[-1]


def test_offline_photo_queued_after_pin_and_replayed_as_exact_bytes():
    cubit = read('lib/features/scouting/presentation/new_observation_cubit.dart')
    outbox = read('lib/features/offline_sync/data/offline_sync_api.dart')
    assert "kind: 'observation_create'" in cubit
    assert "kind: 'observation_photo_upload'" in cubit
    assert 'final photoQueued = withPhoto ? await _queuePhoto()' in cubit
    assert 'crypto.sha256.convert(await _store.read(path))' in cubit
    for snippet in ("if (op.kind == 'observation_photo_upload')", "await _photos.find(pinId)",
                    "await _photos.read(path)", "crypto.sha256.convert(bytes)",
                    "verifyScoutingPhotoReceipt(response, fieldId, pinId, digest)",
                    'kOwnerGuardExtra', 'kDurableRetryExtra'):
        assert snippet in outbox
    assert "data: bytes," in outbox
    assert "headers: {'X-Content-SHA256': digest}" in outbox
    assert "kind: ApiErrorKind.unavailable" in outbox


def test_photo_local_read_scoped_by_tenant_and_remote_preview_unreviewed():
    device = read('lib/features/scouting/data/device_sources.dart')
    view = read('lib/features/scouting/presentation/scouting_widgets.dart')
    assert 'File(path).resolveSymbolicLinks()' in device
    assert "canonical.startsWith('$canonicalDir/')" in device
    assert "deps.api.photoForPin(pin.fieldId, pin.pinId)" in view
    assert 'Image.network(url' in view
    assert 'غير معتمدة تشخيصياً' in view


def test_observation_sync_does_not_erase_unrelated_success():
    outbox = read('lib/features/offline_sync/data/durable_offline_outbox.dart')
    assert "response['pin_id'] != r.op.body['pin_id']" in outbox
    assert "response['field_id'] != r.op.fieldId" in outbox
    assert "response['persisted'] != true" in outbox


def test_gateway_to_owner_is_feature_gated_and_no_public_object_ref():
    nginx = (ROOT / 'nginx/nginx.v9.conf').read_text()
    media = (ROOT / 'services/scout-ingest-service/media_api.py').read_text()
    migration = (ROOT / 'migrations/v256_scout_photo_evidence.sql').read_text()
    assert 'location ^~ /api/v1/scouting-media/' in nginx
    assert 'auth_request /_auth_verify;' in nginx
    assert '${SCOUT_MEDIA_SERVICE_TOKEN}' in nginx
    assert 'SCOUT_MEDIA_ENABLED' in media
    assert 'if not blob_store.s3_enabled()' in media
    assert 'raise HTTPException(503, "scout_media_store_unavailable")' in media
    assert '"object_ref"' not in media[media.index('def _public_row'):media.index('async def _read_row')]
    assert 'FOREIGN KEY (tenant_id, field_id, pin_id)' in migration
    assert 'FORCE ROW LEVEL SECURITY' in migration
    assert 'UNIQUE (tenant_id, field_id, pin_id)' in migration


def test_local_photo_paths_fenced_for_write_read_delete_and_discovery():
    source = read('lib/features/scouting/data/device_sources.dart')
    assert "RegExp(r'^[A-Za-z0-9_-]{1,100}$')" in source
    assert 'if (!isValidPinId(pinId))' in source
    assert 'if (bytes.isEmpty || bytes.length > 8 * 1024 * 1024)' in source
    assert 'final f = await _ownedPhotoFile(path);' in source
    assert 'await _ownedPhotoFile(target.path);' in source
    assert "canonical.startsWith('$canonicalDir/')" in source


def test_mobile_photo_context_never_treats_inference_as_authorization():
    api = read('lib/features/scouting/data/scouting_api.dart')
    widgets = read('lib/features/scouting/presentation/scouting_widgets.dart')
    tests = read('test/features/scouting/scouting_api_test.dart')
    assert 'Future<Map<String, dynamic>> photoEvidenceContext' in api
    assert "data['schema'] != 'sahool.scout-photo-evidence-context/v1'" in api
    assert "data['automatic_pesticide_action_authorized'] != false" in api
    assert "decision['state'] != 'not_authorized'" in api
    assert "source['field_id'] != fieldId" in api
    assert "evidence['pin_id'] != pinId" in api
    assert 'deps.api.photoEvidenceContext(pin.fieldId, pin.pinId)' in widgets
    assert 'لا يجيز هذا الدليل الرش تلقائياً' in widgets
    assert "group('authoritative photo context'" in tests


def test_mobile_season_event_api_validates_receipt_and_shows_distinct_statuses():
    api = read('lib/features/scouting/data/scouting_api.dart')
    widgets = read('lib/features/scouting/presentation/scouting_widgets.dart')
    tests = read('test/features/scouting/scouting_api_test.dart')
    assert 'Future<Map<String, dynamic>> appendPhotoSeasonLinkEvent' in api
    assert "data['season']" in api
    assert "r['event_id'] != eventId" in api
    assert "season['link_event_id'] != eventId" in api
    assert "r['automatic_pesticide_action_authorized'] != false" in api
    assert "verifyScoutingPhotoSeasonContext(asJsonMap(r['season']))" in api
    for state in ('linked_accepted', 'linked_not_accepted', 'revoked', 'explicit_link_required'):
        assert state in api
    assert 'الموسم مرتبط صراحةً' in widgets
    assert 'رابط الموسم موجود لكن سجله غير معتمد' in widgets
    assert 'أُلغي رابط الموسم' in widgets
    assert 'لا يجيز هذا الدليل الرش تلقائياً' in widgets
    assert "group('human photo-season link event POST'" in tests


def test_denied_photo_upload_does_not_claim_pending_sync():
    cubit = read('lib/features/scouting/presentation/new_observation_cubit.dart')
    segment = cubit[cubit.index('Future<void> _uploadPhotoOrQueue() async'):cubit.index('Future<void> _enqueue(', cubit.index('Future<void> _uploadPhotoOrQueue() async'))]
    assert "if (!isTransient(err))" in segment
    assert 'err.statusCode == 403' in segment
    assert 'اطلب منح الصلاحية' in segment
    assert segment.index('if (!isTransient(err))') < segment.index('final queued = await _queuePhoto();')
    assert 'outcome: SubmitOutcome.failed' in segment


def test_mobile_detection_source_link_has_strict_receipt_and_unreviewed_presentation():
    api = read('lib/features/scouting/data/scouting_api.dart')
    widget = read('lib/features/scouting/presentation/scouting_widgets.dart')
    tests = read('test/features/scouting/scouting_api_test.dart')
    assert 'verifyScoutingPhotoDetectionContext' in api
    assert "data['detection']" in api
    assert "linked_model_provenance_unreviewed" in api
    assert "detection['human_diagnosis_approved'] != false" in api
    assert "detection['link_proof'] != 'scout_photo_detection_link_events:v261'" in api
    assert "appendPhotoDetectionLinkEvent" in api
    assert "r['event_id'] != eventId" in api
    assert "r['automatic_pesticide_action_authorized'] != false" in api
    assert 'لم يُعتمد التشخيص بعد' in widget
    assert 'لا يجيز هذا الدليل الرش تلقائياً' in widget
    assert "group('attested model source links, not diagnostic approval'" in tests
