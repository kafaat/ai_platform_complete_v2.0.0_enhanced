"""Deterministic regressions for the source-bound SAHOOL UI shadow gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ui_quality_shadow import (
    MAX_REPORT,
    TARGETS,
    ShadowBlocked,
    evaluate,
    findings_count,
    parse_json,
)

# CI invokes this script under an explicit C locale: keep diagnostics UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

IMAGE = "sha256:" + "a" * 64


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


class UIQualityShadowContracts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.root = self.folder / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "qa@example.invalid")
        git(self.root, "config", "user.name", "Reviewed Fixture")
        self.files = {}
        for key, relative in TARGETS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "export default function Component() { return null; }\n", encoding="utf-8"
            )
            self.files[key] = path
        # Test fixture has the same path contract as the real positive control.
        control = self.root / "experiments/ui-quality-shadow/fixtures/source-positive-control.tsx"
        control.parent.mkdir(parents=True, exist_ok=True)
        control.write_text(
            'export function Broken() { return <h1 className="text-purple-700">Bad</h1>; }\n'
        )
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "reviewed UI fixture")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.reports = self.folder / "reports"
        self.reports.mkdir()
        for key in TARGETS:
            (self.reports / (key + ".json")).write_text(
                '{"findings":[{"id":"advisory"}]}' if key == "maphub" else '{"findings":[]}',
                encoding="utf-8",
            )
            (self.reports / (key + ".exit")).write_text(
                "2\n" if key == "maphub" else "0\n", encoding="ascii"
            )

        (self.reports / "positive-control.json").write_text('{"findings":[{"id":"known-pattern"}]}')
        (self.reports / "positive-control.exit").write_text("2\n")

    def check(self):
        return evaluate(self.root, self.reports, IMAGE)

    def test_real_git_binding_and_advisory_only(self):
        result = self.check()
        self.assertEqual(result["source_sha"], self.head)
        self.assertEqual(result["target_count"], 4)
        self.assertTrue(result["positive_control"]["verified"])
        self.assertGreater(result["positive_control"]["findings_detected"], 0)
        self.assertEqual(sum(x["findings_advisory"] for x in result["targets"]), 1)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertFalse(result["style_findings_block_release"])
        self.assertFalse(result["production_accepted"])
        self.assertFalse(result["wcag_conformance_proven"])
        self.assertFalse(result["browser_behavior_tested"])
        for target in result["targets"]:
            path = self.root / target["path"]
            data = path.read_bytes()
            self.assertEqual(target["source_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(
                target["git_blob"], git(self.root, "rev-parse", "HEAD:" + target["path"])
            )

    def test_changed_worktree_rejected_even_if_detector_json_passes(self):
        self.files["irrigation"].write_text("unauthorized local source change")
        with self.assertRaisesRegex(ShadowBlocked, "WORKTREE_DIFFERS_FROM_COMMIT"):
            self.check()

    def test_linked_source_refused_before_read(self):
        path = self.files["field-management"]
        path.unlink()
        path.symlink_to(self.files["irrigation"])
        with self.assertRaisesRegex(ShadowBlocked, "SOURCE_PATH_UNSAFE_OR_MISSING"):
            self.check()

    def test_duplicate_detector_keys_are_not_accepted(self):
        (self.reports / "maphub.json").write_text('{"findings":[],"findings":[{}]}')
        with self.assertRaisesRegex(ShadowBlocked, "DUPLICATE_JSON_KEY"):
            self.check()

    def test_nonfinite_detector_json_rejected(self):
        (self.reports / "maphub.json").write_text('{"findings":NaN}')
        with self.assertRaisesRegex(ShadowBlocked, "NONFINITE_JSON"):
            self.check()

    def test_positive_control_zero_findings_is_blocked(self):
        (self.reports / "positive-control.json").write_text('{"findings":[]}')
        with self.assertRaisesRegex(ShadowBlocked, "POSITIVE_CONTROL_NO_FINDINGS"):
            self.check()

    def test_positive_control_detector_not_active_is_blocked(self):
        (self.reports / "positive-control.exit").write_text("0\n")
        with self.assertRaisesRegex(ShadowBlocked, "POSITIVE_CONTROL_DETECTOR_NOT_ACTIVE"):
            self.check()

    def test_positive_control_missing_is_blocked(self):
        (self.reports / "positive-control.json").unlink()
        with self.assertRaises((ShadowBlocked, OSError)):
            self.check()

    def test_missing_report_rejected(self):
        (self.reports / "remote-sensing.json").unlink()
        with self.assertRaises((ShadowBlocked, OSError)):
            self.check()

    def test_oversized_sparse_report_rejected_before_full_read(self):
        with (self.reports / "maphub.json").open("wb") as stream:
            stream.truncate(MAX_REPORT * 10)
        with self.assertRaisesRegex(ShadowBlocked, "EMPTY_OR_OVERSIZED_INPUT"):
            self.check()

    def test_symlinked_report_rejected(self):
        p = self.reports / "maphub.json"
        p.unlink()
        p.symlink_to(self.reports / "irrigation.json")
        with self.assertRaisesRegex(ShadowBlocked, "UNSAFE_INPUT"):
            self.check()

    def test_findings_and_exit_status_must_agree(self):
        (self.reports / "maphub.exit").write_text("0\n")
        with self.assertRaisesRegex(ShadowBlocked, "DETECTOR_EXIT_MISMATCH"):
            self.check()

    def test_detector_execution_error_is_not_an_advisory(self):
        (self.reports / "maphub.exit").write_text("1\n")
        with self.assertRaisesRegex(ShadowBlocked, "DETECTOR_DID_NOT_COMPLETE"):
            self.check()

    def test_unrecognized_shape_and_array_types_refused(self):
        for raw in (b'{"success":true}', b'{"findings":["bad"]}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ShadowBlocked):
                    findings_count(parse_json(raw))

    def test_invalid_image_identifier_rejected(self):
        with self.assertRaisesRegex(ShadowBlocked, "IMAGE_ID_REQUIRED"):
            evaluate(self.root, self.reports, "node:24")

    def test_cli_output_within_source_rejected_before_write(self):
        command = [
            sys.executable,
            str(Path(__file__).with_name("ui_quality_shadow.py")),
            "--root",
            str(self.root),
            "--reports",
            str(self.reports),
            "--image-id",
            IMAGE,
            "--out",
            str(self.root / "shadow.json"),
        ]
        p = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["reason"], "OUTPUT_WITHIN_SOURCE")
        self.assertFalse((self.root / "shadow.json").exists())

    def test_cli_writes_review_only_receipt(self):
        out = self.folder / "review.json"
        p = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("ui_quality_shadow.py")),
                "--root",
                str(self.root),
                "--reports",
                str(self.reports),
                "--image-id",
                IMAGE,
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        payload = json.loads(out.read_text())
        self.assertEqual(payload["source_sha"], self.head)
        self.assertEqual(payload["status"], "REVIEW_ONLY")
        self.assertFalse(payload["style_findings_block_release"])


if __name__ == "__main__":
    unittest.main()
