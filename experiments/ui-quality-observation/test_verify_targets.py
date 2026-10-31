"""Synthetic contract tests; never inspect user data or start a SAHOOL backend."""
import json
import tempfile
import unittest
from pathlib import Path

from verify_targets import (
    ObservationBlocked,
    TARGETS,
    bounded,
    observe,
    primary_count,
    strict_json,
)

SHA = "a" * 40
IMAGE = "sha256:" + "b" * 64


class ReadOnlyUIObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.logs = Path(self.temp.name) / "reports"
        self.logs.mkdir()
        for short, relative in TARGETS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("export const KnownFixture = () => <section aria-label='test' />;")
            (self.logs / (short + ".json")).write_text('{"findings":[]}')
            (self.logs / (short + ".exit")).write_text("0")

    def reviewed(self):
        return observe(self.root, self.logs, SHA, IMAGE)

    def test_four_surfaces_are_observed_but_not_accepted(self):
        r = self.reviewed()
        self.assertEqual(r["status"], "OBSERVED_FOR_REVIEW")
        self.assertEqual(r["surfaces_checked"], 4)
        self.assertEqual(r["total_primary_findings"], 0)
        self.assertFalse(r["production_accepted"])
        self.assertFalse(r["browser_acceptance_executed"])
        self.assertFalse(r["end_to_end_product_flow_tested"])

    def test_nonzero_findings_are_recorded_not_release_blockers(self):
        (self.logs / "maphub.json").write_text('{"findings":[{"rule":"demo"}]}')
        (self.logs / "maphub.exit").write_text("2")
        r = self.reviewed()
        self.assertEqual(r["total_primary_findings"], 1)
        self.assertFalse(r["style_findings_block_release"])

    def test_forged_clean_exit_rejected(self):
        (self.logs / "maphub.json").write_text('{"findings":[{"rule":"demo"}]}')
        with self.assertRaisesRegex(ObservationBlocked, "DETECTOR_EXIT_OR_FINDINGS_MISMATCH"):
            self.reviewed()

    def test_invalid_source_reference_rejected(self):
        with self.assertRaisesRegex(ObservationBlocked, "INVALID_SOURCE_OR_IMAGE_IDENTITY"):
            observe(self.root, self.logs, "HEAD", IMAGE)
        with self.assertRaisesRegex(ObservationBlocked, "INVALID_SOURCE_OR_IMAGE_IDENTITY"):
            observe(self.root, self.logs, SHA, "node:24")

    def test_missing_and_symlinked_inputs_rejected(self):
        source = self.root / TARGETS["irrigation"]
        source.unlink()
        with self.assertRaises(OSError):
            self.reviewed()
        source.symlink_to(self.root / TARGETS["maphub"])
        with self.assertRaisesRegex(ObservationBlocked, "UNSAFE_INPUT"):
            self.reviewed()

    def test_duplicate_nonfinite_and_invalid_json_rejected(self):
        for content in (b'{"findings":[],"findings":[]}',
                        b'{"findings":NaN}', b'{bad'):
            with self.subTest(content=content):
                with self.assertRaises(ObservationBlocked):
                    strict_json(content)

    def test_oversized_report_rejected_without_full_read(self):
        file = self.logs / "maphub.json"
        with file.open("wb") as stream:
            stream.truncate(4 * 1024 * 1024)
        with self.assertRaisesRegex(ObservationBlocked, "OVERSIZED_INPUT"):
            self.reviewed()

    def test_nested_collections_are_supported(self):
        self.assertEqual(primary_count({"files": [{"findings": [{"id": "x"}]},
                                                   {"findings": []}]}), 1)
        with self.assertRaisesRegex(ObservationBlocked, "UNSUPPORTED_DETECTOR_RESULT"):
            primary_count({"success": True})


if __name__ == "__main__":
    unittest.main()
