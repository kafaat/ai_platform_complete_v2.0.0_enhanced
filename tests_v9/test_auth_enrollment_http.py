"""Real ASGI auth app and JWT/bcrypt/TOTP; only DB/Redis I/O are doubled.
No lifespan startup or live DB/Redis/network; exact selected SQL fields are modeled.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
import time
from contextlib import asynccontextmanager

import httpx
import jwt
import pytest

from tests_v9.service_module import load_service_main

pyotp = pytest.importorskip("pyotp")
Fernet = pytest.importorskip("cryptography.fernet").Fernet

main = load_service_main("services/auth", required_attrs=("_ensure_admin_user", "MfaCodeRequest"))
mfa_crypto = importlib.import_module("mfa_crypto")

pytestmark = [pytest.mark.unit, pytest.mark.security]

PASSWORD = "Synthet1c-Password!"
TENANT = "00000000-0000-0000-0000-000000000007"
SECRET = "JBSWY3DPEHPK3PXP"


def user(role="farmer", mfa=False):
    return dict(
        id=7,
        email="synthetic@example.com",
        password_hash=main.hash_password(PASSWORD, 4),
        role=role,
        full_name="Synthetic User",
        tenant_id=TENANT,
        active=True,
        mfa_enabled=mfa,
        mfa_secret=None,
        encrypted_mfa_secret=mfa_crypto.encrypt_secret(SECRET) if mfa else None,
        mfa_failed_attempts=0,
        mfa_locked_until=None,
        mfa_last_totp_step=None,
        mfa_enabled_at="enabled-before" if mfa else None,
        updated_at="initial",
    )


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.sets = {}

    async def get(self, k):
        return self.kv.get(k)

    async def getdel(self, k):
        return self.kv.pop(k, None)

    async def setex(self, k, ttl, v):
        self.kv[k] = str(v)

    async def exists(self, k):
        return int(k in self.kv)

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, *a):
        return True

    async def ttl(self, *a):
        return 60

    async def delete(self, *keys):
        n = 0
        for k in keys:
            n += int(k in self.kv or k in self.sets)
            self.kv.pop(k, None)
            self.sets.pop(k, None)
        return n

    async def sadd(self, k, v):
        self.sets.setdefault(k, set()).add(v)

    async def smembers(self, k):
        return self.sets.get(k, set())


_GUARDED_COLUMNS = ("password_hash", "role", "tenant_id")


class FakeConnection:
    """Models the users row, the WHERE predicates the routes write, and the BEFORE UPDATE
    trigger ``trg_users_updated_at`` (migrations/v9_foundation.sql:53): **every** matched
    users UPDATE gets a fresh ``updated_at`` — the TOTP-step and failure-counter writes too.
    Without the trigger the double hid a real-Postgres 409 on every enrollment activation.
    """

    def __init__(self, row):
        self.row = row
        self.others = []  # further users rows (bootstrap-scope tenant probe only)
        self.sql = []
        self.before_enrollment_write = None
        self.updates = 0
        self.audit = []  # mfa_audit_events.event values, in order

    def _trigger(self):
        self.updates += 1
        self.row["updated_at"] = f"trigger-{self.updates}"

    def _where_holds(self, sql, args):
        where = sql.split(" WHERE ", 1)[1].split(" RETURNING ", 1)[0]
        uid = re.search(r"\bid\s*=\s*\$(\d+)", where)
        if uid and args[int(uid.group(1)) - 1] != self.row["id"]:
            return False
        if "active=TRUE" in where and not self.row["active"]:
            return False
        if "mfa_enabled=FALSE" in where and self.row["mfa_enabled"]:
            return False
        flag = re.search(r"NOT \$(\d+)::boolean OR \(", where)
        guarded = flag is None or bool(args[int(flag.group(1)) - 1])
        for column, n in re.findall(r"(\w+) IS NOT DISTINCT FROM \$(\d+)", where):
            if column in _GUARDED_COLUMNS and not guarded:
                continue
            if self.row[column] != args[int(n) - 1]:
                return False
        return True

    def _bootstrap_probe(self, args):
        uid, roles = args
        if self.row is None or uid != self.row["id"]:
            return None
        enrolled_admin = any(
            o["id"] != uid
            and o["active"]
            and o["mfa_enabled"]
            and o["tenant_id"] == self.row["tenant_id"]
            and (o["role"] or "").strip().lower() in roles
            for o in self.others
        )
        return {
            "never_enrolled": self.row.get("mfa_enabled_at") is None,
            "tenant_has_enrolled_admin": enrolled_admin,
        }

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        if "AS tenant_has_enrolled_admin" in sql:
            return self._bootstrap_probe(args)
        if "UPDATE users SET encrypted_mfa_secret=$1" in sql:
            tag = await self.execute(sql, *args)
            return dict(self.row) if tag == "UPDATE 1" else None
        if "FROM users" not in sql:
            raise AssertionError("unexpected SQL: " + sql)
        if self.row is None:
            return None
        if "WHERE email=$1" in sql and args[0] != self.row["email"]:
            return None
        if "WHERE id=$1" in sql and args[0] != self.row["id"]:
            return None
        fields = sql.split("SELECT ", 1)[1].split(" FROM users", 1)[0]
        return {k.strip(): self.row[k.strip()] for k in fields.split(",")}

    async def fetchval(self, sql, *args):
        if "mfa_failed_attempts = mfa_failed_attempts + 1" in sql:
            self.row["mfa_failed_attempts"] += 1
            self._trigger()
            return False
        raise AssertionError("unexpected SQL: " + sql)

    async def execute(self, sql, *args):
        self.sql.append(sql)
        if "INSERT INTO users" in sql:
            if self.row is None:
                self.row = user("admin", False)
                self.row["email"] = "admin@sahool.ye"
                self.row["password_hash"] = args[0]
            return "INSERT 0 1"
        if "SET mfa_last_totp_step=$1" in sql:
            step, uid = args
            prev = self.row["mfa_last_totp_step"]
            if uid == self.row["id"] and (prev is None or prev < step):
                self.row["mfa_last_totp_step"] = step
                self._trigger()
                return "UPDATE 1"
            return "UPDATE 0"
        if (
            "UPDATE users SET encrypted_mfa_secret=$1" in sql
            or "UPDATE users SET mfa_enabled=TRUE" in sql
        ):
            if self.before_enrollment_write:
                self.before_enrollment_write(self.row)
                self.before_enrollment_write = None
            if not self._where_holds(sql, args):
                return "UPDATE 0"
        if "UPDATE users SET encrypted_mfa_secret=$1" in sql:
            self.row.update(encrypted_mfa_secret=args[0], mfa_secret=None)
            self._trigger()
            return "UPDATE 1"
        if "UPDATE users SET mfa_enabled=TRUE" in sql:
            self.row.update(mfa_enabled=True, mfa_enabled_at="enabled-now", mfa_failed_attempts=0)
            if "encrypted_mfa_secret=$1" in sql:  # legacy plaintext migrated on activation
                self.row.update(encrypted_mfa_secret=args[0], mfa_secret=None)
            self._trigger()
            return "UPDATE 1"
        if "UPDATE users SET mfa_enabled=FALSE" in sql:
            self.row.update(mfa_enabled=False, mfa_secret=None, encrypted_mfa_secret=None)
            self._trigger()
            return "UPDATE 1"
        if "UPDATE users SET mfa_failed_attempts=0" in sql:
            self._trigger()
            return "UPDATE 1"
        if any(
            s in sql
            for s in [
                "set_config(",
                "INSERT INTO audit_log",
                "INSERT INTO mfa_audit_events",
                "DELETE FROM mfa_recovery_codes",
                "INSERT INTO mfa_recovery_codes",
            ]
        ):
            if "INSERT INTO mfa_audit_events" in sql:
                self.audit.append(args[3])
            return "OK"
        raise AssertionError("unexpected SQL: " + sql)

    @asynccontextmanager
    async def transaction(self):
        yield


class FakePool:
    def __init__(self, row):
        self.conn = FakeConnection(row)

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SAHOOL_ENV", "test")
    key = "auth-http-test-only-key-12345678901234567890123456789012345678901234567890"
    for attr in ("JWT_SECRET", "JWT_SIGNING_KEY", "JWT_VERIFY_KEY"):
        monkeypatch.setattr(main, attr, key)
    monkeypatch.setattr(main, "JWT_ALGORITHM", "HS256")
    pool = FakePool(user())
    redis = FakeRedis()
    monkeypatch.setattr(main, "_pool", pool)
    monkeypatch.setattr(main, "_redis", redis)
    monkeypatch.setattr(main, "BCRYPT_ROUNDS", 4)
    return pool, redis


async def request(method, path, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="https://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


def token_for(row):
    return main.create_access_token(
        row["id"], row["email"], row["role"], row["full_name"], row["tenant_id"]
    )[0]


def decode(token):
    return jwt.decode(
        token,
        main.JWT_VERIFY_KEY,
        algorithms=[main.JWT_ALGORITHM],
        audience="sahool",
        issuer="sahool-auth",
    )


@pytest.mark.asyncio
async def test_positive_password_login_issues_valid_jwt(boundary):
    r = await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    claims = decode(r.json()["access_token"])
    assert claims["sub"] == "7" and claims["tenant_id"] == TENANT and claims["role"] == "farmer"
    assert "sahool_at=" in r.headers["set-cookie"]


@pytest.mark.asyncio
async def test_positive_wrong_password_rejected(boundary):
    r = await request(
        "POST",
        "/v1/auth/login",
        json={"email": "synthetic@example.com", "password": "WrongPassword!"},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_positive_sensitive_login_requires_enrollment(boundary):
    pool, _ = boundary
    pool.conn.row = user("admin", False)
    r = await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )
    assert r.status_code == 403, r.text
    assert r.headers["x-mfa-enrollment-required"] == "true"


@pytest.mark.asyncio
async def test_positive_unauthenticated_setup_rejected(boundary):
    r = await request("POST", "/v1/auth/mfa/setup")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_positive_enabled_mfa_admin_can_refresh(boundary):
    pool, _ = boundary
    pool.conn.row = user("admin", True)
    refresh = await main.create_refresh_token(7, TENANT)
    r = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    assert decode(r.json()["access_token"])["role"] == "admin"
    again = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401, again.text


@pytest.mark.asyncio
async def test_positive_inactive_user_cannot_refresh(boundary):
    pool, _ = boundary
    pool.conn.row["active"] = False
    refresh = await main.create_refresh_token(7, TENANT)
    r = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_positive_revoked_jwt_is_rejected(boundary):
    pool, _ = boundary
    token = token_for(pool.conn.row)
    claims = decode(token)
    await main.revoke_jti(claims["jti"], claims["exp"])
    r = await request("GET", "/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_regression_disabled_required_mfa_cannot_mint_admin_session(
    boundary, record_property
):
    pool, _ = boundary
    pool.conn.row = user("admin", True)
    access = token_for(pool.conn.row)
    refresh = await main.create_refresh_token(7, TENANT)
    disabled = await request(
        "POST",
        "/v1/auth/mfa/disable",
        headers={"Authorization": "Bearer " + access},
        json={"code": pyotp.TOTP(SECRET).now()},
    )
    assert disabled.status_code == 200, disabled.text
    assert pool.conn.row["mfa_enabled"] is False
    login = await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )
    assert login.status_code == 403, login.text
    renewed = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    if renewed.status_code == 200:
        claims = decode(renewed.json()["access_token"])
        record_property("observed_new_jwt_role", claims["role"])
        assert claims["role"] == "admin"
    record_property("observed_refresh_status", renewed.status_code)
    assert renewed.status_code in (401, 403), (
        "Disabled required MFA minted another verified admin JWT; expected refusal"
    )


@pytest.mark.asyncio
async def test_regression_fresh_bootstrap_admin_has_scoped_enrollment_path(
    boundary, monkeypatch, record_property
):
    pool, _ = boundary
    pool.conn.row = None
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    await main._ensure_admin_user()
    assert pool.conn.row["role"] == "admin" and pool.conn.row["mfa_enabled"] is False
    login = await request(
        "POST", "/v1/auth/login", json={"email": "admin@sahool.ye", "password": PASSWORD}
    )
    record_property("observed_bootstrap_login_status", login.status_code)
    setup = await request("POST", "/v1/auth/mfa/setup")
    record_property("observed_unauthenticated_setup_status", setup.status_code)
    # Proposed fix contract: verified password supplies restricted enrollment authorization,
    # not a full admin session. Current API returns neither enrollment nor provisioning flow.
    body = login.json()
    challenge = body.get("enrollment_token") or body.get("mfa_enrollment_token")
    assert challenge, (
        "Bootstrap admin trapped: password login=403, setup=401, no enrollment authorization"
    )
    assert "access_token" not in body, "Full admin access must not precede MFA enrollment"
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + challenge}
    )
    assert setup.status_code == 200, setup.text
    activation = setup.json()["enrollment_token"]
    code = pyotp.TOTP(setup.json()["secret"]).now()
    activated = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers={"Authorization": "Bearer " + activation},
        json={"code": code},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["recovery_codes"]
    login = await request(
        "POST",
        "/v1/auth/login",
        json={
            "email": "admin@sahool.ye",
            "password": PASSWORD,
            "mfa_code": pyotp.TOTP(setup.json()["secret"]).at(time.time() + 30),
        },
    )
    assert login.status_code == 200, login.text
    assert decode(login.json()["access_token"])["role"] == "admin"


async def challenge(boundary):
    pool, _ = boundary
    pool.conn.row = user("admin", False)
    response = await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )
    assert response.status_code == 403, response.text
    assert "access_token" not in response.json()
    return response.json()["enrollment_token"]


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/v1/auth/me", None),
        ("GET", "/v1/auth/users", None),
        ("POST", "/v1/auth/mfa/disable", {"code": "123456"}),
    ],
)
async def test_enrollment_proof_cannot_access_other_endpoints(boundary, method, path, body):
    proof = await challenge(boundary)
    response = await request(method, path, headers={"Authorization": "Bearer " + proof}, json=body)
    assert response.status_code == 401, response.text


async def test_enrollment_proof_is_not_an_access_token_for_other_services(boundary):
    from shared.security.access_tokens import decode_access_token

    proof = await challenge(boundary)
    with pytest.raises(jwt.InvalidAudienceError):
        decode_access_token(
            proof, main.JWT_VERIFY_KEY, algorithm=main.JWT_ALGORITHM, site="enrollment-negative"
        )


async def test_enrollment_proof_cannot_refresh(boundary):
    proof = await challenge(boundary)
    response = await request("POST", "/v1/auth/refresh", json={"refresh_token": proof})
    assert response.status_code == 401, response.text


async def test_setup_and_activation_proofs_are_single_use_and_stage_scoped(boundary):
    proof = await challenge(boundary)
    wrong_stage = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers={"Authorization": "Bearer " + proof},
        json={"code": "123456"},
    )
    assert wrong_stage.status_code == 401, wrong_stage.text
    response = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert response.status_code == 200, response.text
    again = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert again.status_code == 401, again.text
    body = response.json()
    activation = body["enrollment_token"]
    wrong_stage = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + activation}
    )
    assert wrong_stage.status_code == 401, wrong_stage.text
    for expected in (200, 401):
        result = await request(
            "POST",
            "/v1/auth/mfa/activate",
            headers={"Authorization": "Bearer " + activation},
            json={"code": pyotp.TOTP(body["secret"]).now()},
        )
        assert result.status_code == expected, result.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("password_hash", "changed"),
        ("role", "viewer"),
        ("tenant_id", "other"),
        ("active", False),
    ],
)
async def test_enrollment_is_bound_to_current_account_state(boundary, field, value):
    proof = await challenge(boundary)
    pool, _ = boundary
    pool.conn.row[field] = value
    response = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert response.status_code == 401, response.text


async def test_activation_is_bound_to_exact_secret(boundary):
    proof = await challenge(boundary)
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    pool, _ = boundary
    pool.conn.row["encrypted_mfa_secret"] = mfa_crypto.encrypt_secret(pyotp.random_base32())
    response = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers={"Authorization": "Bearer " + setup.json()["enrollment_token"]},
        json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "mutation",
    ["expired", "wrong-purpose", "wrong-algorithm", "wrong-signature", "wrong-secret-type"],
)
async def test_invalid_enrollment_proofs_rejected(boundary, mutation):
    proof = await challenge(boundary)
    claims = jwt.decode(proof, options={"verify_signature": False})
    algorithm = "HS256"
    key = main.JWT_SIGNING_KEY
    if mutation == "expired":
        claims.update(
            iat=int(time.time()) - 600, nbf=int(time.time()) - 600, exp=int(time.time()) - 300
        )
    if mutation == "wrong-purpose":
        claims["purpose"] = "access"
    if mutation == "wrong-secret-type":
        claims["secret_state"] = {"not": "a string"}
    if mutation == "wrong-algorithm":
        algorithm = "HS512"
    if mutation == "wrong-signature":
        key = "w" * 48  # a valid-length HS256 key that is not the service key
    bad = jwt.encode(claims, key, algorithm=algorithm, headers={"typ": "mfa-enrollment+jwt"})
    response = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + bad}
    )
    assert response.status_code == 401, response.text


async def test_enrollment_fails_closed_without_redis(boundary, monkeypatch):
    pool, _ = boundary
    pool.conn.row = user("admin", False)
    monkeypatch.setattr(main, "_redis", None)
    response = await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )
    assert response.status_code == 503, response.text
    assert "enrollment_token" not in response.json()


async def test_rs256_enrollment_uses_configured_signing_and_verification_keys(
    boundary, monkeypatch
):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    verification = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    monkeypatch.setattr(main, "JWT_SIGNING_KEY", signing)
    monkeypatch.setattr(main, "JWT_VERIFY_KEY", verification)
    monkeypatch.setattr(main, "JWT_ALGORITHM", "RS256")
    proof = await challenge(boundary)
    claims = jwt.decode(
        proof,
        verification,
        algorithms=["RS256"],
        audience="sahool-mfa-enrollment",
        issuer="sahool-auth",
    )
    assert claims["exp"] - claims["iat"] == 300
    response = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("stage", ["setup", "activate"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("password_hash", "new-password"),
        ("role", "viewer"),
        ("tenant_id", "another-tenant"),
        ("active", False),
    ],
)
async def test_account_change_racing_final_enrollment_write_is_refused(
    boundary, stage, field, value
):
    proof = await challenge(boundary)
    body = None
    if stage == "activate":
        setup = await request(
            "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
        )
        proof = setup.json()["enrollment_token"]
        body = {"code": pyotp.TOTP(setup.json()["secret"]).now()}
    pool, _ = boundary
    original_secret = pool.conn.row["encrypted_mfa_secret"]
    pool.conn.before_enrollment_write = lambda row: row.update({field: value})
    response = await request(
        "POST", "/v1/auth/mfa/" + stage, headers={"Authorization": "Bearer " + proof}, json=body
    )
    assert response.status_code == 409, response.text
    assert pool.conn.row["mfa_enabled"] is False
    assert pool.conn.row["encrypted_mfa_secret"] == original_secret


async def test_refresh_rechecks_required_mfa_even_for_an_existing_refresh_token(boundary):
    pool, _ = boundary
    pool.conn.row = user("admin", False)
    refresh = await main.create_refresh_token(7, TENANT)
    response = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    assert response.status_code == 403, response.text
    assert response.headers["x-mfa-enrollment-required"] == "true"
    assert "access_token" not in response.json()


async def test_parallel_setup_uses_only_one_capability(boundary):
    proof = await challenge(boundary)

    async def setup():
        return await request(
            "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
        )

    responses = await asyncio.gather(setup(), setup())
    assert sorted(r.status_code for r in responses) == [200, 401]


async def test_wrong_totp_does_not_enable_mfa_or_consume_activation_proof(boundary):
    proof = await challenge(boundary)
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    headers = {"Authorization": "Bearer " + setup.json()["enrollment_token"]}
    rejected = await request(
        "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": "nototp"}
    )
    assert rejected.status_code == 400, rejected.text
    pool, _ = boundary
    assert pool.conn.row["mfa_enabled"] is False
    assert pool.conn.row["mfa_failed_attempts"] == 1
    accepted = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers=headers,
        json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
    )
    assert accepted.status_code == 200, accepted.text


async def test_redis_failure_during_consume_is_fail_closed(boundary, monkeypatch):
    proof = await challenge(boundary)
    pool, redis = boundary

    async def unavailable(key):
        raise ConnectionError("synthetic Redis outage")

    monkeypatch.setattr(redis, "getdel", unavailable)
    response = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert response.status_code == 503, response.text
    assert pool.conn.row["encrypted_mfa_secret"] is None


async def test_ordinary_access_session_can_setup_and_activate_optional_mfa(boundary):
    pool, _ = boundary
    headers = {"Authorization": "Bearer " + token_for(pool.conn.row)}
    setup = await request("POST", "/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    assert "enrollment_token" not in setup.json()
    activate = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers=headers,
        json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
    )
    assert activate.status_code == 200, activate.text
    assert pool.conn.row["mfa_enabled"] is True


async def test_legacy_plaintext_activation_remains_supported(boundary):
    pool, _ = boundary
    pool.conn.row["mfa_secret"] = SECRET
    response = await request(
        "POST",
        "/v1/auth/mfa/activate",
        headers={"Authorization": "Bearer " + token_for(pool.conn.row)},
        json={"code": pyotp.TOTP(SECRET).now()},
    )
    assert response.status_code == 200, response.text
    assert pool.conn.row["mfa_secret"] is None
    assert mfa_crypto.decrypt_secret(pool.conn.row["encrypted_mfa_secret"]) == SECRET


# ── Real-Postgres trigger semantics: updated_at moves on every users UPDATE ──────────────


@pytest.mark.parametrize("stage", ["setup", "activate"])
async def test_updated_at_bump_alone_does_not_invalidate_enrollment(boundary, stage):
    """``trg_users_updated_at`` bumps updated_at on any write (profile edit, TOTP step,
    failure counter). Binding the proof to it made every real activation 409."""
    proof = await challenge(boundary)
    body = None
    if stage == "activate":
        setup = await request(
            "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
        )
        assert setup.status_code == 200, setup.text
        proof = setup.json()["enrollment_token"]
        body = {"code": pyotp.TOTP(setup.json()["secret"]).now()}
    pool, _ = boundary
    pool.conn.row["full_name"] = "Renamed Meanwhile"
    pool.conn._trigger()
    pool.conn.before_enrollment_write = lambda row: row.update(updated_at="racing-write")
    response = await request(
        "POST", "/v1/auth/mfa/" + stage, headers={"Authorization": "Bearer " + proof}, json=body
    )
    assert response.status_code == 200, response.text


async def _activation_proof(boundary):
    proof = await challenge(boundary)
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert setup.status_code == 200, setup.text
    return setup.json()["enrollment_token"], setup.json()["secret"]


async def test_activation_retry_after_several_wrong_codes_below_cap(boundary):
    import mfa_enrollment

    activation, secret = await _activation_proof(boundary)
    headers = {"Authorization": "Bearer " + activation}
    for _ in range(mfa_enrollment.MAX_ACTIVATION_ATTEMPTS - 1):
        wrong = await request(
            "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": "000000"}
        )
        assert wrong.status_code == 400, wrong.text
    accepted = await request(
        "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": pyotp.TOTP(secret).now()}
    )
    assert accepted.status_code == 200, accepted.text
    pool, _ = boundary
    assert pool.conn.row["mfa_enabled"] is True


async def test_activation_proof_is_invalidated_after_attempt_cap(boundary):
    import mfa_enrollment

    activation, secret = await _activation_proof(boundary)
    headers = {"Authorization": "Bearer " + activation}
    for _ in range(mfa_enrollment.MAX_ACTIVATION_ATTEMPTS):
        wrong = await request(
            "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": "000000"}
        )
        assert wrong.status_code == 400, wrong.text
    correct = await request(
        "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": pyotp.TOTP(secret).now()}
    )
    assert correct.status_code == 401, correct.text
    pool, redis = boundary
    assert pool.conn.row["mfa_enabled"] is False
    assert not [k for k in redis.kv if k.startswith("sahool:mfa:enrollment:")]


async def test_parallel_wrong_codes_cannot_exceed_the_attempt_cap(boundary, monkeypatch):
    """Counting only after a failed verification let parallel requests all reach TOTP
    verification; refuted live: 30 parallel wrong codes were all verified. The attempt is now
    reserved atomically first, so a proof allows at most MAX_ACTIVATION_ATTEMPTS verifications."""
    import main
    import mfa_enrollment

    activation, _secret = await _activation_proof(boundary)
    headers = {"Authorization": "Bearer " + activation}
    checks = []
    real_check = main._consume_totp_step

    async def counting_check(*args, **kwargs):
        checks.append(1)
        await asyncio.sleep(0)  # yield so the parallel requests interleave
        return await real_check(*args, **kwargs)

    monkeypatch.setattr(main, "_consume_totp_step", counting_check)

    async def wrong():
        return await request(
            "POST", "/v1/auth/mfa/activate", headers=headers, json={"code": "000000"}
        )

    responses = await asyncio.gather(*(wrong() for _ in range(12)))
    assert len(checks) <= mfa_enrollment.MAX_ACTIVATION_ATTEMPTS, len(checks)
    assert all(r.status_code in (400, 401) for r in responses), [r.status_code for r in responses]
    _pool, redis = boundary
    assert not [k for k in redis.kv if k.startswith("sahool:mfa:enrollment:")]


async def test_parallel_activation_yields_exactly_one_success(boundary):
    activation, secret = await _activation_proof(boundary)
    headers = {"Authorization": "Bearer " + activation}
    totp = pyotp.TOTP(secret)

    async def activate(code):
        return await request("POST", "/v1/auth/mfa/activate", headers=headers, json={"code": code})

    responses = await asyncio.gather(activate(totp.now()), activate(totp.at(time.time() + 30)))
    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(200) == 1, [r.text for r in responses]
    assert statuses[1] in (400, 401), statuses
    pool, _ = boundary
    assert pool.conn.row["mfa_enabled"] is True


# ── MFA_SELF_ENROLLMENT_SCOPE: password-only enrollment is bootstrap-only by default ──────


def enrolled_admin(tenant=TENANT, *, role="admin", active=True, mfa=True, uid=8):
    other = user(role, mfa)
    other.update(id=uid, email=f"other{uid}@example.com", tenant_id=tenant, active=active)
    return other


async def login_admin(boundary, *, row=None):
    pool, _ = boundary
    pool.conn.row = row or user("admin", False)
    return await request(
        "POST", "/v1/auth/login", json={"email": "synthetic@example.com", "password": PASSWORD}
    )


def assert_refused_without_token(response):
    assert response.status_code == 403, response.text
    assert response.headers["x-mfa-enrollment-required"] == "true"
    body = response.json()
    assert "enrollment_token" not in body and "access_token" not in body
    assert "مسؤول" in body["detail"]


@pytest.mark.parametrize("value", [None, "", "bootstrap", " Bootstrap "])
async def test_default_bootstrap_scope_offers_first_admin_enrollment(boundary, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MFA_SELF_ENROLLMENT_SCOPE", raising=False)
    else:
        monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", value)
    response = await login_admin(boundary)
    assert response.status_code == 403, response.text
    assert response.json()["enrollment_token"]
    assert response.json()["expires_in"] == 300
    pool, _ = boundary
    assert "mfa_enrollment_offered" in pool.conn.audit


async def test_bootstrap_scope_refuses_when_tenant_already_has_enrolled_admin(
    boundary, monkeypatch
):
    monkeypatch.delenv("MFA_SELF_ENROLLMENT_SCOPE", raising=False)
    pool, redis = boundary
    pool.conn.others = [enrolled_admin()]
    response = await login_admin(boundary)
    assert_refused_without_token(response)
    assert "mfa_enrollment_refused" in pool.conn.audit
    assert not [k for k in redis.kv if k.startswith("sahool:mfa:enrollment:")]


async def test_bootstrap_scope_refuses_previously_enrolled_account(boundary, monkeypatch):
    monkeypatch.delenv("MFA_SELF_ENROLLMENT_SCOPE", raising=False)
    row = user("admin", False)
    row["mfa_enabled_at"] = "enrolled-then-disabled"
    assert_refused_without_token(await login_admin(boundary, row=row))


@pytest.mark.parametrize(
    "other",
    [
        {"tenant": "00000000-0000-0000-0000-000000000099"},
        {"role": "farmer"},
        {"active": False},
        {"mfa": False},
    ],
    ids=["other-tenant", "non-required-role", "inactive", "not-enrolled"],
)
async def test_bootstrap_scope_ignores_accounts_that_do_not_close_bootstrap(
    boundary, monkeypatch, other
):
    monkeypatch.delenv("MFA_SELF_ENROLLMENT_SCOPE", raising=False)
    pool, _ = boundary
    pool.conn.others = [enrolled_admin(**other)]
    response = await login_admin(boundary)
    assert response.status_code == 403, response.text
    assert response.json()["enrollment_token"]


async def test_scope_all_offers_every_unenrolled_required_account(boundary, monkeypatch):
    monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", "all")
    pool, _ = boundary
    pool.conn.others = [enrolled_admin()]
    row = user("admin", False)
    row["mfa_enabled_at"] = "enrolled-then-disabled"
    response = await login_admin(boundary, row=row)
    assert response.status_code == 403, response.text
    proof = response.json()["enrollment_token"]
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert setup.status_code == 200, setup.text


async def test_scope_off_never_offers_password_only_enrollment(boundary, monkeypatch):
    monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", "off")
    assert_refused_without_token(await login_admin(boundary))


@pytest.mark.parametrize("value", ["false", "0", "no", "none", "disabled", "DISABLE"])
async def test_disable_spellings_mean_off(boundary, monkeypatch, value):
    monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", value)
    assert_refused_without_token(await login_admin(boundary))


async def test_unknown_scope_fails_closed_to_bootstrap_and_warns(boundary, monkeypatch, caplog):
    monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", "everyone")
    pool, _ = boundary
    pool.conn.others = [enrolled_admin()]
    with caplog.at_level(logging.WARNING, logger="auth"):
        response = await login_admin(boundary)
    assert_refused_without_token(response)  # 'everyone' must not widen to 'all'
    assert any("MFA_SELF_ENROLLMENT_SCOPE" in r.getMessage() for r in caplog.records)
    pool.conn.others = []
    fresh = await login_admin(boundary)
    assert fresh.status_code == 403 and fresh.json()["enrollment_token"]


@pytest.mark.parametrize("stage", ["setup", "activate"])
async def test_in_flight_proof_closes_once_tenant_admin_enrolls(boundary, monkeypatch, stage):
    monkeypatch.delenv("MFA_SELF_ENROLLMENT_SCOPE", raising=False)
    proof = await challenge(boundary)
    body = None
    if stage == "activate":
        proof, secret = await _activation_proof_from(proof)
        body = {"code": pyotp.TOTP(secret).now()}
    pool, _ = boundary
    pool.conn.others = [enrolled_admin()]
    response = await request(
        "POST", "/v1/auth/mfa/" + stage, headers={"Authorization": "Bearer " + proof}, json=body
    )
    assert response.status_code == 401, response.text
    assert pool.conn.row["mfa_enabled"] is False


async def _activation_proof_from(proof):
    setup = await request(
        "POST", "/v1/auth/mfa/setup", headers={"Authorization": "Bearer " + proof}
    )
    assert setup.status_code == 200, setup.text
    return setup.json()["enrollment_token"], setup.json()["secret"]


# ── MFA disable revokes every existing session (not only via the refresh MFA re-check) ───


async def test_mfa_disable_revokes_existing_access_and_refresh_tokens(boundary):
    """A farmer is not MFA-required, so only revoke_all_user_sessions can stop these."""
    pool, redis = boundary
    pool.conn.row = user("farmer", True)
    access = token_for(pool.conn.row)
    refresh = await main.create_refresh_token(7, TENANT)
    assert redis.sets.get("sahool:user:refreshset:7")
    disabled = await request(
        "POST",
        "/v1/auth/mfa/disable",
        headers={"Authorization": "Bearer " + access},
        json={"code": pyotp.TOTP(SECRET).now()},
    )
    assert disabled.status_code == 200, disabled.text
    me = await request("GET", "/v1/auth/me", headers={"Authorization": "Bearer " + access})
    assert me.status_code == 401, me.text
    renewed = await request("POST", "/v1/auth/refresh", json={"refresh_token": refresh})
    assert renewed.status_code == 401, renewed.text
    assert "sahool:user:refreshset:7" not in redis.sets
    assert "sahool:user:token_floor:7" in redis.kv
