"""Behavioral proof (real Postgres): the PRE-CUTOVER role-certification tool's VERDICT is correct.

``decision_sor_role_certify.py`` is the mandatory precursor to the DECISION-SOR REVOKE — an operator
runs it to confirm the platform and decision-service connect as DIFFERENT Postgres roles before any
REVOKE. A certification is only useful if its verdict is trustworthy, so this test proves the tool:

  * reports ``role_separation_confirmed = True`` and the two distinct current_users when the platform
    and decision-service connections use DIFFERENT login roles;
  * reports ``role_separation_confirmed = False`` when both connections resolve to the SAME role
    (the "do not REVOKE — it would break both services" signal);
  * surfaces the role attributes (``rolsuper`` / ``rolbypassrls`` false for a restricted role) and the
    table OWNER of each of the five SoR tables (owner keeps privileges even after REVOKE).

Runs in the Decision Service Tests job (superuser ``DATABASE_URL`` + migrations applied). Skipped
when DATABASE_URL is absent so local ``pytest`` without a DB stays green.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decision_sor_role_certify as csr  # noqa: E402

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")

PLATFORM_PROBE = "cert_platform_probe"
SERVICE_PROBE = "cert_service_probe"
PROBE_PASSWORD = "cert_probe_pw"
BRIDGE_A = "cert_bridge_a"
BRIDGE_B = "cert_bridge_b"
CHAIN_A = "cert_chain_a"
CHAIN_B = "cert_chain_b"
CHAIN_C = "cert_chain_c"


async def _admin():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _probe_url(role: str) -> str:
    p = urlparse(DB)
    db = (p.path or "/").lstrip("/") or "postgres"
    return f"postgresql://{role}:{PROBE_PASSWORD}@{p.hostname}:{p.port or 5432}/{db}"


async def _drop_probes(admin) -> None:
    # Membership targets must be dropped after memberships are revoked by DROP ROLE cascade rules.
    for role in (PLATFORM_PROBE, SERVICE_PROBE, BRIDGE_A, BRIDGE_B):
        if await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role):
            await admin.execute(f'DROP ROLE IF EXISTS "{role}"')


async def _create_probes(admin) -> None:
    await _drop_probes(admin)
    for role in (PLATFORM_PROBE, SERVICE_PROBE):
        await admin.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{PROBE_PASSWORD}' "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
        )
    for role in (BRIDGE_A, BRIDGE_B):
        await admin.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'
        )


def test_certification_verdict_is_correct() -> None:
    async def _run():
        admin = await _admin()
        try:
            await _create_probes(admin)
            platform_url = _probe_url(PLATFORM_PROBE)
            service_url = _probe_url(SERVICE_PROBE)

            # 1) Distinct roles → role_separation_confirmed True, correct current_users.
            os.environ["DECISION_SOR_PLATFORM_URL"] = platform_url
            os.environ["DECISION_SOR_SERVICE_URL"] = service_url
            distinct = await csr._run()
            assert distinct["role_separation_confirmed"] is True, distinct
            assert distinct["platform_role"] == PLATFORM_PROBE
            assert distinct["decision_service_role"] == SERVICE_PROBE
            assert distinct["platform"]["current_user"] == PLATFORM_PROBE
            assert distinct["decision_service"]["current_user"] == SERVICE_PROBE

            # Role attributes surfaced + restricted (the whole point of certifying the roles).
            attrs = distinct["platform"]["role_attributes"]
            assert attrs["rolsuper"] is False and attrs["rolbypassrls"] is False, attrs
            # The probe is not a member of any role it could SET ROLE into.
            assert distinct["platform"]["memberships_can_set_role_to"] == []
            assert distinct["platform"]["membership_closure"] == []
            assert distinct["cutover_preflight_safe"] is True
            assert distinct["classification"] == "PASSED"

            # Table owner reported for every SoR table (and it is NOT the probe app role).
            owners = distinct["platform"]["table_owners"]
            assert set(owners) == set(csr.SOR_TABLES)
            for table, owner in owners.items():
                assert owner and owner not in (PLATFORM_PROBE, SERVICE_PROBE), (table, owner)

            # security_definer_writers is enumerated (a list — empty is fine, presence is what matters).
            assert isinstance(distinct["platform"]["security_definer_writers"], list)

            # 2) Same role on both connections → role_separation_confirmed False (do NOT revoke).
            os.environ["DECISION_SOR_SERVICE_URL"] = platform_url
            same = await csr._run()
            assert same["role_separation_confirmed"] is False, same
            assert same["platform_role"] == same["decision_service_role"] == PLATFORM_PROBE
            assert same["cutover_preflight_safe"] is False

            # 3) A two-hop membership is visible in the closure and blocks cutover certification.
            await admin.execute(f'GRANT "{BRIDGE_B}" TO "{BRIDGE_A}"')
            await admin.execute(f'GRANT "{BRIDGE_A}" TO "{PLATFORM_PROBE}"')
            os.environ["DECISION_SOR_SERVICE_URL"] = service_url
            chained = await csr._run()
            roles = {row["role"] for row in chained["platform"]["membership_closure"]}
            assert {BRIDGE_A, BRIDGE_B} <= roles, chained["platform"]["membership_closure"]
            assert chained["cutover_preflight_safe"] is False
            assert "platform_role_membership_closure_must_be_empty" in chained["blockers"]
        finally:
            os.environ.pop("DECISION_SOR_PLATFORM_URL", None)
            os.environ.pop("DECISION_SOR_SERVICE_URL", None)
            await _drop_probes(admin)
            await admin.close()

    asyncio.run(_run())


def test_membership_closure_does_not_inherit_across_a_noinherit_middle_role() -> None:
    """A <- B <- C حيث **الوسط** ``B`` هو ``NOINHERIT`` — فهل تعبر الوراثة خلاله؟

    هذه الحالة تمسك أخطر خطأ ممكن في مسار ما قبل PostgreSQL 16: تطبيق ``rolinherit``
    على **الدور الخطأ** داخل الاجتياز العَوديّ. لو قُرِئت سمةُ الطرف (``A``) أو سمةُ
    الهدف (``C``) بدل سمة الوسط (``B``)، لبقيت ``inherit_option`` صادقةً على ``C``
    ولمرَّت السلسلة صامتةً — وهي بالضبط الحلقة التي يُفترَض أن يكشفها إغلاق العضويّة
    قبل أيّ REVOKE.

    والمرجع ليس رأياً: ``pg_has_role(...,'USAGE')`` تقيس الامتياز المتاح **تلقائيّاً**
    بالوراثة، و``'MEMBER'`` تقيس بلوغَ الدور عبر ``SET ROLE``. فالتأكيد يقارن مُخرَج
    الإغلاق بحقيقة الخادم نفسه لا بتوقّعٍ مكتوب يدويّاً.

    وتُفرَض الدلالتان منفصلتَين: انقطاعُ الوراثة عند ``B`` **لا** يقطع بلوغ ``C`` عبر
    ``SET ROLE`` — وخلطُهما كان سيُخفي مسار تصعيدٍ قائماً.
    """

    async def _run():
        admin = await _admin()
        try:
            for role in (CHAIN_A, CHAIN_B, CHAIN_C):
                await admin.execute(f'DROP ROLE IF EXISTS "{role}"')
            await admin.execute(f'CREATE ROLE "{CHAIN_C}" NOLOGIN')
            # الوسط NOINHERIT — لا الطرف.
            await admin.execute(f'CREATE ROLE "{CHAIN_B}" NOLOGIN NOINHERIT')
            await admin.execute(f'CREATE ROLE "{CHAIN_A}" NOLOGIN INHERIT')
            await admin.execute(f'GRANT "{CHAIN_C}" TO "{CHAIN_B}"')
            await admin.execute(f'GRANT "{CHAIN_B}" TO "{CHAIN_A}"')

            version = await admin.fetchval("SELECT current_setting('server_version_num')::int")

            # حقيقة الخادم نفسها — مرجعُ الحكم، لا توقّعٌ مكتوب يدويّاً.
            truth = {}
            for role in (CHAIN_B, CHAIN_C):
                truth[role] = {
                    "usage": await admin.fetchval(
                        "SELECT pg_has_role($1, $2, 'USAGE')", CHAIN_A, role
                    ),
                    "member": await admin.fetchval(
                        "SELECT pg_has_role($1, $2, 'MEMBER')", CHAIN_A, role
                    ),
                }
            assert truth[CHAIN_B]["usage"] is True, truth
            assert truth[CHAIN_C]["usage"] is False, truth  # الوراثة لا تعبر الوسط
            assert truth[CHAIN_B]["member"] is truth[CHAIN_C]["member"] is True, truth

            # **كلا الفرعين يُقاسان على أيّ خادم.** لولا ذلك لكان هذا الاختبار أخضرَ
            # «لسببٍ خاطئ» على خادم ١٦: فرعُ ما قبل ١٦ لا يُنفَّذ أصلاً، فطفرةٌ فيه
            # تنجو صامتةً — وهو ما وقع فعلاً عند تكذيب هذه الحالة أوّل مرّة. فيُجبَر
            # الفرع الآخر بتزييف رقم النسخة وحده، ويبقى الخادم حقيقيّاً.
            class _PinnedVersion:
                def __init__(self, conn, num):
                    self._c, self._n = conn, num

                async def fetchval(self, q, *a):
                    if "server_version_num" in q:
                        return self._n
                    return await self._c.fetchval(q, *a)

                async def fetch(self, q, *a):
                    return await self._c.fetch(q, *a)

            branches = {"derived_pre_pg16_rolinherit": _PinnedVersion(admin, 150008)}
            if version >= 160000:
                branches["pg_auth_members"] = admin

            for expected_source, conn in branches.items():
                rows = await csr._membership_closure(conn, CHAIN_A)
                closure = {row["role"]: row for row in rows}
                assert {CHAIN_B, CHAIN_C} <= set(closure), (expected_source, closure)
                assert closure[CHAIN_C]["depth"] == 2, (expected_source, closure[CHAIN_C])
                # الوراثة تصل الوسط ولا تتجاوزه — مطابقةً لحكم الخادم نفسه.
                for role in (CHAIN_B, CHAIN_C):
                    assert closure[role]["inherit_option"] is truth[role]["usage"], (
                        expected_source,
                        role,
                        closure[role],
                    )
                    # وSET ROLE يبقى دلالةً منفصلة: انقطاعُ الوراثة لا يقطع البلوغ.
                    assert closure[role]["set_option"] is True, (expected_source, closure[role])
                assert closure[CHAIN_B]["membership_option_source"] == expected_source, closure
        finally:
            for role in (CHAIN_A, CHAIN_B, CHAIN_C):
                await admin.execute(f'DROP ROLE IF EXISTS "{role}"')
            await admin.close()

    asyncio.run(_run())
