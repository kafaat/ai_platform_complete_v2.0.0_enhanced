"""T3 (تدقيق 2026-11-01): المنح الشامل لا يُعيد دوالّ DEFINER لمستوى تحكّم الإدخال إلى sahool_app.

``GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_role`` في سكربتَي bootstrap كان يُعيد EXECUTE
على الدوالّ التي يملكها ``sahool_ingest_resolver`` (BYPASSRLS) والتي سحبتها v198/v199 من PUBLIC.
مقيس على PG 16 مبنيّة من MANIFEST: ``sahool_app`` بسياق المستأجر A استدعى
``claim_submissions_for_projection`` فأعاد ``normalized_payload`` للمستأجر B وسرق قفل معالجته.

العقد (بلا قاعدة): في كتلة تهيئة دور التطبيق، وبعد المنح الشامل، يُسحَب EXECUTE من app_role على
**كلّ** دالّة يُنقَل ملكها إلى ``sahool_ingest_resolver`` في السكربت نفسه — مشتقّةً من أوامر
``ALTER FUNCTION … OWNER TO sahool_ingest_resolver`` لا من قائمة منسوخة. البرهان التنفيذيّ الحيّ
في ``test_role_bootstrap_executable.py`` (integration).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = (
    _ROOT / "migrations" / "apply_in_compose.sh",
    _ROOT / "migrations" / "bootstrap_postgres.sh",
)
_BLANKET = 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :"app_role";'
_OWNER_RE = re.compile(r"ALTER FUNCTION (\w+)\([^)]*\) OWNER TO sahool_ingest_resolver")


def _app_role_heredoc(text: str) -> str:
    for m in re.finditer(r"<<'SQL'\n(.*?)\nSQL\b", text, re.DOTALL):
        body = m.group(1)
        if "CREATE ROLE" in body and "app_role" in body:
            return body
    raise AssertionError("app-role bootstrap heredoc not found")


def _revoked_after_blanket(body: str) -> set[str]:
    idx = body.find(_BLANKET)
    assert idx >= 0, "blanket EXECUTE grant to app_role not found (contract moved?)"
    tail = body[idx + len(_BLANKET) :]
    revoked: set[str] = set()
    for m in re.finditer(
        r"SELECT format\('REVOKE EXECUTE ON FUNCTION %s FROM %I', (\w+)\.sig, :'app_role'\)"
        r"(.*?)\\gexec",
        tail,
        re.DOTALL,
    ):
        revoked |= set(re.findall(r"\('public\.(\w+)\([^)]*\)'\)", m.group(2)))
    return revoked


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.name)
def test_resolver_owned_definers_revoked_from_app_role_after_blanket_grant(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    resolver_owned = set(_OWNER_RE.findall(text))
    # المعروف اليوم (v198/v199) — يحمي الاشتقاق من أن يصير فارغاً صامتاً.
    assert {
        "resolve_ingest_source",
        "claim_submissions_for_projection",
        "complete_submission_projection",
    } <= resolver_owned
    revoked = _revoked_after_blanket(_app_role_heredoc(text))
    missing = sorted(resolver_owned - revoked)
    assert not missing, (
        f"{script.name}: EXECUTE re-granted to app_role on BYPASSRLS-owned DEFINER functions "
        f"{missing} — REVOKE them after the blanket grant (T3)"
    )


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.name)
def test_ingest_role_keeps_explicit_execute(script: Path) -> None:
    """السحب من app_role لا يمسّ المستدعي الشرعيّ الوحيد (sahool_ingest)."""
    text = script.read_text(encoding="utf-8")
    for fn in (
        "resolve_ingest_source(TEXT)",
        "claim_submissions_for_projection(INT, INT)",
        "complete_submission_projection(BIGINT, TEXT, TEXT)",
    ):
        assert f"GRANT EXECUTE ON FUNCTION {fn} TO sahool_ingest;" in text
