"""P0 field grants are mandatory; fake DB is only a unit harness, not live PostgreSQL."""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi import HTTPException
from test_scout_photo_evidence_contract import (
    FIELD, PIN, TENANT_A, TENANT_B, c, headers, path, post,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCOPES = ('photo.upload', 'photo.read', 'photo.context', 'photo.season_link')


def _context():
    return path() + '/context'


def _events():
    return path() + '/season-link-events'


def test_role_and_valid_tenant_are_insufficient_without_field_grants(c, monkeypatch):
    client, db, uploaded, _ = c
    db['grants'].clear()
    monkeypatch.setenv('SCOUT_MEDIA_SEASON_LINK_ENABLED', '1')
    assert post(client, hdr=headers(role='owner')).status_code == 403
    assert client.get(path(), headers=headers(role='owner')).status_code == 403
    assert client.get(_context(), headers=headers(role='admin')).status_code == 403
    assert client.get(_events(), headers=headers(role='admin')).status_code == 403
    assert not uploaded and not db['photos']


def test_scope_is_exact_and_one_scope_cannot_impersonate_another(c, monkeypatch):
    client, db, uploaded, _ = c
    db['grants'] = {(TENANT_A, FIELD, '101', 'photo.upload'): {}}
    assert post(client).status_code == 200
    assert client.get(path(), headers=headers()).status_code == 403
    assert client.get(_context(), headers=headers(role='manager')).status_code == 403
    monkeypatch.setenv('SCOUT_MEDIA_SEASON_LINK_ENABLED', '1')
    assert client.get(_events(), headers=headers(role='manager')).status_code == 403


def test_other_field_or_tenant_with_role_does_not_get_media(c):
    client, db, uploaded, _ = c
    db['grants'] = {(TENANT_A, 'other-field', '101', 'photo.upload'): {}}
    assert post(client).status_code == 403
    db['grants'] = {(TENANT_B, FIELD, '101', 'photo.upload'): {}}
    assert post(client).status_code == 403
    assert not uploaded


def test_grant_expired_or_revoked_or_user_inactive_is_denied(c):
    client, db, uploaded, _ = c
    key = (TENANT_A, FIELD, '101', 'photo.upload')
    db['grants'][key] = {'expired': True}
    assert post(client).status_code == 403
    db['grants'][key] = {'revoked': True}
    assert post(client).status_code == 403
    db['grants'][key] = {}
    db['active_users'].discard('101')
    assert post(client).status_code == 403
    assert not uploaded


def test_revoke_between_upload_and_db_insert_blocks_durable_receipt(c, monkeypatch):
    client, db, uploaded, media = c
    original = media.blob_store.upload_bytes
    def revoke_when_uploaded(key, data, ct):
        result = original(key, data, ct)
        db['grants'][(TENANT_A, FIELD, '101', 'photo.upload')] = {'revoked': True}
        return result
    monkeypatch.setattr(media.blob_store, 'upload_bytes', revoke_when_uploaded)
    result = post(client)
    assert result.status_code == 403
    assert not db['photos']  # object might need S3 garbage-collection, but no false receipt
    assert len(uploaded) == 1


def test_grants_database_unavailable_fails_closed(c, monkeypatch):
    client, db, uploaded, media = c
    original = media._tenant_connection
    async def unavailable(tenant):
        raise OSError('private DB internal error')
    monkeypatch.setattr(media, '_tenant_connection', unavailable)
    result = post(client)
    assert result.status_code == 503
    assert result.json()['detail'] == 'scout_media_database_unavailable'
    assert 'private DB internal error' not in result.text
    monkeypatch.setattr(media, '_tenant_connection', original)


def test_grant_schema_is_tenant_fenced_and_read_only_to_media_service():
    schema = (ROOT/'migrations/v258_scout_photo_field_access_grants.sql').read_text()
    for part in (
        'grant_id UUID PRIMARY KEY',
        'scout_photo_grants_one_active_uq',
        'FOREIGN KEY (tenant_id, field_id)',
        'FOREIGN KEY (tenant_id, user_id)',
        'FOREIGN KEY (tenant_id, granted_by)',
        'FOREIGN KEY (tenant_id, revoked_by)',
        'FORCE ROW LEVEL SECURITY',
        'BEFORE UPDATE OR DELETE ON scout_photo_field_access_grants',
        'expires_at > granted_at',
        'revocation_reason IS NOT NULL',
    ):
        assert part in schema
    manifest = (ROOT/'migrations/MANIFEST.txt').read_text()
    assert manifest.index('v257_scout_photo_season_link_events.sql') < manifest.index('v258_scout_photo_field_access_grants.sql') < manifest.index('v206_rls_final_hardening.sql')
    owners = (ROOT/'docs/architecture/db_ownership.yml').read_text()
    assert '  scout_photo_field_access_grants:\n    owner: sahool-platform\n    writers: [sahool-platform]\n    readers: [scout-ingest-service]' in owners
    for filename in ('bootstrap_postgres.sh', 'apply_in_compose.sh'):
        grants = (ROOT/'migrations'/filename).read_text()
        assert 'GRANT SELECT ON scout_photo_field_access_grants TO sahool_ingest' in grants
        assert 'REVOKE INSERT, UPDATE, DELETE ON scout_photo_field_access_grants FROM sahool_ingest' in grants
        assert "REVOKE ALL PRIVILEGES ON TABLE public.scout_photo_field_access_grants FROM %I', :'app_role'" in grants
        assert grants.index('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";') < grants.index("REVOKE ALL PRIVILEGES ON TABLE public.scout_photo_field_access_grants FROM %I', :'app_role'")
    apply = (ROOT/'migrations/apply_in_compose.sh').read_text()
    assert "REVOKE ALL PRIVILEGES ON TABLE public.scout_photo_field_access_grants FROM %I', :'jobs_role'" in apply
    assert apply.index('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"jobs_role";') < apply.index("REVOKE ALL PRIVILEGES ON TABLE public.scout_photo_field_access_grants FROM %I', :'jobs_role'")
    media = (ROOT/'services/scout-ingest-service/media_api.py').read_text()
    for name in SCOPES:
        assert '"'+name+'"' in media
    assert 'u.active IS TRUE' in media
    assert 'g.revoked_at IS NULL' in media
    assert 'g.expires_at > now()' in media
    assert 'scout_media_field_scope_denied' in media


def test_revoked_role_or_old_edge_claim_cannot_reuse_field_grant(c):
    client, db, uploaded, _ = c
    # Issued while farmer, but user's live role changes before token refresh.
    db['user_roles']['101'] = 'viewer'
    assert post(client, hdr=headers(role='farmer')).status_code == 403
    # The current role also lacks upload authority, even with a grant.
    assert post(client, hdr=headers(role='viewer')).status_code == 403
    assert not uploaded


def test_current_role_is_required_for_photo_read(c):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    db['user_roles']['101'] = 'viewer'
    assert client.get(path(), headers=headers(role='farmer')).status_code == 403
    # A fresh downgraded token is allowed READ when read grant still valid.
    assert client.get(path(), headers=headers(role='viewer')).status_code == 200


def test_legacy_perpetual_and_overlong_grants_cannot_authorize(c):
    client, db, uploaded, _ = c
    key = (TENANT_A, FIELD, '101', 'photo.upload')
    db['grants'][key] = {'no_expiry': True}
    assert post(client).status_code == 403
    db['grants'][key] = {'overlong': True}
    assert post(client).status_code == 403
    assert not uploaded


def test_runtime_grants_select_live_role_and_finite_lease():
    source = (ROOT / 'services/scout-ingest-service/media_api.py').read_text()
    assert 'lower(u.role::text)=$5' in source
    assert 'g.expires_at IS NOT NULL' in source
    assert "g.expires_at <= g.granted_at + interval '90 days'" in source
    for file in ('bootstrap_postgres.sh', 'apply_in_compose.sh'):
        script = (ROOT / 'migrations' / file).read_text()
        assert 'GRANT SELECT (id, tenant_id, active, role) ON users TO sahool_ingest' in script
