"""حُرّاس ساكنون لحزمة تصليب البنية التحتيّة «72 ساعة» (التدقيق الجنائيّ للطبقة
البيانات). نصّيّة صرفة — لا استيراد لأيّ كود خدمات.

يفرض:
- v206 آخر مدخل MANIFEST دائمًا + محتواه (fail-closed WITH CHECK + catalog assertion).
- وجهةُ PostgreSQL مُعرَّفةٌ **مرّةً واحدة** يقرأ منها النسخُ الاحتياطيّ والاستعادة،
  وتطابق خدمةَ compose ودورَها فعلاً (لا sahool-postgis/postgres).
- دور Odoo المقيَّد في apply_in_compose.sh (REVOKE ALL PRIVILEGES على قاعدة المنصّة).
- سحب CONNECT الضمنيّ من PUBLIC + منح صريح + حارس MANIFEST وقت التشغيل + تأكيد
  سمات الأدوار (SUPERUSER/BYPASSRLS) عند bootstrap.
- compose: redis-state منفصل (noeviction+AOF) وخدمات الأمان تشير إليه، وOdoo لا
  يعمل بـsahool_user. (تُستكمَل تعديلات compose ضمن الفرع نفسه قبل فتح PR.)
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "migrations/MANIFEST.txt"
V206 = ROOT / "migrations/v206_rls_final_hardening.sql"
BACKUP = ROOT / "scripts/backup_postgres.sh"
RESTORE = ROOT / "scripts/restore_postgres.sh"
LIB_PG = ROOT / "scripts/lib/pg_conn_defaults.sh"
APPLY = ROOT / "migrations/apply_in_compose.sh"
COMPOSE = ROOT / "docker-compose.v9.yml"


def _manifest_sql_entries() -> list[str]:
    return [
        ln.strip()
        for ln in MANIFEST.read_text(encoding="utf-8").splitlines()
        if ln.strip().endswith(".sql")
    ]


def test_v206_is_last_manifest_entry():
    entries = _manifest_sql_entries()
    assert entries, "MANIFEST بلا مداخل"
    assert entries[-1] == "v206_rls_final_hardening.sql", (
        f"v206 يجب أن يبقى آخر مدخل دائمًا (الأخير الآن: {entries[-1]})"
    )


def test_v206_fail_closed_and_catalog_assertion():
    src = V206.read_text(encoding="utf-8")
    # تشديد tenant_isolation: الكتابة بلا سياق تفشل (سحب هروب IS NULL القديم):
    assert "policyname = 'tenant_isolation'" in src
    assert "with_check ILIKE '%current_setting%IS NULL%'" in src
    assert "sahool_effective_tenant_id()" in src
    # تأكيد catalog دائم: ENABLE + FORCE + WITH CHECK، وEXCEPTION عند التسرب:
    assert "relforcerowsecurity" in src
    assert "RAISE EXCEPTION 'v206 catalog assertion:" in src


def _compose_postgres_identity() -> tuple[str, str, str]:
    """يشتقّ (المضيف، الدور، القاعدة) من `docker-compose.v9.yml` نفسِه.

    الاشتقاق قصدٌ لا زينة: صياغةٌ تُثبِّت السلاسل حرفيّاً تقيس **تطابقَ نصٍّ مع نصّ**،
    فتبقى خضراء لو أُعيدت تسميةُ الخدمة في compose وتخلّف السكربتان. والمقصود
    خاصّيّةٌ أخرى: أن يقصد السكربتان **ما هو قائمٌ فعلاً**.
    """
    src = COMPOSE.read_text(encoding="utf-8")
    block = src.split("\n  sahool-postgres:", 1)[1].split("\n  sahool-", 1)[0]
    db = re.search(r"POSTGRES_DB:\s*(\S+)", block)
    user = re.search(r"POSTGRES_USER:\s*(\S+)", block)
    assert db and user, "خدمة sahool-postgres في compose بلا POSTGRES_DB/POSTGRES_USER"
    return "sahool-postgres", user.group(1), db.group(1)


def test_one_definition_of_the_postgres_destination_shared_by_backup_and_restore():
    """وجهةُ القاعدة تُعرَّف **مرّةً واحدة**، ويقرأ منها النسخُ الاحتياطيّ والاستعادة.

    **العطل المقيس:** كان لكلٍّ منهما جدولُ افتراضاتٍ خاصّ. النسخُ يقصد
    `sahool-postgres`/`sahool_user` (وهو ما في compose)، والاستعادةُ تقصد
    `sahool-postgis`/`postgres` — **مضيفٌ ودورٌ لا وجودَ لهما** في الملفّ القانونيّ.
    وكان تعليقُ الاستعادة يقول «نفس قيم backup_postgres.sh»: انحرافٌ يحمل معه دعوى
    عدم الانحراف، فلا يفحصه قارئ.

    **وهذا الاختبارُ نفسُه كان نصفَ حارس:** فرض الزوجَ الصحيح على `backup` وحدَه،
    وسمّى `sahool-postgis/postgres` خطأً بالحرف — وهو ما كان في `restore` بلا أن
    ينظر إليه. فالمقيسُ الآن الطرفان والمصدرُ الواحد.
    """
    host, user, database = _compose_postgres_identity()
    lib = LIB_PG.read_text(encoding="utf-8")
    assert f': "${{PGHOST:={host}}}"' in lib, f"المصدر الواحد لا يقصد خدمة compose ({host})"
    assert f': "${{PGUSER:={user}}}"' in lib, f"المصدر الواحد لا يقصد دور compose ({user})"
    assert f': "${{PGDATABASE:={database}}}"' in lib

    for script in (BACKUP, RESTORE):
        src = script.read_text(encoding="utf-8")
        assert "lib/pg_conn_defaults.sh" in src, f"{script.name} لا يقرأ من المصدر الواحد"
        # ولا جدولَ ثانياً: تعريفٌ محلّيٌّ لأيٍّ من الأربعة يُعيد الانحرافَ الذي أُزيل.
        for name in ("PGHOST", "PGPORT", "PGUSER", "PGDATABASE"):
            assert f'{name}="${{{name}:-' not in src, (
                f"{script.name} يُعيد تعريف {name} محلّيّاً — تعريفان لحاجةٍ واحدة"
            )


def test_neither_backup_nor_restore_targets_the_nonexistent_host_or_role():
    """الشاهدُ السالب صريحاً: الزوجُ الخاطئ الذي أسقط الاستعادة لا يعود من أيّ باب.

    `sahool-postgis` اسمٌ **قائمٌ** في `docker-compose.light.yml` — فليس هراءً
    يُمسَك بالصدفة، بل جارٌ مقنعٌ يسهل أن يُكتَب مرّةً أخرى.
    """
    for path in (BACKUP, RESTORE, LIB_PG):
        src = path.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        assert "sahool-postgis" not in code, f"{path.name}: الخدمة الفعليّة هي sahool-postgres"
        assert "PGUSER:=postgres}" not in code and "PGUSER:-postgres}" not in code, (
            f"{path.name}: الدور الفعليّ هو sahool_user"
        )


def test_odoo_restricted_role_cannot_reach_platform_db():
    src = APPLY.read_text(encoding="utf-8")
    assert "ODOO_DB_ROLE:-odoo_app" in src, "دور odoo_app المقيَّد غائب"
    # REVOKE CONNECT وحده لا يكفي (يبقي المنح السابقة/TEMP) — يلزم REVOKE ALL:
    assert "REVOKE ALL PRIVILEGES ON DATABASE" in src, "سحب كلّ امتيازات قاعدة المنصّة عن odoo غائب"
    assert "NOBYPASSRLS CREATEDB NOCREATEROLE" in src


def test_public_connect_revoked_with_explicit_grants():
    src = APPLY.read_text(encoding="utf-8")
    # PostgreSQL يمنح CONNECT لـPUBLIC افتراضيًّا — يهزم REVOKE الموجَّه لأيّ دور جديد:
    assert "FROM PUBLIC" in src and "REVOKE CONNECT ON DATABASE" in src, (
        "سحب CONNECT الضمنيّ من PUBLIC غائب"
    )
    # والمنح الصريح للأدوار المُدارة موجود (إلّا يتعذّر اتّصال التطبيق نفسه):
    assert "GRANT CONNECT ON DATABASE" in src


def test_manifest_last_entry_enforced_at_runtime():
    src = APPLY.read_text(encoding="utf-8")
    # الحارس الساكن (أعلاه) لا يكفي — السكربت نفسه يجب أن يرفض MANIFEST مكسور الترتيب:
    assert "LAST_SQL=" in src, "حارس وقت التشغيل لآخر مدخل MANIFEST غائب"
    assert '!= "v206_rls_final_hardening.sql"' in src
    assert "exit 1" in src


def test_bootstrap_roles_attributes_asserted():
    src = APPLY.read_text(encoding="utf-8")
    # تأكيد bootstrap: لا SUPERUSER/BYPASSRLS خارج القائمة المعتمدة (انجراف يدويّ):
    assert "app.managed_roles" in src
    assert "app.bypassrls_allowed" in src
    assert "r.rolsuper OR r.rolbypassrls" in src
    assert "bootstrap assertion فشل" in src


def test_compose_splits_security_redis_from_cache():
    src = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-redis-state:" in src, "خدمة redis-state المنفصلة غائبة"
    block = src.split("sahool-redis-state:", 1)[1].split("\n  sahool-", 1)[0]
    assert "noeviction" in block, "redis-state يجب أن يكون noeviction"
    assert "--appendonly yes" in block, "redis-state يتطلّب AOF"
    # خدمات الحالة الأمنيّة (auth + guardrails) تشير إلى redis-state:
    auth_block = src.split("\n  sahool-auth:", 1)[1].split("\n  sahool-", 1)[0]
    assert "sahool-redis-state" in auth_block, "auth ما زال على redis الكاش"
    guard_block = src.split("\n  sahool-guardrails-engine:", 1)[1].split("\n  sahool-", 1)[0]
    assert "sahool-redis-state" in guard_block, "guardrails ما زال على redis الكاش"


def test_compose_odoo_not_platform_superuser():
    src = COMPOSE.read_text(encoding="utf-8")
    odoo_block = src.split("\n  sahool-odoo:", 1)[1].split("\n  sahool-", 1)[0]
    assert "USER: sahool_user" not in odoo_block, "Odoo ما زال يعمل بمالك الهجرات"
    assert "ODOO_DB_ROLE" in odoo_block or "odoo_app" in odoo_block
