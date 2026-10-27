"""Entry gate for GDAL processes that cannot import SAHOOL code (the legacy TiTiler image).

blob_store and raster object_store derive GDAL's ``AWS_S3_ENDPOINT`` / ``AWS_HTTPS``
from ``resolve_configured_s3_endpoint``. The upstream TiTiler image runs none of our
code, so Compose used to hand it ``AWS_HTTPS`` straight from ``S3_USE_SSL`` and the
host from a separate variable: an external host over plaintext went through unchecked.

This gate applies the same decision, writes the GDAL variables from it alone, then
``exec``s the real command (the server becomes PID 1, signals unchanged). A rejected
endpoint stops here with a fixed code that never echoes the input.

Usage: python gdal_s3_env_gate.py <command> [args...]
Stdlib only; loads ``s3_endpoint_security.py`` from this file's directory.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path

# The GDAL variables this gate owns: whatever the environment carried is discarded.
GDAL_S3_KEYS = ("AWS_S3_ENDPOINT", "AWS_HTTPS", "AWS_VIRTUAL_HOSTING")
EX_CONFIG = 78


def _load_policy():
    path = Path(__file__).resolve().with_name("s3_endpoint_security.py")
    spec = importlib.util.spec_from_file_location("_sahool_gdal_gate_s3_policy", path)
    if spec is None or spec.loader is None:
        raise ImportError("s3_endpoint_security.py not found next to the gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_policy = _load_policy()
EndpointPolicyError = _policy.EndpointPolicyError


def derive_gdal_env(environ: Mapping[str, str]) -> dict[str, str]:
    """GDAL S3 variables from the shared decision; {} when no S3 endpoint is configured."""
    endpoint = str(environ.get("S3_ENDPOINT", "") or "").strip()
    bucket = str(environ.get("S3_BUCKET", "") or "").strip()
    if not endpoint:
        if bucket:
            raise EndpointPolicyError("bucket_without_endpoint")
        return {}
    decision = _policy.resolve_configured_s3_endpoint(
        endpoint,
        environ.get("S3_USE_SSL"),
        environ.get("S3_ALLOW_PLAINTEXT_INTERNAL", "false"),
        environ.get("S3_ALLOW_PLAINTEXT_LOOPBACK", "false"),
    )
    _policy.require_path_style_service_root(decision, bucket)
    return {
        "AWS_S3_ENDPOINT": decision.authority,
        "AWS_HTTPS": "YES" if decision.tls else "NO",
        "AWS_VIRTUAL_HOSTING": "FALSE",
    }


def apply_gdal_env(environ: MutableMapping[str, str]) -> None:
    derived = derive_gdal_env(environ)
    for key in GDAL_S3_KEYS:
        environ.pop(key, None)
    environ.update(derived)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: gdal_s3_env_gate.py <command> [args...]", file=sys.stderr)
        return 2
    try:
        apply_gdal_env(os.environ)
    except EndpointPolicyError as exc:
        print(f"unsafe S3 endpoint configuration: {exc}{_policy.hint_for(exc)}", file=sys.stderr)
        return EX_CONFIG
    os.execvp(argv[0], argv)
    return 127  # execvp does not return


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
