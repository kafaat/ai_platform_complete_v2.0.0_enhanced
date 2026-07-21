#!/usr/bin/env python3
"""حارس ملكيّة scout-ingest-service لجدول ``external_submissions`` (SCOUT-INGEST-01 / B1.2b).

**تصحيح قرار (ج):** حُرّاس المنصّة الأربعة رفضت مسار إدخال جديد على المنصّة، فاستُخرِج مدخل ODK
إلى خدمة مالكة مستقلّة على غرار السابقة #201 (field-management-service). هذا الحارس يُثبّت العقد
بحيث لا ينحدر لاحقاً إلى «أيّ خدمة تكتب في الجدول»:

  • **كاتب وحيد ورقيّاً:** ``db_ownership.yml`` يُسنِد external_submissions مالكاً وكاتباً وحيداً
    إلى scout-ingest-service (لا platform، لا مشترَك).
  • **كاتب وحيد بنيويّاً:** لا ``INSERT INTO external_submissions`` في أيّ مصدر خارج
    ``services/scout-ingest-service/`` (لا تكتبه المنصّة ولا أيّ خدمة أخرى).
  • **أقلّ منح:** دور ``sahool_ingest`` يُمنَح SELECT+INSERT فقط (لا UPDATE/DELETE) على الجدول
    في **كلا** مُهيّئَي الأدوار (bootstrap + apply_in_compose)، وهو NOBYPASSRLS.
  • **الخدمة fail-closed:** compose يوصلها بدور ``sahool_ingest`` المقيَّد (لا sahool_app/superuser)،
    خلف ``SCOUT_INGEST_ENABLED``؛ والخدمة لا تقبل ``SAHOOL_AGENT_TOKEN`` ولا JWT — اعتماد لكلّ مصدر.

فحص ساكن صرف — ``pytest -m unit`` (لا قاعدة/خدمات).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DB_OWNERSHIP = ROOT / "docs" / "architecture" / "db_ownership.yml"
SERVICE = "scout-ingest-service"
SVC_DIR = ROOT / "services" / SERVICE
COMPOSE = ROOT / "docker-compose.v9.yml"
BOOTSTRAP = ROOT / "migrations" / "bootstrap_postgres.sh"
APPLY = ROOT / "migrations" / "apply_in_compose.sh"


def _ownership_block(table: str) -> dict[str, str]:
    lines = DB_OWNERSHIP.read_text(encoding="utf-8").splitlines()
    block: dict[str, str] = {}
    current = None
    for raw in lines:
        m = re.match(r"^  ([A-Za-z_][\w]*):\s*$", raw)
        if m:
            current = m.group(1)
            continue
        fm = re.match(r"^    (owner|writers|readers):\s*(.*?)\s*$", raw)
        if current == table and fm:
            block[fm.group(1)] = fm.group(2)
    return block


def test_db_ownership_makes_scout_ingest_sole_writer_owner():
    block = _ownership_block("external_submissions")
    assert block.get("owner") == SERVICE, block
    assert block.get("writers") == f"[{SERVICE}]", block  # كاتب وحيد = المالك


def test_no_other_source_inserts_into_external_submissions():
    """لا كاتب لـexternal_submissions خارج الخدمة المالكة (المنصّة لا تكتبه)."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or "tests" in parts or path.name.startswith("test_"):
            continue
        if SVC_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"INSERT\s+INTO\s+external_submissions", text, re.I):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"external_submissions يُكتَب من خارج الخدمة المالكة (خرق ملكيّة الكاتب الوحيد): {offenders}"
    )


@pytest.mark.parametrize("runner", [BOOTSTRAP, APPLY])
def test_ingest_role_is_least_grant_no_update_delete(runner: Path):
    text = runner.read_text(encoding="utf-8")
    # المنح موجود على الجدول: SELECT + INSERT فقط.
    assert re.search(
        r"GRANT\s+SELECT,\s*INSERT\s+ON\s+external_submissions\s+TO\s+sahool_ingest", text
    ), f"{runner.name}: منح SELECT+INSERT لـsahool_ingest مفقود"
    # لا UPDATE/DELETE يُمنَح للدور على الجدول (تحديث الحالة لكاتب لاحق B1.3).
    assert not re.search(
        r"GRANT[^\n;]*\b(UPDATE|DELETE)\b[^\n;]*external_submissions[^\n;]*\bsahool_ingest\b(?!_)",
        text,
        re.I,
    ), f"{runner.name}: sahool_ingest لا يجوز منحه UPDATE/DELETE على external_submissions"
    # الدور NOBYPASSRLS (RLS يبقى فعّالاً).
    assert "NOBYPASSRLS" in text and "sahool_ingest" in text


