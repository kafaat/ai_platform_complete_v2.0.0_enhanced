#!/usr/bin/env python3
"""`OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01`: عقدٌ يُعلَن ولا يُقاس.

`docs/architecture/db_ownership.yml` يعلن لكلّ جدولٍ مالكاً وكُتّاباً وقُرّاءً —
**ولا شيء في الشجرة كان يقارن ما يُعلَن بما يقع**. فبقي العقدُ وثيقةَ نيّة، وانحرف
الكودُ عنه بصمت.

**العطلُ الذي وُجِد لأجله، مقيساً:** `db_ownership.yml:24` يعلن
``actuator_command_outbox`` مملوكاً لـ``actuator-service`` وكاتبُه هو وحده،
و``sahool-platform`` **قارئاً**. والمقيس أنّ ``sahool-platform`` يكتبه
(``phase_runtime_store.py``) وأنّ **لا قارئ له في كامل الشجرة**. والمثلُ في
``iot_command_dispatch`` — يكتبه ويقرؤه ويطالِبه ``sahool-platform`` وحده، بينما
العقدُ يعلنه قارئاً فقط. عطلان لم يكشفهما شيءٌ آليّ لأنّ **الفحص لم يكن موجوداً**.

**والقياسُ لا يُدين ما أذِن به العقدُ صراحةً:** الكتابةُ مشروعةٌ إن كانت الخدمةُ في
``writers``، **أو** كانت ``mirror`` الجدولِ — وهو جسرٌ انتقاليٌّ موثَّق
(``status: interim-bridge``) لا انحراف. فحارسٌ يخلط الاستثناءَ الموثَّقَ بالانحراف
يُنذِر كذباً، ويُدرَّب الناسُ على تجاهله، فيموت وهو أخضر.

**والكشفُ من شجرة البناء لا من النصّ** (درس
درسٌ مقيسٌ في #951): بحثٌ نصّيٌّ في
كامل الملفّ يتّهم التعليقَ الذي يشرح *لماذا* هُجِر مسارٌ، فيصير توثيقُ الإصلاح
مُبطِلاً له. هنا تُفحَص **سلاسلُ SQL الحرفيّة وحدَها**.

**والكتابةُ يُعرِّفها النحوُ لا الكلمة** (``A-WRITE-REGEX-CAPTURES-SQL-KEYWORDS-AS-TABLES-01``،
قِيس 2026-09-21): كلُّ لفظةٍ تلي ``UPDATE`` كانت تُسجَّل جدولاً، فادّعت المصنوعةُ كتابةَ
جداولَ اسمُها ``set`` و``skip`` و``the`` — من ``DO UPDATE SET`` و``FOR UPDATE SKIP LOCKED``
(قراءةٌ بقفل) ومن نثرِ التوثيق. الشرحُ المقيس عند ``_WRITE``.

**وأساسٌ ينزل ولا يصعد** (درس ``AN-EXEMPTION-LIST-WITH-NO-DESCENDING-CEILING-01``):
الراتشِت يفشل في الاتّجاهين — مخالفةٌ جديدة **ومدخلٌ بائتٌ لم يعد منحرفاً**. إعفاءٌ
بلا سقفٍ نازل ليس ديناً مؤجَّلاً بل شطبٌ صامت.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "db_ownership.yml"
BASELINE = ROOT / "docs" / "architecture" / "db_writer_ownership_baseline.json"
# الفرزُ: لكلّ مخالفةٍ في الأساس أبعادٌ مقيسةٌ بالمحرّك نفسِه وصنفٌ مشتقٌّ بقاعدةٍ معلَنة —
# يُولَّد مع الأساس بـ`--generate` ويُقاس بياتُه في `findings()`. تصنيفٌ لا حكمٌ ولا حلّ.
TRIAGE = ROOT / "docs" / "architecture" / "db_writer_ownership_triage.json"

# `INSERT INTO` · `UPDATE` · `DELETE FROM` — و`ONLY` اختياريّة (PostgreSQL).
#
# **الكلمةُ وحدَها لا تُعرِّف الكتابة — النحوُ يُعرِّفها** (`A-WRITE-REGEX-CAPTURES-SQL-
# KEYWORDS-AS-TABLES-01`, قِيس 2026-09-21). كان يكفي أن تلي كلمةَ `UPDATE` أيُّ لفظةٍ
# لتُسجَّل جدولاً، وحرفيّاتُ SQL تُلتقَط من **كلّ** سلسلةٍ طولُها ≥ `_MIN_SQL_LEN` —
# وفيها نصُّ التوثيق. فأنتج الماسحُ ٢٤ مفتاحاً جدولُه لفظةٌ لا جدول: `set` من
# `ON CONFLICT … DO UPDATE SET`، و`skip`/`of` من `FOR UPDATE SKIP LOCKED` و`FOR UPDATE OF o`
# (وكلاهما **قراءةٌ بقفل** لا كتابة)، و`or` من `BEFORE UPDATE OR DELETE` في DDL مُقتبَس،
# و`the`/`to`/`a`/`one`/`must`/`of` من جملٍ إنجليزيّةٍ في docstrings («update **the** water
# ledger idempotently» · «revoking INSERT/UPDATE/DELETE from **the** platform role»).
#
# وليس هذا ضجيجاً تجميليّاً: المصنوعةُ تقول «هذه الخدمةُ تكتب هذا الجدول»، فادّعت كتابةَ
# جداولَ اسمُها `set` و`the`. ومن قرأها يقرأ دعوى كتابةٍ لا وجود لها — وهو الصنفُ نفسُه
# الذي سُجِّل هنا باسم `SCANNER-COUNTS-A-PATH-LITERAL-AS-A-USAGE-01`.
#
# فصار لكلّ عبارةٍ **شرطُ استمرارٍ نحويّ** يفرضه معيار SQL أصلاً: بعد جدولِ `UPDATE`
# تلزم `SET` (مع كنيةٍ اختياريّة)، وبعد `INSERT INTO` تلزم قائمةُ أعمدةٍ أو مصدرُ صفوف،
# وبعد `DELETE FROM` يلزم فاصلٌ نحويٌّ أو نهايةُ الجملة. فلا يُلتقَط `DO UPDATE SET` (ليس
# رأسَ عبارة) ولا `FOR UPDATE …` (قراءة) ولا نثرٌ.
#
# **والقياسُ قبل/بعد على الشجرة نفسِها (`0606bb67`):** ٢٧٩ → ٢٥٥ مفتاحاً، الفاقدُ ٢٤
# **كلُّها** لفظاتٌ لا جداول، و**صفرٌ** مكتسَب، و`survey()` ثابتٌ عند ٧١ — أي أنّ الشدَّ
# لم يُسقِط موضعَ كتابةٍ حقيقيّاً ولا حرّك الراتشِت الحاجب.
#
# **وحدُّ صدقٍ يبقى مُعلَناً:** نثرٌ يُحاكي النحوَ حرفاً بحرف ما يزال يمرّ — سطرُ
# توثيقٍ مثل «- INSERT into event_outbox  (same transaction)» يُقرأ عبارةً صحيحة. الشدُّ
# يُضيّق البابَ ولا يُغلِقه، والتمييزُ الكاملُ يحتاج مُحلِّلَ SQL لا نمطاً.
_WRITE = re.compile(
    r"""\b(?:
        INSERT\s+INTO\s+(?:ONLY\s+)?(?P<insert>[a-z_][a-z0-9_]*)\s*
            (?=\(|VALUES\b|SELECT\b|DEFAULT\s+VALUES\b|OVERRIDING\b|AS\b|WITH\b|TABLE\b)
      | UPDATE\s+(?:ONLY\s+)?(?P<update>[a-z_][a-z0-9_]*)\s+
            (?:(?:AS\s+)?[a-z_][a-z0-9_]*\s+)?(?=SET\b)
      | DELETE\s+FROM\s+(?:ONLY\s+)?(?P<delete>[a-z_][a-z0-9_]*)\s*
            (?:(?:AS\s+)?[a-z_][a-z0-9_]*\s*)?(?=$|[;)]|WHERE\b|USING\b|RETURNING\b)
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# أقصرُ من هذا لا يحمل عبارةَ SQL كاملة — يقلّل الضجيج بلا إسقاطِ حالةٍ حقيقيّة.
_MIN_SQL_LEN = 12


def _matched_table(match: re.Match[str]) -> str:
    """الجدولُ من الفرع الذي طابق — فرعٌ واحدٌ يلتقط في كلّ مطابقة.

    بدونها كان `group(1)` يقرأ فرعَ `INSERT` وحدَه فيُعيد `None` لكلّ `UPDATE`/`DELETE`.
    """
    table = match.group("insert") or match.group("update") or match.group("delete")
    if table is None:  # pragma: no cover — لا فرعَ بلا التقاط في هذا النمط
        raise AssertionError(f"مطابقةٌ بلا جدول: {match.group(0)!r}")
    return table


_SKIP_PARTS = ("/.git/", "/node_modules/", "/tests/", "/test_", "/.venv/", "/site-packages/")

_SERVICE_ROOTS = ("scripts", "migrations", "shared", "agents", "bots")

# هويّةُ الخدمة في العقد هي اسمُها في compose لا اسمُ مجلّدها: `services/odoo-bridge/` يُبنى
# خدمةً باسم `sahool-erp-bridge` (`docker-compose.v9.yml`، و`ODOO_BRIDGE_URL` «legacy env alias»)،
# والعقدُ وخريطةُ الاستخراج يسمّيانها `erp-bridge`. بلا هذا الربط كان **المالكُ نفسُه** يُدان
# بالكتابة إلى جداوله (قِيس 2026-09-21: مدخلان في الأساس، `odoo_sync_log`/`odoo_sync_state`).
# يُثبِته `test_the_directory_identity_map_is_backed_by_compose` — لا اسمٌ هنا بلا كتلة compose.
_DIRECTORY_IDENTITY = {"odoo-bridge": "erp-bridge"}


def _service_of(rel: Path) -> str:
    """الخدمةُ من المسار: ``services/<اسم>/…`` أو الجذرُ العلويّ — والاسمُ هويّةُ compose."""
    parts = rel.parts
    if not parts:
        return "?"
    if parts[0] == "services" and len(parts) > 1:
        return _DIRECTORY_IDENTITY.get(parts[1], parts[1])
    if parts[0] in _SERVICE_ROOTS:
        return parts[0]
    return parts[0]


def load_contract() -> dict[str, Any]:
    """العقدُ يُقرأ من مفتاح ``tables``، ويُتحقَّق أنّه غيرُ فارغ.

    **هذا الشرطُ ليس تجميلاً.** أوّلُ صياغةٍ لهذا الحارس قرأت جذرَ YAML بدل
    ``tables``، فصار كلُّ جدولٍ «غيرَ مُصرَّحٍ عنه» وأبلغ الحارسُ **صفرَ مخالفات**
    على شجرةٍ تحمل خمساً وسبعين. حارسٌ يمرّ صفراً كاذباً أسوأُ من غيابه: يُقرَأ
    ضماناً ويُسجَّل تغطية.
    """
    raw = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    tables = raw.get("tables") if isinstance(raw, dict) and "tables" in raw else raw
    if not isinstance(tables, dict) or len(tables) < 100:
        raise SystemExit(
            f"OWNERSHIP_CONTRACT_UNREADABLE: {CONTRACT} أعطى "
            f"{len(tables) if isinstance(tables, dict) else 'لا شيء'} جدولاً — "
            "الحارسُ كان سيمرّ صفراً كاذباً، فيفشل صراحةً بدلاً من ذلك"
        )
    return tables


def _write_allowed(table: str, service: str, contract: dict[str, Any]) -> bool:
    meta = contract.get(table)
    if not isinstance(meta, dict):
        return True  # جدولٌ خارج العقد — لا يُدان بما لم يُعلَن عنه
    if service in (meta.get("writers") or []):
        return True
    # جسرٌ انتقاليٌّ موثَّق: `mirror` + `status: interim-bridge` إذنٌ صريح لا انحراف.
    return meta.get("mirror") == service


_SQLITE_IMPORT_ROOTS = {"sqlite3", "aiosqlite"}
_POSTGRES_IMPORT_ROOTS = {"asyncpg", "psycopg", "psycopg2", "pg8000"}


def _import_roots(tree: ast.AST) -> set[str]:
    """Top-level imported module names; aliases do not change backend identity."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _db_backend(tree: ast.AST) -> str:
    """Conservative backend evidence: unknown remains PostgreSQL-scan in-scope."""
    roots = _import_roots(tree)
    sqlite = bool(roots & _SQLITE_IMPORT_ROOTS)
    postgres = bool(roots & _POSTGRES_IMPORT_ROOTS)
    if sqlite and not postgres:
        return "sqlite"
    if postgres:
        return "postgres"
    return "unknown"


def _sql_literals(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) >= _MIN_SQL_LEN:
                yield node.value


def _python_sources(base: Path):
    """(المسارُ النسبيّ، الشجرةُ النحويّة) لكلّ ملفّ بايثون داخل نطاق المسح — مصدرٌ واحد للماسحَين."""
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base)
        posix = "/" + rel.as_posix()
        if any(part in posix for part in _SKIP_PARTS) or rel.parts[0] == "tests":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        yield rel, tree


def _write_keys(rel: Path, tree: ast.AST):
    service = _service_of(rel)
    for sql in _sql_literals(tree):
        for match in _WRITE.finditer(sql):
            yield f"{_matched_table(match).lower()}::{service}"


def write_sites(root: Path | None = None) -> dict[str, list[str]]:
    """{"<جدول>::<خدمة>": [ملفّات]} لكلّ كتابةٍ **مقيسة** — مأذونةً كانت أو لا.

    **المسحُ واحدٌ والترشيحُ بعدَه، عمداً.** كان هذا المسحُ يُسقِط المأذونَ به في
    موضع الالتقاط فلا يبقى منه أثر، بينما هو نفسُه الدليلُ الذي يرفع حافّةً مُعلَنةً
    من `declared` إلى `resolved` في جرد المكوّنات. فمَن أراد ذلك الدليلَ كان أمامه
    أن يكتب ماسحاً ثانياً — بنمطِ كتابةٍ ثانٍ وقواعدِ استثناءٍ ثانية — فينحرف الجوابان
    عن سؤالٍ واحد. والانحرافُ هنا صامت: لا شيء يُظهِره حتّى يُقارَن العددان بيدٍ.

    فصار المسحُ يُعيد ما رآه كاملاً، و`survey` مُرشِّحاً فوقه. ولا يقدر أحدُهما أن
    يرى ما لا يراه الآخر.

    **وحدُّه مُعلَن:** حرفيّاتُ SQL في بايثون وحدَها. لا `.sql` ولا ORM ولا استعلامٌ
    مُركَّبٌ في وقت التشغيل — فغيابُ موضعٍ هنا **ليس** نفياً لوجود كاتب.

    **وما يُستبعَد يُرى لا يُبتلَع:** ملفٌّ خلفيّتُه SQLite وحدَها (دليلٌ موجب: مستورِدُ
    SQLite بلا مستورِد PostgreSQL) خارجُ عقد PostgreSQL، فيُسقَط هنا — ويُعاد ما أُسقِط
    منه بالمواضع والدليل في `excluded_write_sites()`. و«مجهول» يبقى داخل النطاق.
    """
    base = ROOT if root is None else root
    found: dict[str, set[str]] = {}
    for rel, tree in _python_sources(base):
        # PostgreSQL ownership contract: only positive SQLite-only evidence excludes a file.
        # Unknown is deliberately in-scope; absence of a driver import is not an exemption.
        if _db_backend(tree) == "sqlite":
            continue
        for key in _write_keys(rel, tree):
            found.setdefault(key, set()).add(rel.as_posix())
    return {key: sorted(files) for key, files in sorted(found.items())}


def excluded_write_sites(
    root: Path | None = None, contract: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """ما أسقطه `write_sites()` لأنّ خلفيّتَه SQLite وحدَها — بالمواضع والدليل، لا بالعدد.

    استبعادٌ صامت يجعل انخفاضَ الأساس يُقرأ إصلاحاً وهو تغييرُ نطاق (72 → 71 عند
    #1055). فكلُّ مفتاحٍ أُسقِط يُعاد هنا مع الملفّات ومستورِدات SQLite التي كانت
    الدليلَ، وحالةِ العقد (أَكان الإسقاطُ سيغيّر الراتشِت أم لا). القاعدةُ قاعدةُ
    `_db_backend` نفسُها؛ لا مرشّحَ ثانٍ.
    """
    base = ROOT if root is None else root
    contract = load_contract() if contract is None else contract
    out: dict[str, dict[str, Any]] = {}
    for rel, tree in _python_sources(base):
        if _db_backend(tree) != "sqlite":
            continue
        roots = _import_roots(tree)
        for key in _write_keys(rel, tree):
            table, service = key.split("::", 1)
            entry = out.setdefault(
                key,
                {
                    "files": set(),
                    "reason": "sqlite_only_backend",
                    "evidence": {
                        "driver_imports": sorted(roots & _SQLITE_IMPORT_ROOTS),
                        "postgres_driver_imports": sorted(roots & _POSTGRES_IMPORT_ROOTS),
                    },
                    "contract_state": (
                        "outside_contract"
                        if not isinstance(contract.get(table), dict)
                        else "authorised"
                        if _write_allowed(table, service, contract)
                        else "not_authorised"
                    ),
                },
            )
            entry["files"].add(rel.as_posix())
    return {key: {**entry, "files": sorted(entry["files"])} for key, entry in sorted(out.items())}


def survey() -> dict[str, list[str]]:
    """{"<جدول>::<خدمة>": [ملفّات]} لكلّ كتابةٍ لم يأذن بها العقد."""
    contract = load_contract()
    return {
        key: files
        for key, files in write_sites().items()
        if not _write_allowed(key.split("::", 1)[0], key.split("::", 1)[1], contract)
    }


def _head_sha() -> str:
    """رأسُ الشجرة الذي قِيس عليه الأساس — أو ``unknown`` إن تعذّر (لا رمي، ولا اختلاق).

    قيمةٌ مختلقةٌ كانت ستُنتِج ختماً يبدو صادقاً ولا يُحيل إلى شيء؛ و``unknown``
    تُبقي الفجوةَ مرئيّةً لـ``claim_base_guard`` بدل أن تُخفيها.

    و``measured_on`` **إشارةُ إسناد** لا سلطةَ طزاجة: يقول أين قِيس الأساس، لا أنّ
    القياسَ ما زال صالحاً — السلطةُ للماسح حين يُعاد تشغيله.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and len(sha) == 40 else "unknown"


def _baseline() -> dict[str, list[str]]:
    if not BASELINE.is_file():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("violations", {})


def findings() -> list[str]:
    current, base = survey(), _baseline()
    out: list[str] = []
    for key in sorted(set(current) - set(base)):
        files = " · ".join(current[key])
        out.append(f"مخالفةٌ جديدة: {key} ⇒ {files}")
    # الراتشِت ينزل: مدخلٌ بائتٌ يُقرَأ ديناً قائماً وقد سُدِّد.
    for key in sorted(set(base) - set(current)):
        out.append(f"مدخلٌ بائتٌ في الأساس لم يعد منحرفاً — احذفه: {key}")
    out.extend(triage_drift())
    return out


# ── الفرز: أبعادٌ مقيسة وصنفٌ مشتقّ — لكلّ مخالفةٍ في الأساس ─────────────────────

TRIAGE_CATEGORIES = (
    "owner-name-not-in-tree",  # العقدُ يسمّي مالكاً لا مجلّدَ له ولا هويّةَ compose تربطه
    "tooling-writer",  # الكاتبُ سكربتٌ لا خدمة
    "dual-writer",  # رُصد المالكُ بين الكُتّاب ومعه كاتبٌ آخر
    "owner-never-writes",  # لم يُرصد للمالك موضعُ كتابةٍ في نطاق الماسح
)

# لقطةُ نشر Railway من المراجعة الخارجيّة 2026-09-20
# (docs/evidence/railway_audit_review_20260920.md) — **مؤرَّخةٌ لا حيّة**: وجودُ الخدمة
# فيها ليس إذناً بتحويل الكتابة إليها وقتَ الانتقال. تُحمَل في كلّ صفٍّ كائنَ
# `deployment_evidence` مؤرَّخاً، و`cutover_ready` فيه `false` دائماً: الجاهزيّةُ تُقاس
# حيّةً وقتَ الانتقال (D9) لا تُشتقّ من لقطة.
_DEPLOYMENT_EVIDENCE_OBSERVED_ON = "2026-09-20"
_DEPLOYMENT_EVIDENCE_SOURCE = "docs/evidence/railway_audit_review_20260920.md"
_DEPLOYED_RAILWAY_20260920 = frozenset(
    {
        "sahool-platform",
        "auth",
        "tts-service",
        "guardrails-engine",
        "notification",
        "field-management-service",
        "raster-service",
        "vegetation-analysis-service",
    }
)


def owner_dir_in_tree(owner: str | None, root: Path | None = None) -> bool:
    """مجلّدُ المالك تحت ``services/`` — بهويّة compose (`_DIRECTORY_IDENTITY`) لا بالاسم الحرفيّ وحده."""
    base = ROOT if root is None else root
    directories = [d for d, identity in _DIRECTORY_IDENTITY.items() if identity == owner] or [
        str(owner)
    ]
    return any((base / "services" / d).is_dir() for d in directories)


def writer_kind(files: list[str]) -> str:
    first = files[0] if files else ""
    if first.startswith("scripts/e2e/"):
        return "e2e-script"
    if first.startswith("scripts/"):
        return "ops-script"
    if first.startswith("agents/"):
        return "agent"
    if "/routers/" in first:
        return "service-router"
    if "worker" in first:
        return "worker"
    return "service-module"


def derive_category(*, owner_dir_in_tree: bool, writer: str, owner_writes_table: bool) -> str:
    """القاعدةُ الوحيدة التي تُنتِج الصنف — دالّةٌ على أبعادٍ مقيسة، لا اختيار.

    **والصنفُ لا يحمل عددَ الكُتّاب**: `owner-never-writes` يقول إنّ المالكَ لم يُرصد،
    لا إنّ الكاتبَ المخالف وحيد. عددُ الكُتّاب بُعدٌ مستقلّ (`measured_writer_count` ·
    `multiple_non_owner_writers`) — كان الوصفُ يخلطهما فقال «الكاتبُ الوحيد» عن
    `weather_signals` وله كاتبان مرصودان (كشفه المالك بالقراءة، 2026-09-21).
    """
    if not owner_dir_in_tree:
        return "owner-name-not-in-tree"
    if writer == "scripts":
        return "tooling-writer"
    if owner_writes_table:
        return "dual-writer"
    return "owner-never-writes"


def remedy(category: str, non_owner_writer_count: int) -> tuple[str, str]:
    """(العلاجُ المقترَح، صاحبُ القرار) — نصٌّ مشتقٌّ من الصنف وعدد الكُتّاب، لا من صفٍّ بعينه.

    «لم يُرصد» لا «لا يكتب»: نطاقُ الماسح حرفيّاتُ SQL في بايثون وحدَها، فغيابُ الموضع
    ليس نفياً. ولا يُوصَف كاتبٌ بأنّه الوحيد إلّا حين يكون عددُ الكُتّاب غيرِ المالك واحداً.
    """
    scope = "لم يُرصد للمالك المُعلَن موضعُ كتابةٍ في نطاق الماسح (حرفيّاتُ SQL في بايثون؛ غيابُ الموضع ليس نفياً)"
    if category == "owner-never-writes":
        if non_owner_writer_count > 1:
            # صاحبُ القرار المالكُ — لكنّ قرارَه مشروطٌ بمراجعةٍ هندسيّة تسبقه، وهذا في النصّ
            # لا في قيمةٍ ثالثة: مفرداتُ `decision_owner` اثنتان كي لا يتشعّب الحقلُ بلا سقف.
            return (
                f"{scope}، ورُصد {non_owner_writer_count} كُتّابٍ غيرِ المالك لهذا الجدول — لا يجوز "
                "وصفُ أيٍّ منهم بالكاتب الوحيد. تعدّدُ كتابةٍ يحتاج مراجعةً هندسيّةً (من يكتب ماذا "
                "ومتى، وهل يتنافسان) قبل أيّ قرارِ ملكيّة. الخياران بعدها: استخراجٌ إلى المالك بواجهةٍ "
                "يملكها (نمطُ البند ٣، إن كان منشوراً)، أو إعادةُ إعلانٍ يرفضها "
                "`ownership_extraction_alignment_guard` ما دام المالكُ هدفَ استخراجٍ حيّ.",
                "owner",
            )
        return (
            f"{scope}، والكاتبُ المرصودُ الوحيدُ هو المخالف. الخياران: (أ) استخراجُ الكتابة إلى "
            "المالك بواجهةٍ يملكها ثمّ استدعاؤها (نمطُ البند ٣) — ممكنٌ فقط إن كان المالكُ منشوراً "
            "وقتَ الانتقال لا في لقطةٍ قديمة؛ (ب) إعادةُ إعلان الكاتب مالكاً/كاتباً إن لم يعد الاستخراجُ "
            "مقصوداً — يرفضه `ownership_extraction_alignment_guard` ما دام المالكُ هدفَ استخراجٍ حيّ، "
            "فهو قرارُ مالكٍ لا سطر.",
            "owner",
        )
    if category == "dual-writer":
        return (
            f"رُصد المالكُ بين الكُتّاب ومعه {non_owner_writer_count} كاتبٌ غيرُه — تعارضُ كتابةٍ "
            "حقيقيّ. العلاج: توجيهُ كتابة غيرِ المالك عبر واجهةٍ يملكها المالك (نمطُ البند ٣) أو "
            "جسرٌ انتقاليٌّ موثَّق (`mirror` + `status: interim-bridge`) بسقفٍ نازل. وتشغيلُ الكاتب بدور "
            "مالك الجدول في PostgreSQL ليس حلّاً: ملكيّةُ الخدمة في العقد غيرُ ملكيّة الجدول وصلاحيّاتِ "
            "الدور وسياساتِ RLS.",
            "engineering",
        )
    if category == "tooling-writer":
        return (
            "الكاتبُ سكربتُ تشغيلٍ/e2e لا خدمة. العلاج: نقلُه تحت أدوات المالك أو إعلانُه جسراً "
            "موثَّقاً بسقف. ونقلُ الملفّ وحدَه لا يُثبِت انتقالَ سلطة الكتابة ولا صحّةَ المعاملة — "
            "تُختبَر الصلاحيّاتُ الفعليّة وعزلُ المستأجرين.",
            "engineering",
        )
    return (
        "العقدُ يسمّي مالكاً لا مجلّدَ له ولا هويّةَ compose تربطه. العلاج: تصحيحُ الاسم في العقد "
        "أو إضافةُ الربط في `_DIRECTORY_IDENTITY` بدليلٍ من compose.",
        "owner",
    )


def triage_rows(
    contract: dict[str, Any] | None = None,
    sites: dict[str, list[str]] | None = None,
    violations: dict[str, list[str]] | None = None,
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """صفوفُ الفرز من المحرّك نفسِه: العقد + `write_sites()` + الأساس. حتميّةٌ من الشجرة."""
    contract = load_contract() if contract is None else contract
    sites = write_sites(root) if sites is None else sites
    violations = _baseline() if violations is None else violations
    writers_of: dict[str, set[str]] = {}
    for key in sites:
        table, service = key.split("::", 1)
        writers_of.setdefault(table, set()).add(service)
    rows: dict[str, dict[str, Any]] = {}
    for key, files in sorted(violations.items()):
        table, writer = key.split("::", 1)
        meta = contract.get(table) if isinstance(contract.get(table), dict) else {}
        owner = meta.get("owner")
        writers = sorted(writers_of.get(table, set()))
        non_owner = [w for w in writers if w != owner]
        in_tree = owner_dir_in_tree(owner, root)
        owner_writes = owner in writers
        category = derive_category(
            owner_dir_in_tree=in_tree, writer=writer, owner_writes_table=owner_writes
        )
        text, decision = remedy(category, len(non_owner))
        rows[key] = {
            "table": table,
            "writer": writer,
            "files": files,
            "declared_owner": owner,
            "declared_writers": meta.get("writers"),
            "owner_dir_in_tree": in_tree,
            "measured_writers_of_table": writers,
            "measured_writer_count": len(writers),
            "non_owner_writers": non_owner,
            "multiple_non_owner_writers": len(non_owner) > 1,
            "owner_writes_table": owner_writes,
            "writer_kind": writer_kind(files),
            "category": category,
            "remedy": text,
            "decision_owner": decision,
            "status": "triaged",
            "deployment_evidence": {
                "observed_on": _DEPLOYMENT_EVIDENCE_OBSERVED_ON,
                "source": _DEPLOYMENT_EVIDENCE_SOURCE,
                "owner_deployed": owner in _DEPLOYED_RAILWAY_20260920,
                "writer_deployed": writer in _DEPLOYED_RAILWAY_20260920,
                "cutover_ready": False,
                "freshness": "historical_snapshot",
            },
        }
    return rows


def triage_document(
    rows: dict[str, dict[str, Any]], excluded: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    for row in rows.values():
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
    excluded = excluded_write_sites() if excluded is None else excluded
    return {
        "$comment": (
            "فرزُ مخالفات ملكيّة الكتابة: كلُّ صفٍّ مقيسٌ بمحرّك db_writer_ownership_guard نفسِه "
            "(write_sites + العقد + الأساس)، والصنفُ مشتقٌّ بقاعدةٍ صريحة (derive_category في الحارس) "
            "لا مختار، وعددُ الكُتّاب بُعدٌ مستقلٌّ عن الصنف. المصنوعةُ تصنّف ولا تحكم ولا تحلّ: "
            "status=triaged لكلّ صفّ. تُولَّد مع الأساس بـ--generate ويُقاس بياتُها صفّاً صفّاً في --check. "
            "'owner_writes_table: false' تعني «لم يُرصد موضع» بحدّ الماسح (حرفيّاتُ SQL في بايثون؛ "
            "ملفّاتُ SQLite-only خارج النطاق وتُرى في excluded_write_sites) لا «لا يكتب». "
            "'deployment_evidence' لقطةٌ مؤرَّخة من مراجعةٍ خارجيّة لا حالةٌ حيّة، وcutover_ready فيها false دائماً."
        ),
        "baseline": BASELINE.relative_to(ROOT).as_posix(),
        "measured_on": _head_sha(),
        "category_vocabulary": list(TRIAGE_CATEGORIES),
        "counts": {
            "total": len(rows),
            "by_category": by_category,
            "multiple_non_owner_writers": sum(
                1 for r in rows.values() if r["multiple_non_owner_writers"]
            ),
            "excluded_write_sites": len(excluded),
            "excluded_by_contract_state": {
                state: sum(1 for e in excluded.values() if e["contract_state"] == state)
                for state in ("not_authorised", "authorised", "outside_contract")
            },
        },
        "rows": rows,
        "excluded_write_sites": excluded,
    }


def _stored_triage() -> dict[str, Any] | None:
    if not TRIAGE.is_file():
        return None
    return json.loads(TRIAGE.read_text(encoding="utf-8"))


def triage_drift() -> list[str]:
    """الفرزُ المخزَّن يجب أن يساوي ما يُشتقّ من الشجرة الآن — صفّاً صفّاً، لا عدداً.

    والمستبعَدُ جزءٌ من القياس: استبعادٌ يظهر أو يزول أو يغيّر دليلَه بلا إعادة توليد
    انحرافٌ مثلُ صفٍّ بائت.
    """
    stored = _stored_triage()
    if stored is None:
        return [f"مصنوعةُ الفرز غائبة: {TRIAGE.relative_to(ROOT)} — أعِد --generate"]
    stored_rows = stored.get("rows") or {}
    current = triage_rows()
    out: list[str] = []
    for key in sorted(set(current) - set(stored_rows)):
        out.append(f"مخالفةٌ بلا فرز: {key} — أعِد --generate")
    for key in sorted(set(stored_rows) - set(current)):
        out.append(f"فرزٌ بائت لمخالفةٍ زالت: {key} — أعِد --generate")
    for key in sorted(set(current) & set(stored_rows)):
        if current[key] != stored_rows[key]:
            changed = sorted(f for f in current[key] if current[key][f] != stored_rows[key].get(f))
            out.append(f"فرزٌ بائت: {key} — تغيّر {', '.join(changed)} — أعِد --generate")
    stored_excluded = stored.get("excluded_write_sites") or {}
    current_excluded = excluded_write_sites()
    for key in sorted(set(current_excluded) ^ set(stored_excluded)):
        out.append(f"استبعادٌ لا يطابق الشجرة: {key} — أعِد --generate")
    for key in sorted(set(current_excluded) & set(stored_excluded)):
        if current_excluded[key] != stored_excluded[key]:
            out.append(f"استبعادٌ بائت (تغيّر الدليل أو المواضع): {key} — أعِد --generate")
    return out


def generate_triage() -> None:
    rows = triage_rows()
    excluded = excluded_write_sites()
    TRIAGE.write_text(
        json.dumps(triage_document(rows, excluded), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(
        f"كُتِب {TRIAGE.relative_to(ROOT)} — {len(rows)} صفّاً مفروزاً · {len(excluded)} موضعاً مستبعَداً"
    )


def generate() -> None:
    current = survey()
    BASELINE.write_text(
        json.dumps(
            {
                "$comment": (
                    "كتاباتٌ لم يأذن بها docs/architecture/db_ownership.yml — "
                    "مَعدودةٌ لا محكومٌ عليها. لم يُثبَت أنّ كلّاً منها خطأ؛ بعضُها قد "
                    "يكون العقدُ هو المخطئ فيه. الأساسُ راتشِتٌ ينزل ولا يصعد: "
                    "يُخفَّض بنقل الكتابة إلى مالكها أو بتصحيح العقد بأساسٍ مُعلَن."
                ),
                "contract": CONTRACT.relative_to(ROOT).as_posix(),
                "measured_on": _head_sha(),
                "violation_count": len(current),
                "violations": current,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"كُتِب {BASELINE.relative_to(ROOT)} — {len(current)} مخالفة")
    generate_triage()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="الوضعُ الحاجب (افتراضيّ)")
    parser.add_argument("--generate", action="store_true", help="إعادةُ توليد الأساس")
    args = parser.parse_args(argv)

    if args.generate:
        generate()
        return 0

    problems = findings()
    if problems:
        print("db_writer_ownership_guard: FAIL")
        for item in problems:
            print(f"  ✗ {item}")
        print(
            "\nالكتابةُ تنتمي إلى مالك الجدول. إن كان العقدُ هو المخطئ فصحّحه "
            "بأساسٍ مُعلَن، ثمّ:\n  python scripts/ci/db_writer_ownership_guard.py --generate"
        )
        return 1
    print(f"db_writer_ownership_guard_ok baseline={len(_baseline())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
