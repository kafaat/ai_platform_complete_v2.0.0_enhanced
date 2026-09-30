"""An overlay is only valid as the merge it is deployed as — never by its filename.

PRODUCTION-OVERLAY-NAMES-SERVICES-ABSENT-FROM-BASE-01. ``docker-compose.production.yml``
attached ``depends_on: production-preflight`` to ``vegetation-analysis-service`` and
``sahool-raster``. The base (``docker-compose.v9.yml``) names them
``sahool-vegetation-analysis`` and ``sahool-raster-service``. Compose merges by service
name, so each misspelt key became a *new* service with no image and no build. Measured on
b0c14b6d with Docker Compose v5.1.1, the file's own canonical production command::

    docker compose -f docker-compose.v9.yml -f docker-compose.production.yml config
    service "sahool-raster" has neither an image nor a build context specified:
    invalid compose project

(and, with only that one fixed, the same error for ``vegetation-analysis-service``).

OVERLAY-VALIDATION-SKIPPED-BY-FILENAME-LIST-01. Nothing caught it because the
*Validate Docker Compose* step skipped seven files by a filename list
("fragment/overlay"), so the production overlay was never rendered on its base. The
step now renders every file as it is deployed: an overlay by the ``docker compose -f
<base> -f <itself> … up`` line in its own header, anything else standalone.

Two properties are pinned here, both without Docker:

1. Every service an overlay touches exists in its base or brings its own image/build
   (a static model of the merge — the rename's regression goes red here).
2. The CI step's render plan merges the production overlay onto v9, excludes nothing
   except a verified non-document fragment, and no compose filename is special-cased
   in shell around it (restoring the skip goes red here).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PRODUCTION = "docker-compose.production.yml"
BASE = "docker-compose.v9.yml"

# Independent of the workflow's own parser on purpose: the header line an overlay
# carries to say which base it is deployed on.
_USAGE = re.compile(
    r"^#.*?\bdocker compose((?:\s+(?:-f|--profile)\s+\S+)+)\s+(?:up|config)\b", re.M
)
_COMPOSE_NAME = re.compile(r"docker-compose[\w.-]*\.yml")


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8")) or {}


def _declared_merge(name: str) -> list[str] | None:
    match = _USAGE.search((ROOT / name).read_text(encoding="utf-8"))
    if match is None:
        return None
    args = match.group(1).split()
    return [args[i + 1] for i in range(0, len(args), 2) if args[i] == "-f"]


def _overlays() -> dict[str, list[str]]:
    found = {}
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        files = _declared_merge(path.name)
        if files and len(files) > 1 and files[-1] == path.name:
            found[path.name] = files[:-1]
    return found


def _orphans(overlay: str, bases: list[str]) -> list[str]:
    known: set[str] = set()
    for base in bases:
        known |= set(_load(base).get("services") or {})
    orphans = []
    for name, spec in (_load(overlay).get("services") or {}).items():
        spec = spec or {}
        if name not in known and "image" not in spec and "build" not in spec:
            orphans.append(name)
    return orphans


# ── 1. the merge, modelled statically ───────────────────────────────────────────


def test_production_overlay_declares_its_v9_merge():
    assert _declared_merge(PRODUCTION) == [BASE, PRODUCTION], (
        f"{PRODUCTION} must carry its canonical command "
        f"`docker compose -f {BASE} -f {PRODUCTION} up -d` — CI renders exactly that"
    )


def test_production_overlay_names_only_services_the_base_defines():
    orphans = _orphans(PRODUCTION, [BASE])
    assert not orphans, (
        f"{PRODUCTION} names services absent from {BASE} without image/build; Compose "
        f"adds each as a new, unbuildable service and the production command fails: {orphans}"
    )
    services = _load(PRODUCTION)["services"]
    gated = {
        n
        for n, s in services.items()
        if "production-preflight" in ((s or {}).get("depends_on") or {})
    }
    assert {
        "sahool-vegetation-analysis",
        "sahool-raster-service",
        "sahool-field-management",
    } <= gated


@pytest.mark.parametrize("overlay", sorted(_overlays()))
def test_every_declared_overlay_touches_only_services_its_base_defines(overlay):
    bases = _overlays()[overlay]
    orphans = _orphans(overlay, bases)
    assert not orphans, (
        f"{overlay} over {bases}: services with no base and no image/build: {orphans}"
    )


def test_the_overlay_inventory_is_not_empty():
    # fail-closed: a header regex that matches nothing would make the parametrized
    # test above collect zero cases and pass on silence.
    assert PRODUCTION in _overlays()


# ── 2. the CI step renders what is deployed ─────────────────────────────────────


def _render_step() -> tuple[str, str]:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    steps = jobs["compose-validate"]["steps"]
    runs = [s.get("run", "") for s in steps if "docker compose" in s.get("run", "")]
    assert len(runs) == 1, "compose-validate must have exactly one step that invokes docker compose"
    run = runs[0]
    match = re.search(r"<<'EOF'\n(.*?)\nEOF\b", run, re.S)
    assert match, "the render step must be one embedded Python program"
    return run, match.group(1)


def _render_program(monkeypatch) -> dict:
    _, program = _render_step()
    namespace: dict = {"__name__": "compose_render_step"}
    monkeypatch.chdir(ROOT)
    exec(compile(program, "ci.yml:compose-validate", "exec"), namespace)  # noqa: S102 — our own workflow
    assert "render_plan" in namespace, "the render step must derive a render plan, not a skip list"
    return namespace


def test_ci_renders_the_production_overlay_merged_onto_v9(monkeypatch):
    namespace = _render_program(monkeypatch)
    plan = namespace["render_plan"]()
    assert PRODUCTION in plan, f"CI no longer renders {PRODUCTION}"
    args = plan[PRODUCTION]
    files = [args[i + 1] for i in range(0, len(args), 2) if args[i] == "-f"]
    assert files == [BASE, PRODUCTION], f"{PRODUCTION} must be rendered on {BASE}, got {args}"


def test_ci_excludes_nothing_but_verified_fragments(monkeypatch):
    namespace = _render_program(monkeypatch)
    plan = namespace["render_plan"]()
    excluded = namespace["NOT_A_COMPOSE_DOCUMENT"]
    every = {p.name for p in ROOT.glob("docker-compose*.yml")}
    assert every == set(plan) | set(excluded), (
        f"silently unrendered: {sorted(every - set(plan) - set(excluded))}"
    )
    for name in excluded:
        document = _load(name)
        assert "services" not in document, (
            f"{name} is a compose document — render it, do not exclude it"
        )


def test_no_compose_file_is_special_cased_outside_the_render_plan():
    run, program = _render_step()
    shell = run.replace(program, "")
    named = sorted(set(_COMPOSE_NAME.findall(shell)))
    assert not named, f"compose files special-cased in shell around the render plan: {named}"


def test_ci_fails_a_render_that_has_a_service_with_neither_image_nor_build(monkeypatch):
    check = _render_program(monkeypatch)["services_without_image_or_build"]
    rendered = {
        "services": {
            "a": {"image": "x"},
            "b": {"build": {"context": "."}},
            "sahool-raster": {"depends_on": {}},
        }
    }
    assert check(rendered) == ["sahool-raster"]
