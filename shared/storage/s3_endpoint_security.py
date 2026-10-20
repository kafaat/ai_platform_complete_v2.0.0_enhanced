"""Fail-closed S3 endpoint contract shared by boto3 and GDAL adapters.

Also applied to the legacy TiTiler image by gdal_s3_env_gate.py. No DNS or network I/O.
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


_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")


def _loopback(host: str) -> bool:
    # Only the literal name: "*.localhost" may be resolved by an upstream DNS server
    # inside a container, so it is not guaranteed to stay on 127.0.0.0/8.
    if host == "localhost":
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
    if explicit_scheme and not raw.lower().startswith(("https://", "http://")):
        raise EndpointPolicyError("unsupported_scheme")
    ssl_flag = _bool_flag(ssl_setting)
    # Resolve the host using a temporary https: scheme, not by allowing
    # urlsplit() to parse a bare host:port as an unrelated URI scheme.
    # urlsplit and its accessors raise ValueError on malformed brackets or ports; the
    # message can quote the input, so it is replaced by a fixed code (`from None`).
    try:
        parsed = urlsplit(raw if explicit_scheme else "https://" + raw)
        has_userinfo = parsed.username is not None or parsed.password is not None
        host = parsed.hostname
    except ValueError:
        raise EndpointPolicyError("invalid_host") from None
    if has_userinfo:
        raise EndpointPolicyError("userinfo_forbidden")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise EndpointPolicyError("endpoint_must_be_host_only")
    try:
        port = parsed.port
    except ValueError:
        raise EndpointPolicyError("invalid_port") from None
    if not host or not re.fullmatch(r"[A-Za-z0-9_.:-]+", host):
        raise EndpointPolicyError("invalid_host")
    try:
        ipaddress.ip_address(host)
        ip_host = True
    except ValueError:
        ip_host = False
    # Brackets are for IPv6 literals only (urlsplit would turn "[v1.x]" into a name).
    if "[" in parsed.netloc and not (ip_host and ":" in host):
        raise EndpointPolicyError("invalid_host")
    if not ip_host:
        labels = host.split(".")
        # No empty or hyphen-edged labels, and a numeric last label is a malformed IP.
        if any(not _DNS_LABEL.fullmatch(x) for x in labels) or labels[-1].isdigit():
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
        f"{scheme}://{host_out}{port_out}",
        hostname,
        scheme == "https",
        scope,
        f"{host_out}{port_out}",
    )


def require_path_style_service_root(decision: EndpointDecision, bucket: str) -> None:
    """Reject a bucket-qualified endpoint: the path-style client adds /<bucket>/<key> itself.

    With S3_ENDPOINT=https://sahool-data.s3.example and S3_BUCKET=sahool-data, every
    request would address the bucket twice. The endpoint must be the service root.
    """
    normalized_bucket = str(bucket or "").strip().lower()
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
