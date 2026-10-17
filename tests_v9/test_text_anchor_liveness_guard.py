"""TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01 — an anchor must hold on live code.

#824 (``fc88d494``) measured two text guards passing for the wrong reason: an anchor on a
dead ``lazy(() => import(...))`` line in ``App.tsx`` while the property lived in
``FieldWorkspaceRouteShell.tsx``, and a regex that required ``(poly as any)`` verbatim.
The fixtures below are the **verbatim pre-#824 text** (``fc88d494^``), embedded rather than
read from history: a test that needs a SHA in the clone is skipped in CI's depth-1
checkout, and a skipped witness proves nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "text_anchor_liveness_guard", ROOT / "scripts/ci/text_anchor_liveness_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules[_SPEC.name] = guard  # dataclasses resolve their module by name
_SPEC.loader.exec_module(guard)

# fc88d494^:frontend/src/App.tsx lines 7, 114-115, 323 — verbatim.
_APP_PRE_824 = """\
import { useState, useEffect, Suspense, lazy, useCallback } from 'react';
const FieldWorkspaceMapCard = lazy(() => import('./sections/FieldWorkspaceMapCard'));
const FieldWorkspaceRouteShell = lazy(() => import('./sections/FieldWorkspaceRouteShell'));
function Router() {
  switch (page) {
      case 'field-workspace': return <FieldWorkspaceRouteShell />;
  }
  return <Suspense fallback={null}>{useState(useEffect(useCallback))}</Suspense>;
}
"""

# fc88d494^:services/sahool-platform/tests/test_ui14_field_workspace_route_shell_guard.py
_UI14_PRE_824 = """\
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_routes_dynamic_field_workspace_without_breaking_compat_page():
    app = read(FRONTEND / "App.tsx")
    assert "FieldWorkspaceRouteShell" in app
    # Compatibility card remains imported because the route shell reuses it rather than rewriting map behavior.
    assert "./sections/FieldWorkspaceMapCard" in app
"""

# fc88d494^:frontend/src/components/maphub/DrawingTools.static.test.ts lines 1-10, 54-58.
_DRAWING_PRE_824 = """\
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const addField = readFileSync(join(root, 'src/components/AddFieldWithMap.tsx'), 'utf8');

