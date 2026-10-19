"""Offline tests for UWRP Professional v4.2. Each check has a negative control.

Run:  python3 work-router/tests/test_pack.py
These are structural and logic tests; they say nothing about agent behaviour.
"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load("verify_pack", "work-router/scripts/verify_pack.py")
router = load("route_work", "work-router/scripts/route_work.py")
contract = load("check_contract", "intent-to-proof/scripts/check_contract.py")
trigger = load("trigger_eval", "skill-evaluator/scripts/trigger_eval.py")


class Copy:
    """A throwaway copy of the managed skills, so a test can damage it."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="uwrp42-")
        self.root = Path(self.tmp.name)
        for name in verify.managed_skills():
            shutil.copytree(
                ROOT / name,
                self.root / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        return self.root

    def __exit__(self, *exc):
        self.tmp.cleanup()


class Integrity(unittest.TestCase):
    def test_pack_passes(self):
        problems, _ = verify.verify(ROOT)
        self.assertEqual([], problems)

    def test_an_edit_breaks_the_manifest(self):
        with Copy() as root:
            path = root / "safe-delivery" / "SKILL.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8"
            )
            self.assertIn("does not match", " ".join(verify.verify(root)[0]))

    def test_a_long_description_is_rejected(self):
        with Copy() as root:
            path = root / "change-review" / "SKILL.md"
            text = path.read_text(encoding="utf-8")
            start = text.index('description: "') + len('description: "')
            path.write_text(
                text[:start] + "x" * 190 + " " + text[start:], encoding="utf-8"
            )
            (root / verify.MANIFEST).write_text(
                verify.manifest_text(root), encoding="utf-8"
            )
            self.assertIn("description is", " ".join(verify.verify(root)[0]))

    def test_a_link_out_of_the_skill_folder_is_rejected(self):
        with Copy() as root:
            path = root / "change-review" / "SKILL.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n[x](../safe-delivery/SKILL.md)\n",
                encoding="utf-8",
            )
            (root / verify.MANIFEST).write_text(
                verify.manifest_text(root), encoding="utf-8"
            )
            self.assertIn("leaves its skill folder", " ".join(verify.verify(root)[0]))

    def test_an_upload_incompatible_key_is_rejected(self):
        with Copy() as root:
            path = root / "skill-evaluator" / "SKILL.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "metadata:", "when_to_use: x\nmetadata:", 1
                ),
                encoding="utf-8",
            )
            (root / verify.MANIFEST).write_text(
                verify.manifest_text(root), encoding="utf-8"
            )
            self.assertIn(
                "rejected by claude.ai upload", " ".join(verify.verify(root)[0])
            )

    def test_router_text_must_list_every_route(self):
        with Copy() as root:
            path = root / "work-router" / "SKILL.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "`failure-investigation`", "failure investigation"
                ),
                encoding="utf-8",
            )
            (root / verify.MANIFEST).write_text(
                verify.manifest_text(root), encoding="utf-8"
            )
            self.assertIn(
                "does not list routed skill failure-investigation",
                " ".join(verify.verify(root)[0]),
            )

    def test_missing_baselines_are_a_note_unless_required(self):
        with Copy() as root:
            problems, notes = verify.verify(root)
            self.assertEqual([], problems)
            self.assertTrue(any("baseline not installed" in n for n in notes))
            self.assertTrue(
                any("baseline not installed" in p for p in verify.verify(root, True)[0])
            )

    def test_action_template_never_claims_authority(self):
        with Copy() as root:
            path = root / "safe-delivery" / "assets" / "external-action.example.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["authorized"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            (root / verify.MANIFEST).write_text(
                verify.manifest_text(root), encoding="utf-8"
            )
            self.assertIn("claims authority", " ".join(verify.verify(root)[0]))


