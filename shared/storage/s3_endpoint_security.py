"""Fail-closed S3 endpoint contract shared by boto3 and GDAL adapters.

Local PR candidate; not merged/deployed to SAHOOL. No DNS or network I/O.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class EndpointPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class EndpointDecision:
    endpoint_url: str
    host: str
    tls: bool
    classification: str
    authority: str


def _bool_flag(raw: str | bool | None) -> bool | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, bool):
        return raw
    v = str(raw).strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    raise EndpointPolicyError("invalid_ssl_flag")


def _loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_endpoint(
    endpoint: str,
    *,
    ssl_setting: str | bool | None = None,
    internal_hosts: frozenset[str] = frozenset(),
    allow_plaintext_loopback: bool = False,
    allow_plaintext_internal: bool = False,
) -> EndpointDecision:
    """Resolve endpoint without silently rewriting an explicit scheme.

    Bare hosts default to HTTPS. Explicit HTTP requires an opt-in *and* exact
    trusted hostname or loopback, never substring matches or RFC1918 inference.
    DNS authenticity, TLS CA and authorization must be verified separately.
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise EndpointPolicyError("empty_endpoint")
    raw = endpoint.strip()
    if re.search(r"[\s\x00-\x1f\x7f]", raw) or raw.startswith("//"):
        raise EndpointPolicyError("invalid_endpoint_characters")
    explicit_scheme = "://" in raw
    if explicit_scheme and not raw.startswith(("https://", "http://")):
        raise EndpointPolicyError("unsupported_scheme")
    ssl_flag = _bool_flag(ssl_setting)
    # Resolve the host using a temporary https: scheme, not by allowing
    # urlsplit() to parse a bare host:port as an unrelated URI scheme.
    try:
        parsed = urlsplit(raw if explicit_scheme else "https://" + raw)
    except ValueError as exc:
        raise EndpointPolicyError("invalid_endpoint_authority") from exc
    if parsed.username is not None or parsed.password is not None:
        raise EndpointPolicyError("userinfo_forbidden")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise EndpointPolicyError("endpoint_must_be_host_only")
    try:
        host = parsed.hostname
        port = parsed.port  # raises ValueError for malformed ports
    except ValueError as exc:
        raise EndpointPolicyError("invalid_port") from exc
    if not host or not re.fullmatch(r"[A-Za-z0-9_.:-]+", host):
        raise EndpointPolicyError("invalid_host")
    # Bracketed IPv6 is permissible; underscores in DNS labels are not.
    try:
        ipaddress.ip_address(host)
        ip_host = True
    except ValueError:
        ip_host = False
    if not ip_host:
        if any(
            not re.fullmatch(r"[A-Za-z0-9-]+", label) or not label
            for label in host.split(".")
        ):
            raise EndpointPolicyError("invalid_dns_label")
    if port is not None and not 1 <= port <= 65535:
        raise EndpointPolicyError("invalid_port")
    scheme = parsed.scheme if explicit_scheme else ("http" if ssl_flag is False else "https")
    if explicit_scheme and ssl_flag is not None and ssl_flag != (scheme == "https"):
        raise EndpointPolicyError("scheme_flag_conflict")
    trusted = {x.lower().rstrip(".") for x in internal_hosts}
    hostname = host.lower().rstrip(".")
    if _loopback(hostname):
        scope = "loopback"
    elif hostname in trusted:
        scope = "explicit_internal_allowlist"
    else:
        scope = "untrusted_host"
    if scheme == "http":
        if scope == "loopback" and not allow_plaintext_loopback:
            raise EndpointPolicyError("plaintext_loopback_requires_opt_in")
        if scope == "explicit_internal_allowlist" and not allow_plaintext_internal:
            raise EndpointPolicyError("plaintext_internal_requires_opt_in")
        if scope == "untrusted_host":
            raise EndpointPolicyError("plaintext_external_forbidden")
    host_out = f"[{host}]" if ":" in host else hostname
    port_out = f":{port}" if port else ""
    return EndpointDecision(
        endpoint_url=f"{scheme}://{host_out}{port_out}",
        host=hostname,
        tls=scheme == "https",
        classification=scope,
        authority=f"{host_out}{port_out}",
    )


def require_path_style_service_root(decision: EndpointDecision, bucket: str) -> None:
    """Reject a bucket-qualified endpoint when the client will add /bucket/key.

    An endpoint such as https://sahool-data.s3.example used with
    Bucket=sahool-data could otherwise address the bucket twice. The caller
    must configure the S3 service ROOT, not a virtual-hosted bucket URL.
    This is a structural check, not a DNS/security certificate check.
    """
    normalized_bucket = str(bucket).strip().lower()
    if normalized_bucket and decision.host.startswith(normalized_bucket + "."):
        raise EndpointPolicyError("bucket_prefixed_endpoint_forbidden_in_path_style")


# Only explicit service identifiers, never substring checks such as "minio" in a URL.
# Railway currently has no MinIO service; these are local Compose identities only.
TRUSTED_S3_SERVICE_HOSTS = frozenset({"sahool-minio", "sahool-minio.railway.internal"})


def resolve_configured_s3_endpoint(
    endpoint: str,
    ssl_setting: str | bool | None,
    allow_plaintext_internal: str | bool | None = None,
    allow_plaintext_loopback: str | bool | None = None,
) -> EndpointDecision:
    return resolve_endpoint(
        endpoint,
        ssl_setting=ssl_setting,
        internal_hosts=TRUSTED_S3_SERVICE_HOSTS,
        allow_plaintext_internal=_bool_flag(allow_plaintext_internal) is True,
        allow_plaintext_loopback=_bool_flag(allow_plaintext_loopback) is True,
    )
