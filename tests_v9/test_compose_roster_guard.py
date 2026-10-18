"""v9 وحدَه يُعرّف المكدّس — ``COMPOSE-ALTERNATES-UNGUARDED-AND-NAME-INCOMPATIBLE-01``.

يشهد على ``scripts/ci/compose_roster_guard.py``: الشجرةُ المُلتزَمة نظيفة، والبدائلُ في
التاريخ وحدَه، وكلُّ صنفِ عطلٍ يعرفه الحارس يُكتشَف على شجرةٍ اصطناعيّة.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "ci" / "compose_roster_guard.py"
ROSTER = ROOT / "docs" / "architecture" / "compose_file_roster.json"

#: البدائلُ التي نُقلت بقرار المالك (2026-10-15) — بأسمائها في التاريخ.
FORMER_ALTERNATES = {
    "docker-compose.unified.yml": "docker-compose.unified.yml",
    "docker-compose.light.yml": "docker-compose.light.yml",
    "docker-compose.fixed.yml": "docker-compose.fixed.yml",
    "docker-compose.odoo-snippet.yml": "docker-compose.odoo-snippet.yml",
    "frontend/docker-compose.web.yml": "frontend.docker-compose.web.yml",
    "scripts_v9/setup_unified.sh": "setup_unified.sh",
}


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("_compose_roster_guard", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_committed_tree_is_clean(guard):
    problems = guard.audit()
    assert problems == [], "\n".join(problems)


def test_the_former_alternates_live_only_in_history():
    tracked = set(
        subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
            check=True,
        ).stdout.splitlines()
    )
    history = json.loads(ROSTER.read_text(encoding="utf-8"))["history_dir"]
    for old, new in FORMER_ALTERNATES.items():
        assert old not in tracked, f"{old} عاد إلى الشجرة الحيّة — تعريفٌ ثانٍ للمكدّس"
        assert f"{history}/{new}" in tracked, f"{history}/{new} غائب — التاريخُ فقد البديل"


def test_the_guard_sees_compose_files_outside_the_root(guard):
    """السطحُ أوسعُ من الجذر: ملفٌّ متعقَّب في أيّ دليل يدخل المساواة."""
    tracked = guard.tracked_compose_files("docs/history/compose")
    assert "docker-compose.v9.yml" in tracked
    assert not any(p.startswith("docs/history/compose/") for p in tracked)
    assert guard._COMPOSE_NAME.search("services/x/compose.yaml")
    assert guard._COMPOSE_NAME.search("frontend/docker-compose.web.yml")
    assert not guard._COMPOSE_NAME.search("docs/compose_notes.md")


# ── شجرةٌ اصطناعيّة: كلّ صنفِ عطلٍ يُكتشَف ────────────────────────────────────


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


_BASE = """services:
  sahool-auth: {image: a}
  sahool-raster-service: {image: r}
networks:
  sahool-internal: {}
