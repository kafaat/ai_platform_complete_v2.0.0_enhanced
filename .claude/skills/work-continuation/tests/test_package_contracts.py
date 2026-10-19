"""Offline positive/negative tests for UWRP v3 template semantics."""
from __future__ import annotations
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("uwrp_validate", ROOT / "scripts" / "validate_package.py")
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.state = json.loads((ROOT / "templates" / "state.example.json").read_text("utf-8"))
        self.receipt = json.loads((ROOT / "templates" / "shard-receipt.example.json").read_text("utf-8"))

    def test_original_byte_hash(self):
        path = ROOT / "references" / "PROTOCOL_v2_1_ORIGINAL.md"
        self.assertEqual(validator.digest(path.read_bytes()), validator.ORIGINAL_V2_1_SHA256)

    def test_examples_do_not_claim_execution(self):
        self.assertEqual(self.state["verification_status"], "RECORDED_UNVERIFIED")
        self.assertEqual(self.state["backup"]["status"], "BACKUP_PENDING")
        self.assertFalse(validator.check_state_contract(self.state))
        self.assertFalse(validator.check_receipt(self.receipt))

    def test_backup_verified_without_remote_readback_rejected(self):
        altered = copy.deepcopy(self.state)
        altered["backup"]["status"] = "BACKUP_VERIFIED"
        self.assertTrue(validator.check_state_contract(altered))

    def test_done_without_verified_source_rejected(self):
        altered = copy.deepcopy(self.state)
        altered["checkpoint"]["status"] = "DONE_VERIFIED"
        self.assertTrue(validator.check_state_contract(altered))

    def test_not_run_with_exit_code_rejected(self):
        altered = copy.deepcopy(self.receipt)
        altered["exit_code"] = 0
        self.assertTrue(validator.check_receipt(altered))

    def test_false_pass_without_evidence_rejected(self):
        altered = copy.deepcopy(self.receipt)
        altered["status"] = "PASSED"
        altered["exit_code"] = 0
        self.assertTrue(validator.check_receipt(altered))

    def test_sharded_preflight_false_promotion_rejected(self):
        altered = copy.deepcopy(self.receipt)
        altered["contiguous_preflight_proven"] = True
        self.assertTrue(validator.check_receipt(altered))

    def test_validity_key_independent_of_json_property_order(self):
        a = {"base_head": "A", "source_tree": "B", "command_digest": "C"}
        b = {"command_digest": "C", "source_tree": "B", "base_head": "A"}
        self.assertEqual(validator.key_digest(a), validator.key_digest(b))

    def test_changing_base_head_changes_key(self):
        a = {"source_tree": "same", "base_head": "A"}
        b = {"source_tree": "same", "base_head": "B"}
        self.assertNotEqual(validator.key_digest(a), validator.key_digest(b))

    def test_v2_baseline_unmodified(self):
        self.assertFalse(validator.validate(ROOT, check_hashes=False))

    def test_reference_missing_fails(self):
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td)
            (dst / "references").mkdir()
            (dst / "templates").mkdir()
            (dst / "SKILL.md").write_text("---\nname: work-continuation\ndescription: >-\n  example\n---\n`references/does-not-exist.md`\n", encoding="utf-8")
            self.assertTrue(validator.validate(dst, check_hashes=False))

    def test_no_host_io_or_repo_writes_in_validator_source(self):
        script = (ROOT / "scripts" / "validate_package.py").read_text("utf-8")
        for bad in ("urllib.request", "requests.post", "subprocess.run", "os.system(", "create_branch("):
            self.assertNotIn(bad, script)


if __name__ == "__main__":
    unittest.main()

# JSON Schema tests are optional; the package validator itself is standard-library-only.
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    Draft202012Validator = None
    FormatChecker = None


@unittest.skipUnless(Draft202012Validator is not None, "optional jsonschema not installed")
class SchemaIntegration(unittest.TestCase):
    def test_example_state_against_schema(self):
        schema = json.loads((ROOT / "templates" / "state.schema.json").read_text("utf-8"))
        data = json.loads((ROOT / "templates" / "state.example.json").read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)

    def test_invalid_extra_field_fails_schema(self):
        schema = json.loads((ROOT / "templates" / "state.schema.json").read_text("utf-8"))
        data = json.loads((ROOT / "templates" / "state.example.json").read_text("utf-8"))
        data["unexpected_permissions"] = "push_everywhere"
        self.assertFalse(Draft202012Validator(schema).is_valid(data))


@unittest.skipUnless(Draft202012Validator is not None, "optional jsonschema not installed")
class MoreSchemas(unittest.TestCase):
    def test_test_receipt_schema(self):
        schema = json.loads((ROOT / "templates" / "shard-receipt.schema.json").read_text("utf-8"))
        data = json.loads((ROOT / "templates" / "shard-receipt.example.json").read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)

    def test_external_action_schema(self):
        schema = json.loads((ROOT / "templates" / "external-action.schema.json").read_text("utf-8"))
        data = json.loads((ROOT / "templates" / "external-action.example.json").read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
