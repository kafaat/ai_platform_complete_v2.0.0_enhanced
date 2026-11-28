"""Behavioural witnesses for offline timestamp, MSI and MCP decoder gaps.

Subprocesses isolate service package names; no network or service doubles are needed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def run_service(path, source):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / path), str(ROOT)))
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT / path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "cursor,stamp,expected",
    [
        ("2026-10-17T00:00:00", "2026-10-17T00:00:00+00:00", False),
        ("2026-10-17T03:00:00+03:00", "2026-10-17T00:00:00Z", False),
        ("2026-10-17T01:00:00+03:00", "2026-10-16T23:00:00Z", True),
        ("2026-10-17T00:00:00Z", "2026-10-17T01:00:00+03:00", False),
        ("not-a-time", "2026-10-17T00:00:00Z", True),
        ("2026-10-17T00:00:00Z", "!invalid", True),
    ],
)
def test_offline_cursor_compares_instants_and_preserves_unknown(cursor, stamp, expected):
    run_service(
        "services/sahool-platform",
        f"from api.sync_delta import filter_since\n"
        f"ops = [{{'created_at': {stamp!r}}}]\n"
        f"assert bool(filter_since(ops, {cursor!r})) is {expected!r}\n",
    )


def test_offline_newest_ignores_invalid_and_orders_offsets():
    run_service(
        "services/sahool-platform",
        """
from api.sync_delta import newest_cursor
ops = [{'created_at': x} for x in [
    '2026-10-17T02:00:00+03:00', '2026-10-17T00:00:00Z', 'invalid']]
assert newest_cursor(ops) == '2026-10-17T00:00:00Z'
assert newest_cursor([{'created_at': 'invalid'}]) is None
""",
    )


def test_offline_producer_and_retention_accept_legacy_and_offset_stamps():
    run_service(
        "services/sahool-platform",
        """
from datetime import UTC, datetime, timedelta, timezone
from core.offline_first import OfflineQueue, OperationKind, SyncStatus, record_operation_offline
queue = OfflineQueue()
ops = [record_operation_offline(queue, tenant_id='t', user_id='u',
       kind=OperationKind.OBSERVATION_CREATE, payload={}) for _ in range(4)]
assert datetime.fromisoformat(ops[0].created_at).utcoffset() == timedelta(0)
for op in ops:
    queue.mark_status('t', op.op_id, SyncStatus.SYNCED)
old = datetime.now(UTC) - timedelta(hours=48)
ops[0].synced_at = old.replace(tzinfo=None).isoformat()
ops[1].synced_at = old.astimezone(timezone(timedelta(hours=3))).isoformat()
ops[2].synced_at = '!unknown'
assert queue.clear_synced('t') == 2
assert queue.queue_size('t') == 2
""",
    )


def test_msi_default_request_receives_core_cloud_quality_policy():
    run_service(
        "services/raster-service",
        """
from raster_api_models import AutoBackfillPolicy
from scene_policy import select_backfill_scenes_by_policy
assert 'msi' in AutoBackfillPolicy.model_fields['default_indices'].default
scenes = [{'item_id': 'cloudy', 'datetime': '2026-10-16T00:00:00Z',
           'cloud_cover_pct': 70, 'assets': {'nir': 'https://example.com/nir.tif'}}]
assert select_backfill_scenes_by_policy(scenes, indices=['msi'], max_cloud_pct=90, limit=1) == []
""",
    )


def test_mcp_decoder_shares_observe_policy_without_unshadowing_storage():
    run_service(
        "services/mcp_servers",
        """