"""


def _roster(files: dict) -> dict:
    return {"base": "docker-compose.v9.yml", "history_dir": "docs/history/compose", "files": files}


def test_an_unrostered_compose_file_blocks(guard, tmp_path):
    """مساواةُ المجموعات: ملفٌّ متعقَّب خارج السجلّ يحجب — وهو عطلُ الفجوة نفسُه."""
    root = _tree(tmp_path, {"docker-compose.v9.yml": _BASE})
    problems = guard.audit(
        root,
        tracked=["docker-compose.v9.yml", "docker-compose.unified.yml"],
        roster=_roster({}),
    )
    assert any("docker-compose.unified.yml" in p and "خارج السجلّ" in p for p in problems), problems


def test_a_rostered_file_that_is_gone_blocks(guard, tmp_path):
    root = _tree(tmp_path, {"docker-compose.v9.yml": _BASE, "ci.yml": "docker-compose.x.yml"})
    problems = guard.audit(
        root,
        tracked=["docker-compose.v9.yml"],
        roster=_roster({"docker-compose.x.yml": {"role": "overlay", "consumers": ["ci.yml"]}}),
    )
    assert any("سجلٌّ بائت" in p for p in problems), problems


def test_an_overlay_naming_a_service_that_does_not_exist_blocks(guard, tmp_path):
    """عطلُ production المقيس: ``sahool-raster`` لا وجود له في v9 ولا image/build."""
    root = _tree(
        tmp_path,
        {
            "docker-compose.v9.yml": _BASE,
            "docker-compose.production.yml": (
                "services:\n"
                "  pre: {image: busybox}\n"
                "  sahool-raster:\n"
                "    depends_on: {pre: {condition: service_completed_successfully}}\n"
                "  sahool-auth:\n"
                "    depends_on: [ghost]\n"
            ),
            "ci.yml": "docker-compose.production.yml",
        },
    )
    problems = guard.audit(
        root,
        tracked=["docker-compose.v9.yml", "docker-compose.production.yml"],
        roster=_roster(
            {"docker-compose.production.yml": {"role": "overlay", "consumers": ["ci.yml"]}}
        ),
    )
    assert any("sahool-raster —" in p and "image/build" in p for p in problems), problems
    assert any("depends_on ghost" in p for p in problems), problems
    assert not any(":: pre" in p for p in problems), problems


def test_an_entry_without_a_consumer_naming_it_blocks(guard, tmp_path):
    root = _tree(
        tmp_path,
        {
            "docker-compose.v9.yml": _BASE,
            "docker-compose.test.yml": "services:\n  test-redis: {image: redis}\n",
            "runner.sh": "docker compose -f something-else.yml up",
        },
    )
    tracked = ["docker-compose.v9.yml", "docker-compose.test.yml"]
    silent = guard.audit(
        root,
        tracked=tracked,
        roster=_roster({"docker-compose.test.yml": {"role": "test_stack", "consumers": []}}),
    )
    assert any("بلا مستهلِك" in p for p in silent), silent
    unnamed = guard.audit(
        root,
        tracked=tracked,
        roster=_roster(
            {"docker-compose.test.yml": {"role": "test_stack", "consumers": ["runner.sh"]}}
        ),
    )
    assert any("لا يُسمّي docker-compose.test.yml" in p for p in unnamed), unnamed


def test_a_test_stack_reusing_a_base_service_name_blocks(guard, tmp_path):
    """اسمٌ من v9 في مكدّسٍ آخر تعريفٌ ثانٍ — صنفُ ``auth-service``/``sahool-auth``."""
    root = _tree(
        tmp_path,
        {
            "docker-compose.v9.yml": _BASE,
            "docker-compose.test.yml": "services:\n  sahool-auth: {image: other}\n",
            "ci.yml": "docker-compose.test.yml",
        },
    )
    problems = guard.audit(
        root,
        tracked=["docker-compose.v9.yml", "docker-compose.test.yml"],
        roster=_roster(
            {"docker-compose.test.yml": {"role": "test_stack", "consumers": ["ci.yml"]}}
        ),
    )
    assert any("sahool-auth" in p and "تعريفٌ ثانٍ" in p for p in problems), problems


def test_a_companion_must_join_a_base_network(guard, tmp_path):
    def run(networks: str) -> list[str]:
        root = _tree(
            tmp_path,
            {
                "docker-compose.v9.yml": _BASE,
                "docker-compose.erp.yml": "services:\n  erp: {image: e}\n" + networks,
                "env": "docker-compose.erp.yml",
            },
        )
        return guard.audit(
            root,
            tracked=["docker-compose.v9.yml", "docker-compose.erp.yml"],
            roster=_roster({"docker-compose.erp.yml": {"role": "companion", "consumers": ["env"]}}),
        )

    assert any("لا ينضمّ" in p for p in run("networks:\n  own: {}\n"))
    joined = "networks:\n  n: {external: true, name: proj_sahool-internal}\n"
    assert run(joined) == []
