"""Expose only canonical security helpers when MCP's shared package shadows root.

The image already copies root shared/security alongside this package. In a source
checkout extend only this subpackage, without making unrelated shared modules
visible or copying the verification implementation.
"""

from pathlib import Path

_canonical = (Path(__file__).resolve().parent / "../../../../shared/security").resolve()
if _canonical.is_dir() and _canonical != Path(__file__).resolve().parent:
    __path__.append(str(_canonical))
