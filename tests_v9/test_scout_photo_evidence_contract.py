"""SCOUT-PHOTO (v260): the photo's single source of truth is ``scout_photo_evidence``.

Unit contract, no database and no object store:

* the pure proof-of-bytes rules in ``shared.security.scout_photo`` (decode, digest, key,
  object-ref ownership, the client receipt);
* the HTTP gates of ``services/scout-ingest-service/media_api.py`` that must answer **before**
  any database or store contact. ``DATABASE_URL`` is empty, so a request that reached the
  database would answer 503 ``scout_media_database_unavailable`` instead of the code tested;
* the schema, registration and wiring text (v260, MANIFEST, grants, db_ownership, nginx,
  compose, .env.example).

What needs a real PostgreSQL (RLS, FK, the immutable trigger, idempotent and concurrent
resubmits, the HEAD check after commit) is proven in
``services/scout-ingest-service/tests/test_media_live.py`` (``-m integration``).
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
PIL = pytest.importorskip("PIL")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "scout-ingest-service"
for folder in (str(ROOT), str(SERVICE)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

from shared.security import scout_photo as sp  # noqa: E402

TENANT_A = "00000000-0000-0000-0000-0000000000aa"
TENANT_B = "00000000-0000-0000-0000-0000000000bb"
FIELD = "field-alpha"
PIN = "019a3350-1983-719d-91e4-111111111111"
TOKEN = "test-media-only-token"  # noqa: S105 — test value
BUCKET = "sahool-scout-ingest"


def picture(fmt: str = "JPEG", size: tuple[int, int] = (64, 40)) -> bytes:
    im = Image.new("RGB", size, (60, 180, 55))
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    return buf.getvalue()


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ─── pure: proof of bytes ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fmt,mime", [("PNG", "image/png"), ("WEBP", "image/webp"), ("JPEG", "image/jpeg")]
)
def test_valid_pictures_are_fully_decoded(fmt, mime):
    data = picture(fmt)
    info = sp.inspect_photo(data, mime, hashlib.sha256(data).hexdigest())
    assert (info.width, info.height, info.content_type) == (64, 40, mime)
    assert info.size_bytes == len(data)


@pytest.mark.parametrize(
    "data,mime,digest,code",
    [
        (b"", "image/jpeg", None, "photo_size_invalid"),
        (b"x", "image/gif", None, "unsupported_photo_type"),
        (None, "image/jpeg", "", "photo_sha256_required"),
        (None, "image/jpeg", "0" * 64, "photo_sha256_mismatch"),
        (b"\xff\xd8\xfffake", "image/jpeg", None, "photo_decode_failed"),
        (None, "image/webp", None, "photo_type_mismatch"),  # JPEG bytes claimed as WebP
    ],
)
def test_refusals_carry_a_stable_code(data, mime, digest, code):
    data = picture() if data is None else data
    digest = hashlib.sha256(data).hexdigest() if digest is None else digest
    with pytest.raises(sp.PhotoValidationError) as exc:
        sp.inspect_photo(data, mime, digest)
    assert exc.value.code == code


def test_truncated_pixel_data_is_refused():
    data = picture(size=(400, 300))[:-200]
    with pytest.raises(sp.PhotoValidationError) as exc:
        sp.inspect_photo(data, "image/jpeg", hashlib.sha256(data).hexdigest())
    assert exc.value.code == "photo_decode_failed"


def test_pixel_limit(monkeypatch):
    monkeypatch.setattr(sp, "MAX_PHOTO_PIXELS", 64 * 40 - 1)
    data = picture()
    with pytest.raises(sp.PhotoValidationError) as exc:
        sp.inspect_photo(data, "image/jpeg", hashlib.sha256(data).hexdigest())
    assert exc.value.code == "photo_pixel_limit"


def test_status_codes_for_refusals():
    assert sp.http_status_for("unsupported_photo_type") == 415
    assert sp.http_status_for("photo_type_mismatch") == 415
    assert sp.http_status_for("photo_decode_failed") == 415
    assert sp.http_status_for("photo_sha256_mismatch") == 422
    assert sp.http_status_for("photo_sha256_required") == 422
    assert sp.http_status_for("photo_size_invalid") == 422


def test_media_key_is_server_derived_and_path_safe():
    digest = "a" * 64
    assert sp.media_key(TENANT_A, PIN, digest) == f"scouting-photos/v1/{TENANT_A}/{PIN}/{digest}"
    for bad_pin in ("../other", "a/b", "", "x" * 101, "pin:01", "صورة"):
        with pytest.raises(sp.PhotoValidationError):
            sp.media_key(TENANT_A, bad_pin, digest)
    with pytest.raises(sp.PhotoValidationError):
        sp.media_key(TENANT_A, PIN, "G" * 64)
    with pytest.raises(sp.PhotoValidationError):
        sp.media_key("not-a-uuid", PIN, digest)


def _row(**over):
    digest = hashlib.sha256(b"x").hexdigest()
    row = {
        "evidence_id": "e1",
        "field_id": FIELD,
        "pin_id": PIN,
        "content_sha256": digest,
        "mime_type": "image/jpeg",
        "size_bytes": 1,
        "image_width": 1,
        "image_height": 1,
        "object_ref": f"s3://{BUCKET}/{sp.media_key(TENANT_A, PIN, digest)}",
    }
    row.update(over)
    return row


def test_only_the_server_derived_ref_is_ever_headed_or_presigned():
    row = _row()
    assert sp.owned_object_ref(row, BUCKET, TENANT_A, PIN) == row["object_ref"]
    key = row["object_ref"].split("/", 3)[-1]
    for bad in (
        f"s3://other-bucket/{key}",  # another bucket
        row["object_ref"].replace(f"/{TENANT_A}/", f"/{TENANT_B}/"),  # another tenant
        row["object_ref"].replace(PIN, "other-pin"),  # another pin
        row["object_ref"][:-1] + "0",  # another digest
        "file:///etc/passwd",
    ):
        with pytest.raises(sp.PhotoValidationError, match="scout_photo_reference_invalid"):
            sp.owned_object_ref(_row(object_ref=bad), BUCKET, TENANT_A, PIN)
    with pytest.raises(sp.PhotoValidationError):
        sp.owned_object_ref(row, "", TENANT_A, PIN)  # no configured bucket
    with pytest.raises(sp.PhotoValidationError):
        sp.owned_object_ref(row, BUCKET, TENANT_B, PIN)  # read under another tenant


def test_client_receipt_never_shows_the_object_ref_or_uploader():
    out = sp.public_receipt(_row(uploaded_by="person-a"))
    assert "object_ref" not in out and "uploaded_by" not in out
    assert out["persisted"] is True
    assert (out["verification_state"], out["review_state"]) == ("bytes_verified", "unreviewed")


# ─── HTTP gates: answered before any database or store contact ──────────────


@pytest.fixture
def media(monkeypatch):
    import media_api
    import season_api

    monkeypatch.setattr(season_api, "DATABASE_URL", "")  # any DB contact ⇒ 503
    monkeypatch.setenv("SCOUT_MEDIA_ENABLED", "1")
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(media_api.blob_store, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(media_api.blob_store, "S3_ENDPOINT", "https://objects.example.org")
    uploads: list = []

    def no_upload(*args, **kwargs):  # noqa: ANN002, ANN003
        uploads.append(args)
        raise AssertionError("no object may be written by a refused request")

    monkeypatch.setattr(media_api.blob_store, "upload_bytes", no_upload)
    app = FastAPI()
    app.include_router(media_api.router)
    return TestClient(app), uploads, media_api


def headers(tenant=TENANT_A, role="farmer", uid="person-a", token=TOKEN):
    return {
        "X-Scout-Media-Token": token,
        "X-Tenant-Id": tenant,
        "X-User-Id": uid,
        "X-User-Role": role,
    }


def path(pin=PIN, field=FIELD):
    return f"/internal/scouting-media/fields/{field}/pins/{pin}/photo"


def post(client, data=None, *, hdr=None, content_type="image/jpeg", digest=None, pin=PIN):
    data = picture() if data is None else data
    h = {
        **(headers() if hdr is None else hdr),
        "X-Content-SHA256": hashlib.sha256(data).hexdigest() if digest is None else digest,
        "Content-Type": content_type,
    }
    return client.post(path(pin), content=data, headers=h)


def test_feature_flag_token_identity_and_store_gates(media, monkeypatch):
    client, uploads, mod = media
    assert post(client, hdr={}).status_code == 401  # the client never holds the secret
    assert post(client, hdr=headers(token="wrong")).status_code == 401
    assert post(client, hdr=headers(uid="")).status_code == 403
    assert post(client, hdr=headers(tenant="not-a-uuid")).status_code == 403
    monkeypatch.setattr(mod.blob_store, "S3_BUCKET", "")  # no shared store ⇒ no file:// fallback
    assert post(client).status_code == 503
    assert post(client).json()["detail"] == "shared_photo_storage_not_configured"
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", "")
    assert post(client).status_code == 503
    monkeypatch.setenv("SCOUT_MEDIA_ENABLED", "0")
    assert post(client).status_code == 404
    assert client.get(path(), headers=headers()).status_code == 404
    assert not uploads


@pytest.mark.parametrize(
    "role", ["owner", "admin", "manager", "agronomist", "expert", "worker", "farmer"]
)
def test_every_role_that_may_record_a_pin_may_upload_its_photo(media, role):
    client, uploads, _ = media
    # Passes every gate, then reaches the database (absent here) ⇒ 503, not 403.
    res = post(client, hdr=headers(role=role))
    assert res.status_code == 503, res.text
    assert res.json()["detail"] == "scout_media_database_unavailable"
    assert not uploads


@pytest.mark.parametrize("role", ["viewer", "platform_admin", "", "root"])
def test_roles_without_observation_record_cannot_upload(media, role):
    client, uploads, _ = media
    assert post(client, hdr=headers(role=role)).status_code == 403
    assert not uploads


def test_viewer_may_read_platform_admin_may_not(media):
    client, _, _ = media
    assert client.get(path(), headers=headers(role="viewer")).status_code == 503  # reached DB
    assert client.get(path(), headers=headers(role="platform_admin")).status_code == 403


def test_bad_bytes_are_refused_before_the_database(media):
    client, uploads, _ = media
    assert post(client, digest="0" * 64).status_code == 422
    assert post(client, data=b"\xff\xd8\xfffake").status_code == 415
    assert post(client, content_type="image/webp").status_code == 415
    assert post(client, content_type="application/octet-stream").status_code == 415
    assert post(client, data=b"x" * (sp.MAX_PHOTO_BYTES + 1)).status_code == 413
    assert post(client, pin="bad:pin").status_code == 422
    assert client.get(path(pin="bad:pin"), headers=headers()).status_code == 422
    assert not uploads


def test_role_sets_match_the_platform_role_aliases():
    """Upload ⇔ OBSERVATION_RECORD, read ⇔ OBSERVATION_VIEW (api/main.py:_ROLE_ALIASES)."""
    import media_api

    main_src = read("services/sahool-platform/api/main.py")
    block = main_src[main_src.index("_ROLE_ALIASES: dict[str, UserRole] = {") :]
    block = block[: block.index("}")]
    aliases = dict(re.findall(r'"(\w+)": UserRole\.(\w+)', block))
    recorders = {"OWNER", "MANAGER", "AGRONOMIST", "WORKER"}
    assert {k for k, v in aliases.items() if v in recorders} == set(media_api.WRITE_ROLES)
    assert {k for k, v in aliases.items() if v in recorders | {"VIEWER"}} == set(
        media_api.READ_ROLES
    )


# ─── schema, registration, wiring ───────────────────────────────────────────


def test_v260_schema_is_immutable_rls_bound_and_pin_bound():
    sql = read("migrations/v260_scout_photo_evidence.sql")
    assert "CREATE TRIGGER scout_photo_evidence_immutable_guard" in sql
    assert "BEFORE UPDATE OR DELETE ON scout_photo_evidence" in sql
    assert "RAISE EXCEPTION 'scout_photo_evidence_immutable'" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert re.search(
        r"FOREIGN KEY \(tenant_id, field_id, pin_id\)\s+REFERENCES scouting_pins \(tenant_id, field_id, pin_id\)",
        sql,
    )
    assert "UNIQUE (tenant_id, field_id, pin_id)" in sql
    # The FK needs a unique key on scouting_pins (tenant_id, field_id, pin_id): v246's index.
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS scouting_pins_tenant_field_pin_uq\s+"
        r"ON scouting_pins \(tenant_id, field_id, pin_id\);",
        read("migrations/v246_scouting_pin_inspection_task.sql"),
    )


def test_v260_is_registered_after_its_dependencies_and_before_v240_v206():
    entries = [
        line.strip()
        for line in read("migrations/MANIFEST.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pos = {name: i for i, name in enumerate(entries)}
    assert "v256_scout_photo_evidence.sql" not in pos
    for dep in (
        "v94_scouting_pins.sql",
        "v246_scouting_pin_inspection_task.sql",
        "v257_scouting_pin_location_photo.sql",
    ):
        assert pos[dep] < pos["v260_scout_photo_evidence.sql"]
    assert pos["v260_scout_photo_evidence.sql"] < pos["v240_converge_first_pass_schema.sql"]
    assert entries[-1] == "v206_rls_final_hardening.sql"
    runner = read("scripts_v9/run_migrations.sql")
    assert (
        runner.index("v257_scouting_pin_location_photo.sql")
        < runner.index("v260_scout_photo_evidence.sql")
        < runner.index("v240_converge_first_pass_schema.sql")
    )
    assert "v260_scout_photo_evidence.sql" in read("migrations/MANIFEST.md")


def test_db_ownership_names_scout_ingest_as_the_single_writer():
    own = read("docs/architecture/db_ownership.yml")
    block = own[own.index("  scout_photo_evidence:") :]
    block = block[: block.index("\n  scouting_pins:")]
    assert "owner: scout-ingest-service" in block
    assert "writers: [scout-ingest-service]" in block
    assert "migrations/v260_scout_photo_evidence.sql" in block
    pins = own[own.index("  scouting_pins:") :].split("\n  seasons:")[0]
    assert "writers: [sahool-platform]" in pins
    assert "readers: [scout-ingest-service]" in pins


@pytest.mark.parametrize(
    "script", ["migrations/bootstrap_postgres.sh", "migrations/apply_in_compose.sh"]
)
def test_ingest_role_gets_select_insert_only(script):
    src = read(script)
    assert "GRANT SELECT, INSERT ON scout_photo_evidence TO sahool_ingest;" in src
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON scout_photo_evidence FROM sahool_ingest;" in src
    assert "GRANT SELECT ON scouting_pins TO sahool_ingest;" in src
    assert not re.search(r"GRANT[^;]*\b(UPDATE|DELETE)\b[^;]*scout_photo_evidence", src)
    assert not re.search(r"GRANT[^;]*\b(INSERT|UPDATE|DELETE)\b[^;]*\bscouting_pins\b", src)


def test_gateway_compose_and_env_wiring():
    nginx = read("nginx/nginx.v9.conf")
    loc = nginx[nginx.index("location ^~ /api/v1/scouting-media/ {") :]
    loc = loc[: loc.index("\n        }")]
    assert "auth_request /_auth_verify;" in loc
    assert "proxy_pass http://scout_ingest_backend/internal/scouting-media/;" in loc
    assert "include /etc/nginx/proxy_params.conf;" in loc
    assert 'proxy_set_header X-Scout-Media-Token "${SCOUT_MEDIA_SERVICE_TOKEN}";' in loc
    assert "proxy_set_header X-Tenant-Id $scout_media_tenant;" in loc
    compose = read("docker-compose.v9.yml")
    assert (
        "SCOUT_MEDIA_SERVICE_TOKEN"
        in compose.split("NGINX_ENVSUBST_FILTER:", 1)[1].split("\n", 1)[0]
    )
    ingest = compose[compose.index("\n  sahool-scout-ingest:\n") :]
    ingest = ingest[: ingest.index("\n  sahool-scout-ingest-projection:")]
    assert "SCOUT_MEDIA_ENABLED: ${SCOUT_MEDIA_ENABLED:-0}" in ingest
    assert "S3_PUBLIC_ENDPOINT: ${SCOUT_INGEST_S3_PUBLIC_ENDPOINT:-}" in ingest
    # The scout signing host belongs to scout-ingest only, not to the raster services.
    assert compose.count("${SCOUT_INGEST_S3_PUBLIC_ENDPOINT:-}") == 1
    env = read(".env.example")
    assert re.search(r"^SCOUT_MEDIA_ENABLED=0$", env, re.M)
    assert re.search(r"^SCOUT_MEDIA_SERVICE_TOKEN=$", env, re.M)
    assert "Pillow" in read("services/scout-ingest-service/requirements.txt")
    assert "media_router" in read("services/scout-ingest-service/main.py")