class Routing(unittest.TestCase):
    def setUp(self):
        self.routing = router.load_routes()

    def test_simple_task_loads_nothing(self):
        result = router.choose({}, self.routing)
        self.assertEqual(("LIGHT", []), (result["mode"], result["skills"]))

    def test_flags_map_to_skills_and_mode(self):
        result = router.choose(
            {"interrupted": True, "external_action": True}, self.routing
        )
        self.assertEqual(
            {"work-continuation", "safe-delivery"},
            {s["skill"] for s in result["skills"]},
        )
        self.assertEqual("COORDINATED", result["mode"])

    def test_missing_skill_is_reported_not_assumed(self):
        with tempfile.TemporaryDirectory() as empty:
            result = router.choose({"unknown_failure": True}, self.routing, Path(empty))
            self.assertEqual(["failure-investigation"], result["missing"])

    def test_non_boolean_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            router.choose({"multi_agent": "yes"}, self.routing)


def base_contract():
    return json.loads(
        (ROOT / "intent-to-proof/assets/work-contract.example.json").read_text(
            encoding="utf-8"
        )
    )


class Contract(unittest.TestCase):
    def test_example_is_consistent_and_measured(self):
        errors, metrics = contract.check(base_contract())
        self.assertEqual([], errors)
        self.assertEqual(0.5, metrics["closure"])

    def test_verified_without_evidence_is_refused(self):
        c = base_contract()
        c["requirements"][0]["status"] = "VERIFIED"
        self.assertIn("VERIFIED without", " ".join(contract.check(c)[0]))

    def test_pass_without_exit_code_or_ref_is_refused(self):
        c = base_contract()
        c["requirements"][1]["evidence"] = [{"result": "PASS"}]
        self.assertIn("neither exit_code nor ref", " ".join(contract.check(c)[0]))

    def test_pass_with_nonzero_exit_is_refused(self):
        c = base_contract()
        c["requirements"][1]["evidence"][0]["exit_code"] = 1
        self.assertIn("PASS with exit_code 1", " ".join(contract.check(c)[0]))

    def test_cycle_is_refused(self):
        c = base_contract()
        c["tasks"][0]["depends_on"] = ["TASK-002"]
        self.assertIn("dependency cycle", " ".join(contract.check(c)[0]))

    def test_two_writers_are_refused(self):
        c = base_contract()
        c["tasks"][1]["writes"] = ["src/feature.py"]
        self.assertIn("one writer per resource", " ".join(contract.check(c)[0]))

    def test_unknown_requirement_is_refused(self):
        c = base_contract()
        c["tasks"][0]["requirements"] = ["REQ-999"]
        self.assertIn("unknown requirement", " ".join(contract.check(c)[0]))


class Trigger(unittest.TestCase):
    def setUp(self):
        self.cases = trigger.load_cases(
            ROOT / "skill-evaluator/assets/trigger_scenarios.json"
        )

    def test_scenarios_cover_negatives_and_arabic(self):
        negatives = [
            c
            for c in self.cases
            if not (c["required"] or c["any_of"] or c["acceptable"])
        ]
        arabic = [c for c in self.cases if any("؀" <= ch <= "ۿ" for ch in c["prompt"])]
        self.assertGreaterEqual(len(negatives), 8)
        self.assertGreaterEqual(len(arabic), 5)

    def test_perfect_answers_score_full(self):
        answers = {c["id"]: c["required"] + c["any_of"][:1] for c in self.cases}
        self.assertEqual(
            len(self.cases), trigger.score(self.cases, answers, None)["passed"]
        )

    def test_loading_a_skill_on_a_negative_is_a_false_trigger(self):
        answers = {c["id"]: c["required"] + c["any_of"][:1] for c in self.cases}
        answers["NEG-01"] = ["work-router"]
        result = trigger.score(self.cases, answers, None)
        self.assertEqual(1, result["false_triggers"])

    def test_emit_is_blind_and_deterministic(self):
        skills = trigger.installed_skills(ROOT)
        first = trigger.emit(skills, self.cases, 7)
        self.assertEqual(first, trigger.emit(skills, self.cases, 7))
        self.assertNotIn("required", first)

    def test_folded_description_is_parsed(self):
        meta = trigger.frontmatter(
            "---\nname: x\ndescription: >-\n  one\n  two\n---\nbody\n"
        )
        self.assertEqual("one two", meta["description"])


if __name__ == "__main__":
    unittest.main()