import importlib.util
import os
import jwt
os.environ['JWT_SECRET'] = 'test-only-mcp-secret-32-characters-long'
os.environ['SAHOOL_ENV'] = 'development'
os.environ['SAHOOL_ACCESS_TOKEN_CLAIM_POLICY'] = 'observe'
from shared.security.access_tokens import reset_would_reject_counts, would_reject_counts
from shared.oauth_middleware import _authenticate_token
from market_server import verify_token
assert importlib.util.find_spec('shared.storage') is None
reset_would_reject_counts()
token = jwt.encode({'aud': 'sahool', 'iss': 'sahool-auth', 'sub': 'u',
                    'tenant_id': 'tenant-a', 'scope': 'market:read'},
                   os.environ['JWT_SECRET'], algorithm='HS256')
assert _authenticate_token(token, 'market:read')['tenant_id'] == 'tenant-a'
assert verify_token(token)['tenant_id'] == 'tenant-a'
counts = would_reject_counts()
assert counts['mcp.oauth']['missing_exp'] == 1
assert counts['mcp.market']['missing_exp'] == 1
""",
    )


def test_mcp_decoder_works_in_the_merged_docker_package_layout(tmp_path):
    # Reproduce the Dockerfile's two COPY layers, without relying on repo PYTHONPATH.
    shutil.copytree(ROOT / "shared", tmp_path / "shared")
    shutil.copytree(ROOT / "services/mcp_servers/shared", tmp_path / "shared", dirs_exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import jwt
os.environ['JWT_SECRET'] = 'test-only-mcp-secret-32-characters-long'
os.environ['SAHOOL_ENV'] = 'development'
os.environ['SAHOOL_ACCESS_TOKEN_CLAIM_POLICY'] = 'observe'
from shared.oauth_middleware import _authenticate_token
from shared.security.access_tokens import would_reject_counts
token = jwt.encode({'aud': 'sahool', 'iss': 'sahool-auth', 'sub': 'u',
                    'tenant_id': 'tenant-a', 'scope': 'market:read'},
                   os.environ['JWT_SECRET'], algorithm='HS256')
assert _authenticate_token(token, 'market:read')['tenant_id'] == 'tenant-a'
assert would_reject_counts()['mcp.oauth']['missing_exp'] == 1
""",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_landsat_scene_without_catalogue_contract_cannot_take_backfill_slot():
    run_service(
        "services/raster-service",
        """
from scene_policy import select_backfill_scenes_by_policy

clear_unusable = {
    'item_id': 'clear-no-contract',
    'datetime': '2026-10-15T10:00:00Z',
    'cloud_cover_pct': 0,
    'data_type': 'thermal_unique',
    'thermal_urls': {'lst': 'https://example.invalid/missing-metadata.tif'},
    'thermal_contract': None,
}
usable = {
    **clear_unusable,
    'item_id': 'usable',
    'cloud_cover_pct': 25,
    'thermal_urls': {'lst': 'https://example.invalid/usable.tif'},
    'thermal_contract': {
        'collection': 'landsat-c2-l2', 'scene': 'usable',
        'acquired': '2026-10-15T10:00:00Z',
        'key': 'lwir11', 'href': 'https://example.invalid/usable.tif',
        'band': {'data_type': 'uint16', 'scale': 0.00341802, 'offset': 149.0},
    },
}
for malformed in (None, {}, 'not-a-contract'):
    bad = {**clear_unusable, 'thermal_contract': malformed}
    chosen = select_backfill_scenes_by_policy(
        [bad, usable], indices=['lst'], max_cloud_pct=50, limit=1
    )
    assert [item['item_id'] for item in chosen] == ['usable']
    assert chosen[0]['thermal_contract'] == usable['thermal_contract']
    assert select_backfill_scenes_by_policy(
        [bad], indices=['lst'], max_cloud_pct=50, limit=1
    ) == []

# Optical discovery has no thermal contract requirement.
optical = {k: v for k, v in clear_unusable.items()
           if k not in ('thermal_contract', 'thermal_urls', 'data_type')}
assert select_backfill_scenes_by_policy(
    [optical], indices=['ndvi'], max_cloud_pct=50, limit=1
)[0]['item_id'] == 'clear-no-contract'
""",
    )
