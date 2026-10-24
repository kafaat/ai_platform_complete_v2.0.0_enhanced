"""Exercise the actual service-token dependency without DB/service startup."""
import ast
import hmac
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import Header, HTTPException
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/guardrails-engine/main.py"


def dependency(configured):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_require_service_token")
    namespace = {"_Header": Header, "HTTPException": HTTPException, "_GR_AGENT_TOKEN": configured}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_require_service_token"]


class ServiceTokenTests(unittest.TestCase):
    def rejected(self, configured, supplied, expected):
        with self.assertRaises(HTTPException) as caught:
            dependency(configured)(supplied)
        self.assertEqual(caught.exception.status_code, expected)

    def test_valid_ascii_uses_constant_time_comparison(self):
        original = hmac.compare_digest
        with patch("hmac.compare_digest", wraps=original) as compare:
            self.assertTrue(dependency("fixture-only")("fixture-only"))
        compare.assert_called_once_with("fixture-only", "fixture-only")

    def test_wrong_ascii_is_unauthorized(self):
        self.rejected("fixture-only", "wrong", 401)

    def test_missing_header_is_unauthorized(self):
        self.rejected("fixture-only", None, 401)

    def test_empty_header_is_unauthorized(self):
        self.rejected("fixture-only", "", 401)

    def test_non_ascii_header_is_unauthorized(self):
        # ASGI/HTTP headers decoded as latin-1 can contain this code point.
        self.rejected("fixture-only", "\xff", 401)

    def test_missing_configuration_is_unavailable(self):
        self.rejected("", "fixture-only", 503)

    def test_non_ascii_configuration_is_unavailable(self):
        self.rejected("fixture-\xff", "fixture-only", 503)


if __name__ == "__main__":
    unittest.main()