describe('Pivot circle — move/resize handles, not 24 vertex markers', () => {
  it('disables leaflet-draw vertex editing for pivot (only center + radius handles)', () => {
    expect(addField).toContain('const isPivot = pivotEditRef.current !== null;');
    expect(addField).toMatch(/if \\(!isPivot\\) \\(poly as any\\)\\.editing\\?\\.enable\\(\\)/);
  });
});
"""


def _ui14_tree(tmp_path: Path, app: str, test: str = _UI14_PRE_824) -> Path:
    test_path = tmp_path / "services/sahool-platform/tests/test_ui14_guard.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(test, encoding="utf-8")
    sections = tmp_path / "frontend/src/sections"
    sections.mkdir(parents=True)
    (tmp_path / "frontend/src/App.tsx").write_text(app, encoding="utf-8")
    return test_path


def _findings(anchors) -> list[str]:
    return guard.findings(list(anchors))


# ── the two #824 witnesses ────────────────────────────────────────────────────


def test_the_app_tsx_dead_lazy_anchor_of_824_is_caught(tmp_path: Path) -> None:
    test = _ui14_tree(tmp_path, _APP_PRE_824)
    anchors = list(guard.python_anchors(test))
    assert {a.text for a in anchors} == {
        "FieldWorkspaceRouteShell",
        "./sections/FieldWorkspaceMapCard",
    }
    found = _findings(anchors)
    assert len(found) == 1, found
    assert "dead_binding" in found[0] and "FieldWorkspaceMapCard" in found[0]


def test_the_poly_as_any_anchor_of_824_is_caught() -> None:
    test = ROOT / "frontend/src/components/maphub/DrawingTools.static.test.ts"
    anchors = [
        a for a in guard.frontend_anchors_from_text(test, _DRAWING_PRE_824) if "poly" in a.text
    ]
    assert len(anchors) == 1 and anchors[0].regex
    assert anchors[0].target == ROOT / "frontend/src/components/AddFieldWithMap.tsx"
    found = _findings(anchors)
    assert len(found) == 1 and "mandated_escape" in found[0] and "as any" in found[0]


# ── the legitimate remedies pass ──────────────────────────────────────────────


def test_the_post_824_anchor_where_the_property_lives_passes(tmp_path: Path) -> None:
    """Anchor in the shell, where the card is imported **and rendered**."""
    test = _ui14_tree(tmp_path, _APP_PRE_824.replace(_APP_PRE_824.splitlines()[1] + "\n", ""))
    shell = tmp_path / "frontend/src/sections/FieldWorkspaceRouteShell.tsx"
    shell.write_text(
        "import FieldWorkspaceMapCard from './FieldWorkspaceMapCard';\n"
        "export default function Shell() { return <FieldWorkspaceMapCard />; }\n",
        encoding="utf-8",
    )
    test.write_text(
        _UI14_PRE_824.replace(
            '    assert "./sections/FieldWorkspaceMapCard" in app\n',
            '    shell = read(FRONTEND / "sections" / "FieldWorkspaceRouteShell.tsx")\n'
            "    assert \"from './FieldWorkspaceMapCard'\" in shell\n",
        ),
        encoding="utf-8",
    )
    anchors = list(guard.python_anchors(test))
    assert "from './FieldWorkspaceMapCard'" in {a.text for a in anchors}
    assert _findings(anchors) == []


def test_an_anchor_on_a_live_lazy_binding_passes(tmp_path: Path) -> None:
    """``FieldWorkspaceRouteShell`` is lazy-imported **and** rendered: not dead."""
    test = _ui14_tree(tmp_path, _APP_PRE_824)
    test.write_text(
        _UI14_PRE_824.replace(
            "./sections/FieldWorkspaceMapCard", "./sections/FieldWorkspaceRouteShell"
        ),
        encoding="utf-8",
    )
    assert _findings(guard.python_anchors(test)) == []


def test_the_post_824_property_regex_passes() -> None:
    test = ROOT / "frontend/src/components/maphub/DrawingTools.static.test.ts"
    fixed = _DRAWING_PRE_824.replace(
        "/if \\(!isPivot\\) \\(poly as any\\)\\.editing\\?\\.enable\\(\\)/",
        "/if \\(!isPivot\\)\\s*\\w+\\.editing\\?\\.enable\\(\\)/",
    )
    anchors = list(guard.frontend_anchors_from_text(test, fixed))
    assert len(anchors) == 2
    assert _findings(anchors) == []


def test_a_side_effect_import_is_live_by_construction(tmp_path: Path) -> None:
    test = _ui14_tree(tmp_path, "import 'leaflet-draw';\n")
    test.write_text(
        _UI14_PRE_824.replace("./sections/FieldWorkspaceMapCard", "leaflet-draw"),
        encoding="utf-8",
    )
    assert _findings(guard.python_anchors(test)) == []


# ── the shapes ────────────────────────────────────────────────────────────────


def test_a_python_from_import_whose_name_is_unused_is_dead(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("from shared.auth import verify_token\n\nX = 1\n", encoding="utf-8")
    anchor = guard.Anchor("t.py", 1, "from shared.auth import verify_token", target)
    assert "dead_binding" in _findings([anchor])[0]
    target.write_text(
        "from shared.auth import verify_token\n\nX = verify_token('t')\n", encoding="utf-8"
    )
    guard._SPANS.clear()
    assert _findings([anchor]) == []


@pytest.mark.parametrize("escape", guard.ESCAPES)
def test_every_mandated_escape_is_caught(tmp_path: Path, escape: str) -> None:
    anchor = guard.Anchor("t.py", 1, f"x {escape} y", tmp_path / "absent.py")
    assert "mandated_escape" in _findings([anchor])[0]


def test_a_negative_anchor_is_a_prohibition_not_an_anchor(tmp_path: Path) -> None:
    test = _ui14_tree(tmp_path, _APP_PRE_824)
    test.write_text(
        _UI14_PRE_824.replace(
            'assert "./sections/FieldWorkspaceMapCard" in app',
            'assert "x as any" not in app, "the cast was narrowed in #824"',
        ),
        encoding="utf-8",
    )
    assert {a.text for a in guard.python_anchors(test)} == {"FieldWorkspaceRouteShell"}


def test_an_unresolvable_read_yields_no_anchor(tmp_path: Path) -> None:
    test = tmp_path / "test_dynamic.py"
    test.write_text(
        "import os\n\ndef test_x():\n"
        "    text = open(os.environ['P']).read()\n"
        "    assert 'x as any' in text\n",
        encoding="utf-8",
    )
    assert list(guard.python_anchors(test)) == []


# ── the live tree ─────────────────────────────────────────────────────────────


def test_the_live_tree_has_no_dead_or_escape_anchor() -> None:
    anchors = guard.collect_anchors()
    assert len(anchors) > 1000, f"only {len(anchors)} anchors resolved — the resolver regressed"
    assert guard.findings(anchors) == []
