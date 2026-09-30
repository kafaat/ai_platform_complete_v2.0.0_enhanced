"""مُخطِّطُ بناء ملفّات Dockerfile التي يبنيها Railway في الـPR.

DOCKER-BUILD-VERIFIED-ONLY-ON-MANUAL-DISPATCH-SKIP-READS-GREEN-01: البناءُ يُختار حين يتغيّر
الـDockerfile **أو ما ينسخه** — والسياقُ مُشتقٌّ من أسطر COPY لا قائمةً تُصان بيد.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "railway_dockerfile_pr_build_plan", ROOT / "scripts/ci/railway_dockerfile_pr_build_plan.py"
)
planner = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(planner)


def _services(changed: list[str]) -> list[str]:
    return [b["service"] for b in planner.plan(changed, ROOT)["builds"]]


def test_every_railway_dockerfile_exists() -> None:
    """مُدخلٌ لا يُطابق ملفّاً كان سيُسقِط البناءَ الذي وُجد المُخطِّط لأجله — بصمت."""
    missing = [p for p in planner.RAILWAY_DOCKERFILES.values() if not (ROOT / p).exists()]
    assert missing == []


def test_a_file_the_image_copies_selects_its_build_even_if_the_dockerfile_is_unchanged() -> None:
    """الـDockerfile وحده كان سيُفوِّت ما يكسر البناء فعلاً: ملفٌّ يُنسَخ داخل الصورة."""
    assert _services(["services/raster-service/routers/tiles.py"]) == ["sahool-raster-service"]
    assert _services(["agents/base_agent.py"]) == ["sahool-notification-agent"]
    assert _services(["deploy/railway/render_frontend.py"]) == ["sahool-frontend"]


def test_shared_code_selects_every_image_that_copies_it() -> None:
    selected = set(_services(["shared/security/trusted_tenant.py"]))
    assert {"sahool-platform", "sahool-raster-service", "sahool-auth-main"} <= selected
    assert "sahool-frontend" not in selected
    assert "sahool-migrate-main" not in selected


def test_a_change_outside_every_build_context_builds_nothing() -> None:
    """لا كلَّ PR: الدماغُ وملفّاتُ compose والاختباراتُ لا تُنسَخ في أيّ صورة."""
    assert _services(["sahool-brain/log.md", "docker-compose.v9.yml", "tests_v9/test_x.py"]) == []


def test_a_file_in_the_service_directory_that_is_not_copied_builds_nothing() -> None:
    """vegetation ينسخ ملفّاتٍ بأسمائها: README بجوارها لا يدخل الصورة."""
    assert _services(["services/vegetation-analysis-service/README.md"]) == []
    assert _services(["services/vegetation-analysis-service/anomaly_engine.py"]) == [
        "sahool-vegetation-analysis"
    ]


def test_copy_parsing_skips_other_stages_and_flags() -> None:
    text = (
        "FROM node AS builder\n"
        "COPY --chown=1000:1000 frontend/ /src/\n"
        "COPY --from=builder /src/dist /usr/share/nginx/html\n"
        'COPY ["a b.txt", "c/", "/dst/"]\n'
        "ADD ./migrations/ /migrations/\n"
    )
    assert planner.copy_sources(text) == ["frontend", "a b.txt", "c", "migrations"]


def test_a_forced_build_is_planned_without_any_change() -> None:
    """التشغيلُ اليدويّ يُثبت البناءَ نفسه — حين لا يمسّ الـPR سياقاً فلا شيءَ آخر يُثبته."""
    builds = planner.plan([], ROOT, force=["sahool-migrate-main"])["builds"]
    assert [(b["service"], b["reasons"]) for b in builds] == [
        ("sahool-migrate-main", ["forced:sahool-migrate-main"])
    ]
    with pytest.raises(ValueError):
        planner.plan([], ROOT, force=["no-such-service"])


def test_changing_the_verifier_rebuilds_everything_it_verifies() -> None:
    """الـPR الذي يُضيف المُتحقِّق أو يكسره كان سيبني صفراً ويُقرأ أخضر."""
    for verifier in planner.VERIFIER_PATHS:
        assert set(_services([verifier])) == set(planner.RAILWAY_DOCKERFILES)


def test_a_pr_touching_a_railway_dockerfile_never_yields_an_empty_plan() -> None:
    """«نُفِّذت الخطّة» لا يكفي: PR يمسّ Dockerfile وخطّتُه فارغة خطأٌ يجب أن يُحمِّر."""
    for service, dockerfile in planner.RAILWAY_DOCKERFILES.items():
        result = planner.plan([dockerfile], ROOT)
        assert service in {b["service"] for b in result["builds"]}, dockerfile
        planner.assert_plan_covers_touched_dockerfiles([dockerfile], result)


def test_a_broken_matcher_is_caught_instead_of_reading_green(monkeypatch, tmp_path) -> None:
    """الفالسيفير: أفسِد المطابقة فتصير الخطّةُ فارغة — والفحصُ المستقلّ يُحمِّر، والـmain يخرج 1."""
    changed = ["services/raster-service/Dockerfile"]
    with pytest.raises(planner.PlanMissedATouchedDockerfile):
        planner.assert_plan_covers_touched_dockerfiles(changed, {"builds": []})

    monkeypatch.setattr(planner, "plan", lambda *_a, **_k: {"builds": []})
    monkeypatch.setattr(planner, "changed_against", lambda *_a, **_k: changed)
    assert planner.main(["--github-output", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists(), "لا تُكتب مصفوفةٌ فارغة لخطّةٍ فوّتت ما يمسّه الـPR"
