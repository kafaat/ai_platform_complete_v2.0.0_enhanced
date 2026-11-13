"""SCOUT-PHOTO bounded upload, S3-only receipts, tenant/field/pin fencing.

Uses an in-memory DB/MinIO test double, never claims live PostgreSQL/S3 integration.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / 'services/scout-ingest-service'
for folder in (str(ROOT), str(SERVICE)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

from shared.security.scout_photo import (  # noqa: E402
    MAX_PHOTO_BYTES, PhotoValidationError, inspect_photo, media_key,
)

TENANT_A = '00000000-0000-0000-0000-0000000000aa'
TENANT_B = '00000000-0000-0000-0000-0000000000bb'
FIELD = 'field-alpha'
PIN = '019a3350-1983-719d-91e4-111111111111'


def picture(fmt='JPEG', size=(64, 40)) -> bytes:
    im = Image.new('RGB', size, (60, 180, 55))
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    return buf.getvalue()


class FakeConn:
    def __init__(self, db, tenant):
        self.db, self.tenant = db, tenant

    async def fetchval(self, sql, *args):
        if 'INSERT INTO scout_photo_detection_link_events' in sql:
            ev, tenant, field, pin = args[:4]
            assert tenant == self.tenant
            if 'SELECT $1' in sql:
                d_id, prev, actor, reason = args[4:]
                provenance = self.db['model_provenance'].get(d_id)
                photo = self.db['photos'].get((tenant, field, pin))
                if not provenance or not photo or provenance['tenant_id'] != tenant or provenance['field_id'] != field or \
                        provenance['input_sha256'] != photo['content_sha256'] or provenance['attestation'] != 'attested':
                    return None
                action, edge_id = 'link', provenance['edge_result_id']
            else:
                prev, actor, reason = args[4:]
                action, d_id, edge_id = 'revoke', None, None
            chain = [x for x in self.db['detection_links'].values() if
                     (x['tenant_id'], x['field_id'], x['pin_id']) == (tenant, field, pin)]
            if str(ev) in self.db['detection_links'] or any(
                    str(x['previous_event_id']) == str(prev) for x in chain):
                return None
            if prev is None and any(x['previous_event_id'] is None for x in chain):
                return None
            self.db['detection_links'][str(ev)] = {
                'event_id': ev, 'tenant_id': tenant, 'field_id': field,
                'pin_id': pin, 'action': action,
                'detection_provenance_id': d_id, 'edge_result_id': edge_id,
                'previous_event_id': prev, 'actor_id': actor,
                'reason': reason, 'created_at': '2026-11-13T14:00:00Z',
            }
            return ev
        if 'SELECT true FROM detection_provenance d JOIN edge_results er' in sql:
            tenant, d_id, field, content_sha = args
            d = self.db['model_provenance'].get(d_id)
            return bool(d and d['tenant_id'] == tenant and d['field_id'] == field and
                        d['input_sha256'] == content_sha and d['attestation'] == 'attested')
        if 'FROM scout_photo_field_access_grants' in sql:
            tenant, field, user, scope, claimed_role = args
            assert tenant == self.tenant
            grant = self.db['grants'].get((tenant, field, user, scope))
            return bool(grant is not None and not grant.get('revoked') and not grant.get('expired')
                        and not grant.get('no_expiry') and not grant.get('overlong')
                        and user in self.db['active_users']
                        and claimed_role == self.db['user_roles'].get(user, claimed_role))
        if 'FROM scouting_pins' in sql:
            assert args[0] == self.tenant
            return (self.tenant, args[1], args[2]) in self.db['pins']
        if 'INSERT INTO scout_photo_season_link_events' in sql:
            event_id, tenant, field_id, pin_id = args[:4]
            assert tenant == self.tenant
            if "FROM season_records s" in sql:
                season_id, prior, actor, reason = args[4:]
                info = self.db['seasons'].get((tenant, field_id, season_id))
                if not info or info['trust_status'] != 'accepted' or not info['accepted_by'] or not info['accepted_at']:
                    return None
                action = 'link'
            else:
                season_id = None
                prior, actor, reason = args[4:]
                action = 'revoke'
            chain = [e for e in self.db['links'].values()
                     if e['tenant_id'] == tenant and e['field_id'] == field_id and e['pin_id'] == pin_id]
            if event_id in self.db['links']:
                return None
            if prior is None and any(e['previous_event_id'] is None for e in chain):
                return None
            if prior is not None and any(e['previous_event_id'] == prior for e in chain):
                return None
            self.db['links'][event_id] = {
                'event_id': UUID(event_id), 'tenant_id': tenant,
                'field_id': field_id, 'pin_id': pin_id,
                'action': action, 'season_id': UUID(season_id) if season_id else None,
                'previous_event_id': UUID(prior) if prior else None,
                'actor_id': actor, 'reason': reason, 'created_at': '2026-11-13T13:00:00Z',
            }
            return event_id
        if 'SELECT true FROM season_records' in sql:
            sid, tenant, field_id = args
            info = self.db['seasons'].get((tenant, field_id, sid))
            return bool(info and info['trust_status'] == 'accepted'
                        and info['accepted_by'] and info['accepted_at'])
        if 'INSERT INTO scout_photo_evidence' in sql:
            assert args[0] == self.tenant
            key = tuple(args[:3])
            assert key in self.db['pins']
            if key not in self.db['photos']:
                self.db['photos'][key] = {
                    'evidence_id': uuid4(), 'field_id': args[1], 'pin_id': args[2],
                    'object_ref': args[3], 'content_sha256': args[4],
                    'mime_type': args[5], 'size_bytes': args[6],
                    'image_width': args[7], 'image_height': args[8],
                }
                return self.db['photos'][key]['evidence_id']
            return None
        raise AssertionError(sql)

    async def fetch(self, sql, *args):
        if 'FROM scout_photo_detection_link_events e' in sql:
            tenant, field, pin = args
            chain = [x for x in self.db['detection_links'].values()
                     if (x['tenant_id'],x['field_id'],x['pin_id']) == (tenant,field,pin)]
            heads = [x for x in chain if not any(str(n['previous_event_id']) == str(x['event_id']) for n in chain)]
            result = []
            for x in heads[:2]:
                data = dict(x)
                d = self.db['model_provenance'].get(x['detection_provenance_id'], {})
                data.update({k:d.get(k) for k in ('attestation','model_id','model_version','input_sha256')})
                data['content_sha256'] = self.db['photos'][(tenant,field,pin)]['content_sha256']
                result.append(data)
            return result
        if 'FROM scout_photo_detection_link_events' in sql:
            tenant, field, pin = args
            return list(self.db['detection_links'].values())[:201]
        if 'FROM scout_photo_season_link_events' in sql and 'ORDER BY created_at, event_id' in sql:
            tenant, field_id, pin_id = args
            chain = [e for e in self.db['links'].values()
                     if (e['tenant_id'], e['field_id'], e['pin_id']) == (tenant, field_id, pin_id)]
            return sorted(chain, key=lambda e: str(e['event_id']))[:201]
        if 'FROM scout_photo_season_link_events e' in sql:
            tenant, field_id, pin_id = args
            chain = [e for e in self.db['links'].values()
                     if (e['tenant_id'], e['field_id'], e['pin_id']) == (tenant, field_id, pin_id)]
            heads = [e for e in chain if not any(next_event['previous_event_id'] == e['event_id']
                                                 for next_event in chain)]
            result = []
            for e in heads[:2]:
                data = dict(e)
                info = self.db['seasons'].get((tenant, field_id, str(e['season_id'])))
                data.update(info or {'trust_status': None, 'accepted_by': None, 'accepted_at': None})
                result.append(data)
            return result
        assert 'FROM field_tasks' in sql
        assert 'source_scouting_pin_id=$3' in sql
        assert args[0] == self.tenant
        return self.db['tasks'].get(tuple(args[:3]), [])

    async def fetchrow(self, sql, *args):
        if 'FROM scout_photo_detection_link_events' in sql:
            event_id, tenant, field_id, pin_id = args
            event = self.db['detection_links'].get(str(event_id))
            return event if event is not None and (event['tenant_id'],event['field_id'],event['pin_id']) == (tenant,field_id,pin_id) else None
        if 'FROM scout_photo_season_link_events' in sql:
            event_id, tenant, field_id, pin_id = args
            e = self.db['links'].get(event_id)
            return e if e is not None and (e['tenant_id'], e['field_id'], e['pin_id']) == (tenant, field_id, pin_id) else None
        assert 'FROM scout_photo_evidence' in sql
        assert args[0] == self.tenant
        return self.db['photos'].get(tuple(args[:3]))

    async def close(self):
        pass


@pytest.fixture
def c(monkeypatch):
    import media_api
    importlib.reload(media_api)
    import main
    importlib.reload(main)
    # Stubbed platform-issued, field+scope-scoped grants. No RBAC-only default.
    subjects = ('101', '102', '103')
    scopes = ('photo.read', 'photo.upload', 'photo.context', 'photo.season_link', 'photo.detection_link')
    db = {
        'pins': {(TENANT_A, FIELD, PIN)}, 'photos': {}, 'tasks': {}, 'seasons': {}, 'links': {},
        'model_provenance': {}, 'detection_links': {},
        'active_users': set(subjects),
        'user_roles': {},  # override only when a test simulates a live DB role change
        'grants': {(TENANT_A, FIELD, subject, scope): {} for subject in subjects for scope in scopes},
    }
    uploaded = {}
    monkeypatch.setenv('SCOUT_MEDIA_ENABLED', '1')
    monkeypatch.setenv('SCOUT_MEDIA_SERVICE_TOKEN', 'test-media-only-token')
    monkeypatch.setattr(media_api, '_tenant_connection', lambda tenant: _make_conn(db, tenant))
    monkeypatch.setattr(media_api.blob_store, 's3_enabled', lambda: True)
    monkeypatch.setattr(media_api.blob_store, 'S3_BUCKET', 'test-evidence')

    def put(key, data, content_type):
        uploaded[key] = (data, content_type)
        return 's3://test-evidence/' + key

    monkeypatch.setattr(media_api.blob_store, 'upload_bytes', put)
    monkeypatch.setattr(media_api.blob_store, 'object_exists',
                        lambda ref: ref.partition('s3://test-evidence/')[2] in uploaded)
    monkeypatch.setattr(media_api.blob_store, 'presigned_get_url',
                        lambda ref, ttl_s: 'https://scout-assets.example.org/photo?sig=TEST')
    return TestClient(main.app), db, uploaded, media_api


async def _make_conn(db, tenant):
    return FakeConn(db, tenant)


def headers(tenant=TENANT_A, role='farmer', uid='101', token='test-media-only-token'):
    return {
        'X-Scout-Media-Token': token, 'X-Tenant-Id': tenant,
        'X-User-Id': uid, 'X-User-Role': role,
    }


def path(pin=PIN):
    return f'/internal/scouting-media/fields/{FIELD}/pins/{pin}/photo'


def post(client, data=None, *, hdr=None, content_type='image/jpeg', digest=None):
    data = data if data is not None else picture()
    h = {**(hdr if hdr is not None else headers()), 'X-Content-SHA256': digest or hashlib.sha256(data).hexdigest(),
         'Content-Type': content_type}
    return client.post(path(), content=data, headers=h)


def test_valid_image_persists_once_and_has_separate_unreviewed_status(c):
    client, db, uploaded, _ = c
    response = post(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['persisted'] is True
    assert data['field_id'] == FIELD and data['pin_id'] == PIN
    assert data['verification_state'] == 'bytes_verified'
    assert data['review_state'] == 'unreviewed'
    assert 'object_ref' not in data and 'url' not in data
    assert len(uploaded) == 1
    key = next(iter(uploaded))
    assert key.startswith('scouting-photos/v1/' + TENANT_A + '/' + PIN)
    replay = post(client)
    assert replay.status_code == 200 and replay.json()['idempotent'] is True
    assert len(uploaded) == 1
    get = client.get(path(), headers=headers())
    assert get.status_code == 200
    assert get.json()['url'].startswith('https://')
    assert get.json()['expires_in_seconds'] == 120
    assert get.json()['sha256'] == data['sha256']
    assert get.headers['cache-control'] == 'private, no-store'
    assert get.headers['pragma'] == 'no-cache'


def test_cross_tenant_and_wrong_field_fail_without_object_writes(c):
    client, db, uploaded, _ = c
    assert post(client, hdr=headers(tenant=TENANT_B)).status_code == 403
    assert client.get(path(), headers=headers(tenant=TENANT_B)).status_code == 403
    assert client.get('/internal/scouting-media/fields/another/pins/'+PIN+'/photo',
                      headers=headers()).status_code == 403
    assert not uploaded


def test_wrong_hash_and_corruption_refused_before_upload(c):
    client, db, uploaded, _ = c
    assert post(client, digest='0'*64).status_code == 422
    assert post(client, data=b'\xff\xd8\xfffake').status_code == 415
    assert post(client, content_type='image/webp').status_code == 415
    assert not uploaded


def test_conflicting_bytes_do_not_replace_first_image(c):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    changed = post(client, picture(size=(30, 35)))
    assert changed.status_code == 409
    assert len(uploaded) == 1
    assert len(db['photos']) == 1


def test_auth_role_feature_gates_and_no_local_fallback(c, monkeypatch):
    client, db, uploaded, mod = c
    assert post(client, hdr={}).status_code == 401  # no secret from client
    assert post(client, hdr=headers(token='wrong')).status_code == 401
    assert post(client, hdr=headers(role='viewer')).status_code == 403
    assert post(client, hdr=headers(uid='')).status_code == 403
    monkeypatch.setattr(mod.blob_store, 's3_enabled', lambda: False)
    assert post(client).status_code == 503
    monkeypatch.setenv('SCOUT_MEDIA_ENABLED', '0')
    assert post(client).status_code == 404
    assert not uploaded


def test_storage_outage_not_a_saved_receipt(c, monkeypatch):
    client, db, uploaded, mod = c
    def unavailable(*a):
        raise RuntimeError('object store outage')
    monkeypatch.setattr(mod.blob_store, 'upload_bytes', unavailable)
    res = post(client)
    assert res.status_code == 503
    assert not db['photos']


def test_size_and_key_validation(c):
    client, db, uploaded, mod = c
    too_big = b'x' * (MAX_PHOTO_BYTES + 1)
    assert post(client, too_big).status_code == 413
    assert client.post(path('../other'), content=picture(), headers=headers()).status_code in (404, 422)
    with pytest.raises(PhotoValidationError):
        media_key(TENANT_A, '../other', '0'*64)
    with pytest.raises(PhotoValidationError):
        media_key(TENANT_A, PIN, 'G'*64)


def test_pure_picture_verifier_and_png():
    for fmt, mime in (('PNG', 'image/png'), ('WEBP', 'image/webp'), ('JPEG', 'image/jpeg')):
        p = picture(fmt)
        result = inspect_photo(p, mime, hashlib.sha256(p).hexdigest())
        assert result.width == 64 and result.height == 40
    with pytest.raises(PhotoValidationError, match='photo_sha256_mismatch'):
        inspect_photo(picture(), 'image/jpeg', '0'*64)


def test_replay_rechecks_blob_existence_before_claiming_persisted(c, monkeypatch):
    client, db, uploaded, media = c
    assert post(client).status_code == 200
    # DB receipt remains but object was lost independently from SQL.
    uploaded.clear()
    replay = post(client)
    assert replay.status_code == 503
    assert replay.json()['detail'] == 'scout_photo_object_not_verified'


def test_new_upload_requires_s3_head_after_sql_commit(c, monkeypatch):
    client, db, uploaded, media = c
    # put_object succeeded and SQL row exists, but HEAD fails or races with
    # object disappearance: 200 must never be returned for phantom evidence.
    monkeypatch.setattr(media.blob_store, 'object_exists', lambda ref: False)
    response = post(client)
    assert response.status_code == 503
    assert response.json()['detail'] == 'scout_photo_object_not_verified'
    assert len(db['photos']) == 1
    assert client.get(path(), headers=headers()).status_code == 503


def test_poisoned_s3_ref_never_presigned_or_accepted(c):
    client, db, uploaded, media = c
    assert post(client).status_code == 200
    row = next(iter(db['photos'].values()))
    original = row['object_ref']
    # Even if an object with the same hash exists, a forged bucket or prefix
    # must not become a bearer-capability URL for a different tenant.
    for bad in ('s3://other/' + original.split('/', 3)[-1],
                original.replace('/' + TENANT_A + '/', '/' + TENANT_B + '/')):
        row['object_ref'] = bad
        assert post(client).status_code == 503
        response = client.get(path(), headers=headers())
        assert response.status_code == 503
        assert response.json()['detail'] == 'scout_photo_reference_invalid'
    row['object_ref'] = original
    assert client.get(path(), headers=headers()).status_code == 200


def test_racing_same_digest_is_marked_idempotent(c, monkeypatch):
    client, db, uploaded, media = c
    assert post(client).status_code == 200
    # Simulate the row appearing between the initial existence check and
    # the INSERT ... ON CONFLICT DO NOTHING. The re-read sees the winner.
    real_read = media._read_row
    calls = 0
    async def racing_read(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await real_read(*args)
    monkeypatch.setattr(media, '_read_row', racing_read)
    replay = post(client)
    assert replay.status_code == 200
    assert replay.json()['idempotent'] is True
    assert len(db['photos']) == 1


def test_schema_prevents_mutating_existing_evidence():
    sql = (ROOT / 'migrations/v256_scout_photo_evidence.sql').read_text()
    assert 'CREATE TRIGGER scout_photo_evidence_immutable_guard' in sql
    assert 'BEFORE UPDATE OR DELETE ON scout_photo_evidence' in sql
    assert "RAISE EXCEPTION 'scout_photo_evidence_immutable'" in sql


def context_path(pin=PIN):
    return path(pin) + '/context'


def test_context_is_read_only_and_never_invents_season_lab_or_decision(c):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    result = client.get(context_path(), headers=headers())
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['schema'] == 'sahool.scout-photo-evidence-context/v1'
    assert body['source'] == {'kind': 'scouting_pin', 'field_id': FIELD, 'pin_id': PIN}
    assert body['evidence']['persisted'] is True
    assert body['evidence']['review_state'] == 'unreviewed'
    assert body['object_state'] == 'present_at_check'
    assert body['inspection'] == {'state': 'not_linked'}
    assert body['season'] == {'state': 'explicit_link_required', 'season_id': None}
    assert body['lab_sample'] == {'state': 'explicit_link_required', 'sample_id': None}
    assert body['detection'] == {'state': 'explicit_link_required', 'result_id': None}
    assert body['decision'] == {'state': 'not_authorized', 'decision_id': None}
    assert body['automatic_pesticide_action_authorized'] is False
    assert 'object_ref' not in result.text and 's3://' not in result.text
    assert 'url' not in body and 'uploaded_by' not in result.text
    assert result.headers['cache-control'] == 'private, no-store'


def test_context_links_only_task_with_exact_v246_fk(c):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    db['tasks'][(TENANT_A, FIELD, PIN)] = [{'task_id': uuid4(), 'status': 'pending'}]
    result = client.get(context_path(), headers=headers(role='farmer'))
    assert result.status_code == 200, result.text
    link = result.json()['inspection']
    assert link['state'] == 'linked'
    assert link['task_id'] == str(db['tasks'][(TENANT_A, FIELD, PIN)][0]['task_id'])
    assert link['status'] == 'pending'
    assert link['link_proof'] == 'field_tasks.source_scouting_pin_id:v246'
    assert result.json()['season']['season_id'] is None


def test_context_fails_closed_for_cross_tenant_missing_object_and_ambiguous_task(c):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    assert client.get(context_path(), headers=headers(role='viewer')).status_code == 403
    assert client.get(context_path(), headers=headers(role='worker')).status_code == 403
    assert client.get(context_path(), headers=headers(tenant=TENANT_B)).status_code == 403
    assert client.get('/internal/scouting-media/fields/not-mine/pins/'+PIN+'/photo/context',
                      headers=headers()).status_code == 403
    db['tasks'][(TENANT_A, FIELD, PIN)] = [
        {'task_id': uuid4(), 'status': 'pending'},
        {'task_id': uuid4(), 'status': 'pending'},
    ]
    bad = client.get(context_path(), headers=headers())
    assert bad.status_code == 503
    assert bad.json()['detail'] == 'scout_photo_inspection_link_ambiguous'
    db['tasks'].clear()
    uploaded.clear()
    missing = client.get(context_path(), headers=headers())
    assert missing.status_code == 503
    assert missing.json()['detail'] == 'scout_photo_object_not_verified'


def test_storage_adapter_mismatched_bucket_never_commits_immutable_receipt(c, monkeypatch):
    client, db, uploaded, media = c
    monkeypatch.setattr(media.blob_store, 'upload_bytes',
                        lambda *args: 's3://unexpected-bucket/cross-tenant/other')
    response = post(client)
    assert response.status_code == 503
    assert response.json()['detail'] == 'scout_media_store_unavailable'
    assert not db['photos']


def test_context_service_select_is_narrow_and_platform_ownership_is_preserved():
    migration = (ROOT / 'migrations/v246_scouting_pin_inspection_task.sql').read_text()
    assert 'FOREIGN KEY (tenant_id, field_id, source_scouting_pin_id)' in migration
    code = (SERVICE / 'media_api.py').read_text()
    assert 'SELECT task_id, status FROM field_tasks' in code
    assert 'WHERE tenant_id=$1::uuid AND field_id=$2 AND source_scouting_pin_id=$3' in code
    for script in ('apply_in_compose.sh', 'bootstrap_postgres.sh'):
        sh = (ROOT / 'migrations' / script).read_text()
        assert 'GRANT SELECT (tenant_id, field_id, source_scouting_pin_id, task_id, status)' in sh
        assert 'ON field_tasks TO sahool_ingest' in sh
    owners = (ROOT / 'docs/architecture/db_ownership.yml').read_text()
    block = owners.split('  field_tasks:', 1)[1].split('\n  field_weather_overlay:', 1)[0]
    assert 'owner: field-management-service' in block
    assert 'readers: [sahool-platform, scout-ingest-service]' in block
    assert 'writers: [field-management-service]' in block


def test_inspection_db_failure_never_becomes_unlinked_receipt(c, monkeypatch):
    client, db, uploaded, media = c
    assert post(client).status_code == 200
    async def access_denied(*args):
        raise PermissionError('field_tasks column grant absent')
    monkeypatch.setattr(media, '_linked_inspection', access_denied)
    response = client.get(context_path(), headers=headers())
    assert response.status_code == 503
    assert response.json()['detail'] == 'scout_media_database_unavailable'
    assert 'field_tasks column grant absent' not in response.text
