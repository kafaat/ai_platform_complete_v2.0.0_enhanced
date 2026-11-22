import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """Drop // and /* */ comments outside string literals."""
    out, i, quote = [], 0, None
    while i < len(source):
        ch = source[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(source):
                out.append(source[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
        elif source.startswith("//", i):
            i = source.find("\n", i)
            i = len(source) if i < 0 else i
            continue
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def handler_calls(source: str, prop: str) -> list[str]:
    """The statements an inline JSX arrow handler runs: `prop={() => { a(); b(); }}`.

    The handler is parsed by brace matching, so it may span lines, and comments are
    removed first: a call that only appears in a comment, or on the same line outside
    the handler, does not count.
    """
    code = _strip_comments(source)
    matches = list(re.finditer(rf"(?<![\w$]){re.escape(prop)}=\{{", code))
    assert len(matches) == 1, (
        f"{prop} must appear exactly once in the given source, found {len(matches)}"
    )
    i, depth = matches[0].end() - 1, 0
    for j in range(i, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                expression = code[i + 1 : j]
                break
    else:
        raise AssertionError(f"unterminated {prop} handler")
    arrow = expression.split("=>", 1)
    assert len(arrow) == 2, f"{prop} is not an inline arrow handler"
    body = arrow[1].strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    statements, current, quote, depth = [], [], None, 0
    for ch in body:  # split on top-level `;`, outside strings and nested calls
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            statements.append("".join(current))
            current = []
            continue
        current.append(ch)
    statements.append("".join(current))
    return [" ".join(s.split()) for s in statements if s.strip()]


def test_ui11_field_drawer_shell_wraps_existing_drawer_without_moving_behavior():
    shell = read("sections/maphub/FieldDrawerShell.tsx")
    assert "export function FieldDrawerShell" in shell
    assert 'data-testid="maphub-field-drawer-shell"' in shell
    assert 'data-sahool-region="field-drawer"' in shell
    assert "data-field-id" in shell
    assert "data-open" in shell
    maphub = read("sections/MapHub.tsx")
    assert "import { FieldDrawerShell } from './maphub/FieldDrawerShell';" in maphub
    assert "<FieldDrawerShell fieldId={fieldId} open={detailOpen}>" in maphub
    assert "<FieldDetailDrawer" in maphub
    assert "</FieldDrawerShell>" in maphub


def test_ui11_field_timeline_shell_wraps_imagery_timeline_and_exposes_season_context():
    shell = read("sections/maphub/FieldTimelineShell.tsx")
    assert "export function FieldTimelineShell" in shell
    assert "FieldTimelineKind" in shell
    for kind in ["imagery", "operations", "learning"]:
        assert kind in shell
    assert 'data-testid="maphub-field-timeline-shell"' in shell
    assert 'data-sahool-region="season-timeline"' in shell
    assert "data-season-id" in shell
    maphub = read("sections/MapHub.tsx")
    assert "import { FieldTimelineShell } from './maphub/FieldTimelineShell';" in maphub
    assert "<FieldTimelineShell" in maphub
    assert 'kind="imagery"' in maphub
    assert "activeSeasonId={activeSeasonId}" in maphub
    assert 'data-testid="two-year-imagery-timeline"' in maphub


def test_ui12_action_from_map_palette_exists_and_does_not_fake_writes():
    palette = read("sections/maphub/MapActionPalette.tsx")
    assert "export function MapActionPalette" in palette
    assert 'data-testid="maphub-action-from-map-palette"' in palette
    assert 'data-sahool-region="action-from-map"' in palette
    for prop in ["onPinScouting", "onOpenTimeline", "onOpenAlerts", "onAddField"]:
        assert prop in palette
    assert "disabled={!canMutate || !fieldReady}" in palette
    assert "fake" not in palette.lower()
    maphub = read("sections/MapHub.tsx")
    assert "import { MapActionPalette } from './maphub/MapActionPalette';" in maphub
    assert "<MapActionPalette" in maphub
    # The palette's pin action must open a surface that accepts pins: compare/3D maps do not,
    # so it also returns to the 2D single map (UI audit, MapHub palette pin finding).
    # The palette element only: the field drawer has its own onOpenTimeline.
    palette_jsx = maphub[maphub.index("<MapActionPalette") :]
    palette_jsx = palette_jsx[: palette_jsx.index("/>") + 2]
    pin_calls = handler_calls(palette_jsx, "onPinScouting")
    for call in ("setPinMode(true)", "setDrawTools(false)", "setMode('2d')", "setCompare(false)"):
        assert call in pin_calls, call
    timeline_calls = handler_calls(palette_jsx, "onOpenTimeline")
    for call in ("setSettingsOpen(true)", "setShowImageryTimeline(true)"):
        assert call in timeline_calls, call
    assert "onOpenAlerts={() => setShowAlerts(true)}" in maphub
    # The palette's add-field action opens the plain dialog: it must also clear a tool
    # preselected by the toolbar's circle-field button, or the dialog would reopen on it.
    add_calls = handler_calls(palette_jsx, "onAddField")
    for call in ("setShowAddField(true)", "setAddFieldTool(null)"):
        assert call in add_calls, call


def test_handler_calls_reads_the_handler_not_its_line():
    """The #1563 review nit: a same-line comment or neighbour must not satisfy the guard."""
    source = (
        "<P onAddField={() => { setAddFieldTool(null); }} /> // setShowAddField(true)\n"
        "<Q onPin={() => setMode('2d')} other={() => setPinMode(true)} />\n"
        "<R onMulti={() => {\n  /* setX(1); */ setY(2);\n  setZ('a;b');\n}} />\n"
    )
    assert handler_calls(source, "onAddField") == ["setAddFieldTool(null)"]
    assert handler_calls(source, "onPin") == ["setMode('2d')"]
    assert handler_calls(source, "onMulti") == ["setY(2)", "setZ('a;b')"]
    # A longer prop that ends with the name is not a match, and a duplicate is refused.
    assert handler_calls("<A xonAdd={() => wrong()} onAdd={() => right()} />", "onAdd") == [
        "right()"
    ]
    try:
        handler_calls("<A onAdd={() => a()} /><B onAdd={() => b()} />", "onAdd")
    except AssertionError:
        pass
    else:
        raise AssertionError("a prop that appears twice must be refused")


def test_ui13_role_aware_map_surface_contract_is_explicit():
    contract = read("sections/maphub/roleUiContract.ts")
    assert "export type SahoolUiRole" in contract
    assert "export type RoleUiCapability" in contract
    assert "roleCan" in contract
    assert "roleUiMode" in contract
    for capability in [
        "create_field",
        "mutate_field",
        "create_scouting_pin",
        "run_backfill",
        "delete_field",
    ]:
        assert capability in contract
    surface = read("sections/maphub/RoleAwareMapSurface.tsx")
    assert "export function RoleAwareMapSurface" in surface
    assert 'data-testid="maphub-role-aware-surface"' in surface
    assert 'data-sahool-region="role-aware-map-surface"' in surface
    assert "data-role-mode" in surface
    assert "data-can-create-field" in surface
    maphub = read("sections/MapHub.tsx")
    assert "import { RoleAwareMapSurface } from './maphub/RoleAwareMapSurface';" in maphub
    assert "<RoleAwareMapSurface role={user?.role}>" in maphub
    assert "</RoleAwareMapSurface>" in maphub