def test_compose_wires_restricted_role_behind_flag():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-scout-ingest:" in text, "خدمة scout-ingest غير مُسجّلة في docker-compose.v9.yml"
    # كتلة الخدمة تصل بدور sahool_ingest المقيَّد (لا sahool_app/sahool_user).
    # الإرساء على سطر تعريف الخدمة (`\n  sahool-scout-ingest:\n`) لا على أيّ ظهور للنصّ —
    # وإلّا خطف URL مثل `http://sahool-scout-ingest:8000` (في كتلة المنصّة) موضعَ الكتلة.
    block = text.split("\n  sahool-scout-ingest:\n", 1)[1].split("\n  sahool-", 1)[0]
    assert "postgresql://sahool_ingest:" in block, "الخدمة لا تتّصل بدور sahool_ingest المقيَّد"
    assert "sahool_user" not in block and "sahool_app" not in block
    assert "SCOUT_INGEST_ENABLED" in block  # خلف راية التفعيل
    assert "service_completed_successfully" in block  # بعد اكتمال الهجرات
    # لا توكن مشترك مُهيّأ على الخدمة (تعليق يذكره لِنفيه مقبول؛ سطر بيئة يُهيّئه ممنوع).
    env_lines = [
        ln.strip()
        for ln in block.splitlines()
        if "SAHOOL_AGENT_TOKEN" in ln and not ln.strip().startswith("#")
    ]
    assert not env_lines, f"scout-ingest يجب ألّا يُهيّئ SAHOOL_AGENT_TOKEN: {env_lines}"


def test_service_is_fail_closed_per_source_credential():
    src = (SVC_DIR / "main.py").read_text(encoding="utf-8")
    # اعتماد لكلّ مصدر عبر resolve_ingest_source — لا توكن مشترك ولا JWT.
    assert "X-Scout-Ingest-Token" in src and "resolve_ingest_source" in src
    # لا يقرأ توكناً مشتركاً من البيئة (ذِكره في docstring لنفيه مقبول).
    assert 'getenv("SAHOOL_AGENT_TOKEN' not in src and "environ" not in src
    assert "jwt.decode(" not in src and "import jwt" not in src
    # بلا توكن ⇒ 401 · مصدر مجهول/معطَّل ⇒ 403 · خلف الراية ⇒ 404.
    assert "status_code=401" in src and "status_code=403" in src
    assert "SCOUT_INGEST_ENABLED" in src


# ═══════════════════════ B1.3 — نموذج الإسقاط المملوك ═══════════════════════
def test_field_observations_sole_writer_owner():
    """(أ): external_field_observations كاتبه/مالكه scout-ingest وحده — لا platform (لا scouting_pins)."""
    block = _ownership_block("external_field_observations")
    assert block.get("owner") == SERVICE, block
    assert block.get("writers") == f"[{SERVICE}]", block


@pytest.mark.parametrize("runner", [BOOTSTRAP, APPLY])
def test_ingest_role_least_grant_on_observations(runner: Path):
    """العامل يُدرِج فقط (SELECT+INSERT) — لا UPDATE/DELETE على نموذج القراءة (التحديث عبر DEFINER)."""
    text = runner.read_text(encoding="utf-8")
    assert re.search(
        r"GRANT\s+SELECT,\s*INSERT\s+ON\s+external_field_observations\s+TO\s+sahool_ingest", text
    ), f"{runner.name}: منح SELECT+INSERT على external_field_observations مفقود"
    assert not re.search(
        r"GRANT[^\n;]*\b(UPDATE|DELETE)\b[^\n;]*external_field_observations[^\n;]*sahool_ingest",
        text,
        re.I,
    ), f"{runner.name}: لا UPDATE/DELETE لـsahool_ingest على external_field_observations"


@pytest.mark.parametrize("runner", [BOOTSTRAP, APPLY])
def test_projection_status_updated_only_via_definer(runner: Path):
    """least-grant محفوظ: تحديث projection_status عبر دالّتَي DEFINER (يملكهما resolver) لا UPDATE مباشر."""
    text = runner.read_text(encoding="utf-8")
    assert (
        "ALTER FUNCTION claim_submissions_for_projection(INT, INT) OWNER TO sahool_ingest_resolver"
        in text
    )
    assert (
        "ALTER FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) OWNER TO sahool_ingest_resolver"
        in text
    )
    # sahool_ingest يبقى بلا UPDATE على external_submissions (الحارس الأصليّ) — يُنفَّذ التحديث كـresolver.
    assert not re.search(
        r"GRANT[^\n;]*\bUPDATE\b[^\n;]*external_submissions[^\n;]*sahool_ingest\b", text, re.I
    )


def test_read_channel_uses_dedicated_token_not_shared():
    """قناة القراءة توكن خدمة **مخصّص** (SCOUT_INGEST_READ_TOKEN) لا SAHOOL_AGENT_TOKEN المشترك."""
    src = (SVC_DIR / "main.py").read_text(encoding="utf-8")
    assert "/internal/scouting/external-observations" in src
    assert 'getenv("SCOUT_INGEST_READ_TOKEN' in src
    assert 'getenv("SAHOOL_AGENT_TOKEN' not in src
    # الجدول يُقرأ عبر المسار لا SQL مباشر من مستهلك خارجيّ (العقد مُعلَن هنا).
    assert "external_field_observations" in src


def test_projection_worker_projects_only_owned_model_not_platform_tables():
    """العامل يكتب نموذج scout-ingest المملوك فقط — لا يلمس scouting_pins/observations المملوكَين للمنصّة."""
    src = (SVC_DIR / "projection_worker.py").read_text(encoding="utf-8")
    assert "INSERT INTO external_field_observations" in src
    # لا كتابة SQL لجداول المنصّة (ذِكرها في docstring لِنفيها مقبول).
    assert "INSERT INTO scouting_pins" not in src and "UPDATE scouting_pins" not in src
    assert "INSERT INTO observations" not in src
    # المقبولة فقط تُسقَط (عبر دالّة claim) + idempotent (ON CONFLICT DO NOTHING).
    assert (
        "claim_submissions_for_projection" in src
        and "ON CONFLICT (observation_id) DO NOTHING" in src
    )
