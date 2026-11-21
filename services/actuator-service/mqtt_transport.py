"""MQTT endpoint/TLS configuration without connecting or reading credentials."""

from __future__ import annotations

import ssl
from urllib.parse import urlsplit


def mqtt_endpoint(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"mqtt", "mqtts"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MQTT_BROKER_URL must be mqtt[s]://host[:port] without credentials")
    port = parsed.port if parsed.port is not None else (8883 if parsed.scheme == "mqtts" else 1883)
    if not 1 <= port <= 65535:
        raise ValueError("invalid MQTT port")
    return parsed.hostname, port


def mqtt_tls_kwargs(url: str, ca_file: str = "") -> dict:
    """mqtts never falls back to plaintext or disables hostname verification.

    Sources: https://aiomqtt.bo3hm.com/developer-interface.html
    https://docs.python.org/3/library/ssl.html#ssl.create_default_context
    """
    mqtt_endpoint(url)
    if urlsplit(url).scheme == "mqtt":
        return {}
    context = ssl.create_default_context(cafile=ca_file or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return {"tls_context": context}
