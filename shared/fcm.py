"""FCM HTTP v1 credentials and delivery; never probes instance metadata.

Only an explicitly provisioned service account activates this adapter. Legacy
server keys do not activate a retired API. Configuration readiness is not proof
of Google IAM permissions or device delivery.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


@dataclass(frozen=True)
class Credentials:
    project_id: str
    client_email: str
    private_key: str = field(repr=False)


def credentials() -> Credentials | None:
    raw = os.getenv("FCM_CREDENTIALS_JSON", "")
    if not raw or len(raw) > 65536:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("type") != "service_account":
            return None
        project = data["project_id"]
        email = data["client_email"]
        if not isinstance(project, str) or not re.fullmatch(
            r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project
        ):
            return None
        if not isinstance(email, str) or not re.fullmatch(
            r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.iam\.gserviceaccount\.com", email
        ):
            return None
        # Never follow a credential-supplied URL to an arbitrary/private host.
        if data.get("token_uri") != TOKEN_URI:
            return None
        key = data["private_key"]
        parsed = serialization.load_pem_private_key(key.encode(), password=None)
        if not isinstance(parsed, rsa.RSAPrivateKey) or parsed.key_size < 2048:
            return None
        return Credentials(project, email, key)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def fcm_push_active() -> bool:
    return credentials() is not None


_token_lock = asyncio.Lock()
_token_cache: tuple[str, str, float] | None = None


async def _access_token(client: httpx.AsyncClient, account: Credentials) -> str:
    global _token_cache
    fingerprint = hashlib.sha256(
        (account.client_email + account.project_id + account.private_key).encode()
    ).hexdigest()
    async with _token_lock:
        if _token_cache and _token_cache[0] == fingerprint and time.monotonic() < _token_cache[2]:
            return _token_cache[1]
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": account.client_email,
                "scope": SCOPE,
                "aud": TOKEN_URI,
                "iat": now,
                "exp": now + 3600,
            },
            account.private_key,
            algorithm="RS256",
        )
        response = await client.post(
            TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        result = response.json()
        token = result.get("access_token")
        expires = result.get("expires_in")
        if (
            not isinstance(token, str)
            or not token
            or result.get("token_type", "").lower() != "bearer"
        ):
            raise ValueError("invalid OAuth receipt")
        if type(expires) is not int or not 60 <= expires <= 3600:
            raise ValueError("invalid OAuth expiry")
        _token_cache = (fingerprint, token, time.monotonic() + expires - 60)
        return token


async def send_push(push_token: str, title: str, body: str) -> bool:
    """True means FCM accepted a named message, not that the handset received it."""
    global _token_cache
    account = credentials()
    if account is None or not push_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            token = await _access_token(client, account)
            response = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{account.project_id}/messages:send",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "message": {"token": push_token, "notification": {"title": title, "body": body}}
                },
            )
            if response.status_code == 401:
                _token_cache = None
            response.raise_for_status()
            name = response.json().get("name", "")
            prefix = f"projects/{account.project_id}/messages/"
            return isinstance(name, str) and name.startswith(prefix) and len(name) > len(prefix)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return False
