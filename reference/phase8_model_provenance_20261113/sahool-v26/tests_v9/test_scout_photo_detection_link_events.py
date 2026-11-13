"""Explicit human/model-source link contract. All storage/database are test doubles.

This is NOT proof of PostgreSQL trigger/RLS, MinIO, or a clinically correct diagnosis.
"""
from __future__ import annotations

from uuid import uuid4
import hashlib
import pytest

from test_scout_photo_evidence_contract import (
    c, headers, post, path, FIELD, PIN, TENANT_A, TENANT_B, picture,
)

pytestmark = pytest.mark.unit


def link_path():
    return path() + '/detection-link-events'


def event(*, event_id=None, d_id=55, prior=None, action='link', reason=None):
    return {'event_id': str(event_id or uuid4()), 'action': action,
            'detection_provenance_id': d_id if action == 'link' else None,
            'previous_event_id': prior, 'reason': reason}


def _seed(db, *, d_id=55, sha=None, tenant=TENANT_A, field=FIELD, attestation='attested'):
    db['model_provenance'][d_id] = {
        'tenant_id': tenant, 'field_id': field,
        'edge_result_id': 901, 'attestation': attestation,
        'input_sha256': sha or hashlib.sha256(picture()).hexdigest(),
        'model_id': 'local-onnx-crop-disease', 'model_version': 'sha256:artifact-v1',
    }


def test_disabled_by_default_no_link_insert(c, monkeypatch):
    client, db, _, _ = c
    monkeypatch.delenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED', raising=False)
    assert client.post(link_path(), headers=headers(role='expert'), json=event()).status_code == 404
    assert not db['detection_links']
    assert post(client).status_code == 200
    response = client.get(path()+'/context', headers=headers(role='farmer'))
    assert response.status_code == 200, response.text
    assert response.json()['detection'] == {
        'state': 'explicit_link_required', 'result_id': None,
    }


def test_model_link_requires_exact_image_hash_and_is_never_diagnosis(c, monkeypatch):
    client, db, uploaded, _ = c
    assert post(client).status_code == 200
    monkeypatch.setenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED','1')
    _seed(db)
    e1 = event()
    response = client.post(link_path(), headers=headers(role='expert'), json=e1)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['current']['state'] == 'linked_model_provenance_unreviewed'
    assert payload['current']['model_id'] == 'local-onnx-crop-disease'
    assert payload['current']['human_diagnosis_approved'] is False
    assert payload['automatic_pesticide_action_authorized'] is False
    context = client.get(path()+'/context', headers=headers(role='farmer')).json()
    assert context['detection']['state'] == 'linked_model_provenance_unreviewed'
    assert context['decision']['state'] == 'not_authorized'
    replay = client.post(link_path(), headers=headers(role='expert'), json=e1)
    assert replay.status_code == 200 and replay.json()['idempotent'] is True
    history = client.get(link_path(), headers=headers(role='expert'))
    assert history.status_code == 200 and history.json()['history_complete'] is True
    assert len(history.json()['events']) == 1
    assert history.headers['cache-control'] == 'private, no-store'
    rev = event(action='revoke', prior=e1['event_id'], reason='Reviewed and found model linkage incorrect')
    assert client.post(link_path(), headers=headers(role='expert'), json=rev).status_code == 200
    assert client.get(path()+'/context', headers=headers(role='farmer')).json()['detection']['state'] == 'revoked'


@pytest.mark.parametrize('mode',["wrong_hash","other_field","other_tenant","legacy_unattested"])
def test_unverified_model_input_never_links(c, monkeypatch, mode):
    client, db, _, _ = c
    assert post(client).status_code == 200
    monkeypatch.setenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED','1')
    kwargs = {}
    if mode == 'wrong_hash': kwargs['sha'] = '1' * 64
    if mode == 'other_field': kwargs['field'] = 'unrelated'
    if mode == 'other_tenant': kwargs['tenant'] = TENANT_B
    if mode == 'legacy_unattested': kwargs['attestation'] = 'unattested_legacy'
    _seed(db, **kwargs)
    response = client.post(link_path(), headers=headers(role='expert'), json=event())
    assert response.status_code == 422, response.text
    assert response.json()['detail'] == 'scout_photo_detection_image_proof_missing'
    assert not db['detection_links']


def test_event_id_reuse_and_predecessor_conflict(c, monkeypatch):
    client, db, _, _ = c
    assert post(client).status_code == 200
    monkeypatch.setenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED','1')
    _seed(db)
    e1 = event()
    assert client.post(link_path(), headers=headers(role='expert'), json=e1).status_code == 200
    e2 = {**e1, 'detection_provenance_id': 56}
    assert client.post(link_path(), headers=headers(role='expert'), json=e2).status_code == 409
    assert client.post(link_path(), headers=headers(role='expert'), json=event()).status_code == 409
    assert len(db['detection_links']) == 1


def test_photo_detection_scope_cannot_be_replaced_by_read_or_other_role(c, monkeypatch):
    client, db, _, _ = c
    assert post(client).status_code == 200
    monkeypatch.setenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED','1')
    _seed(db)
    db['grants'].pop((TENANT_A,FIELD,'101','photo.detection_link'))
    assert client.post(link_path(), headers=headers(role='expert'), json=event()).status_code == 403
    db['grants'][(TENANT_A,FIELD,'101','photo.detection_link')] = {}
    assert client.post(link_path(), headers=headers(role='worker'), json=event()).status_code == 403
    db['user_roles']['101'] = 'viewer'
    assert client.post(link_path(), headers=headers(role='expert'), json=event()).status_code == 403
    assert not db['detection_links']


def test_chain_self_cycle_and_reason_are_required(c, monkeypatch):
    client, db, _, _ = c
    assert post(client).status_code == 200
    monkeypatch.setenv('SCOUT_MEDIA_DETECTION_LINK_ENABLED','1')
    _seed(db)
    eid = str(uuid4())
    assert client.post(link_path(), headers=headers(role='owner'),
                       json=event(event_id=eid, prior=eid, reason='Fix wrong link now')).status_code == 422
    assert client.post(link_path(), headers=headers(role='owner'),
                       json=event(action='revoke')).status_code == 422
