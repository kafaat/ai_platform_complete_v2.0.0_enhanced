"""حارس: كلّ فهرسٍ في الهجرات يسمّي أعمدةً يُعرِّفها جدولُه فعلاً في مكانٍ ما من الشجرة.

**العطلُ المقيس، لا المتوقَّع** — `MIGRATION-INDEX-NAMES-A-COLUMN-NO-TABLE-DEFINES-01`.
`migrations/v9_new_tables.sql:165` يحرس فهرساً بوجود الجدول (`to_regclass('market_price_history')`)
ثمّ يُنشئه على `(crop_type, recorded_at)` — وعمودان لا يُعرِّفهما **أيُّ** تعريفٍ للجدول في
الشجرة كلّها: التعريفُ الوحيد في `v229_market_mcp_schema.sql:35` أعمدتُه `category` و
`recorded_date`. على قاعدةٍ **جديدة** يمرّ (الجدولُ غائبٌ حين يُقرأ الحارس، ترتيبُ MANIFEST
يضع v9 قبل v229 بسبعمئة سطر) — ولذلك لم تمسكه «18/18 على قاعدة جديدة». وعلى قاعدةٍ
**قائمة** (`docker compose up --force-recreate` على volume طُبِّق عليه v229) الجدولُ موجود ⇒
يدخل الحارس ⇒ ``ERROR: column "crop_type" does not exist`` ⇒ `sahool-migrate` exit 3
والمكدّسُ كلُّه لا يُقلِع. مقيسٌ على مكدّس المالك 2026-09-07.

**والصنف أعمّ من هذا الفهرس:** الحارسُ بوجود الجدول (`to_regclass`) صحيحٌ ضدّ «الجدول لم
يُنشأ بعد» وأعمى عن «الجدول موجودٌ بشكلٍ آخر». وسكربتُ التطبيق يطبع «idempotent — آمنة على
التكرار» **والتكرارُ لم يُقَس قطّ**: جناحُ التمهيد يطبّق البيان على قاعدةٍ فارغة مرّةً واحدة.

هذا الحارس ساكن ولا يحتاج PostgreSQL: يقرأ البيان بترتيبه، يجمع أعمدةَ كلّ جدول من كلّ
`CREATE TABLE` و`ALTER TABLE … ADD COLUMN` و`RENAME COLUMN`، ثمّ يفحص كلّ `CREATE INDEX`
بقائمة أعمدةٍ صريحة. **يحكم فقط على الجداول التي يعرف تعريفَها**: فهرسٌ على جدولٍ لا
يُعرِّفه أيُّ ملفٍّ في البيان (يُنشأ في خدمةٍ أو مجموعةٍ أخرى) لا يُحكَم عليه — فحكمٌ بلا
تعريفٍ تخمين. والفهارسُ التعبيريّة (`lower(col)`، مسارات JSONB) تُتخطّى لأنّ أعمدتها ليست
قائمةً بسيطة؛ مقيسٌ على الشجرة: ٤٤٨ من ٤٥١ فهرساً قوائمُ بسيطة.

**حدُّ صدق:** لا يقيس هذا الحارسُ «التكرار على قاعدةٍ قائمة» نفسَه — ذاك يحتاج تطبيقَ
البيان مرّتين على PostgreSQL حيّ، وهو ما يبقى مسجَّلاً فجوةً. يقيس البديلَ الساكن الذي
كان سيُحمِّر على العطل المقيس قبل أن يصل إلى أيّ قاعدة.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
MANIFEST = MIGRATIONS / "MANIFEST.txt"

_CONSTRAINT_KEYWORDS = frozenset(
    {"primary", "foreign", "unique", "check", "constraint", "exclude", "like", "inherits"}
)
_ORDER_WORDS = frozenset({"asc", "desc", "nulls", "first", "last"})

_CREATE_TABLE = re.compile(
    r"CREATE\s+(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[\w.\"]+)\s*\((?P<body>.*?)\)\s*(?:INHERITS|PARTITION|WITH|TABLESPACE|;)",
    re.I | re.S,
)
_CREATE_TABLE_AS = re.compile(
    r"CREATE\s+(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[\w.\"]+)\s+AS\s",
    re.I,
)
_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(?P<name>[\w.\"]+)\s+(?P<clauses>[^;]*);",
    re.I | re.S,
)
_ADD_COLUMN_CLAUSE = re.compile(
    r"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?P<col>[\w\"]+)", re.I
)
_RENAME_COLUMN = re.compile(
    r"RENAME\s+(?:COLUMN\s+)?(?P<old>[\w\"]+)\s+TO\s+(?P<new>[\w\"]+)", re.I
)
_CREATE_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<index>[\w\"]+)\s+ON\s+(?:ONLY\s+)?(?P<table>[\w.\"]+)\s*(?:USING\s+\w+\s*)?"
    r"\((?P<cols>[^()]*)\)",
    re.I | re.S,
)
_PLAIN_COLUMN_LIST = re.compile(r"^[\w\"\s,]+$")


def _ident(raw: str) -> str:
    """اسمٌ مُطبَّع: بلا مخطّط، بلا اقتباس، بأحرفٍ صغيرة — كما يقارنه PostgreSQL."""
    return raw.split(".")[-1].strip().strip('"').lower()


def _split_top_level(body: str) -> list[str]:
    """يقسم جسدَ CREATE TABLE على الفواصل خارج الأقواس (NUMERIC(14,4) تحوي فاصلة)."""
    parts, depth, current = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _manifest_files() -> list[Path]:
    names = [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return [MIGRATIONS / name for name in names]


def _strip_sql_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"--[^\n]*", " ", text)


def known_columns() -> dict[str, set[str]]:
    """أعمدةُ كلّ جدولٍ كما تُعرِّفها الهجرات مجتمعةً، بترتيب البيان."""
    columns: dict[str, set[str]] = {}
    created_as: set[str] = set()
    for path in _manifest_files():
        if not path.exists():
            continue
        text = _strip_sql_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in _CREATE_TABLE_AS.finditer(text):
            created_as.add(_ident(m.group("name")))
        for m in _CREATE_TABLE.finditer(text):
            table = _ident(m.group("name"))
            cols = columns.setdefault(table, set())
            for entry in _split_top_level(m.group("body")):
                words = entry.split()
                if not words or words[0].lower() in _CONSTRAINT_KEYWORDS:
                    continue
                cols.add(_ident(words[0]))
        for m in _ADD_COLUMN.finditer(text):
            table = _ident(m.group("name"))
            clauses = m.group("clauses")
            for c in _ADD_COLUMN_CLAUSE.finditer(clauses):
                columns.setdefault(table, set()).add(_ident(c.group("col")))
            for r in _RENAME_COLUMN.finditer(clauses):
                columns.setdefault(table, set()).add(_ident(r.group("new")))
    # جدولٌ أُنشئ بـ`AS SELECT` أعمدتُه من الاستعلام — لا نعرفها فلا نحكم عليه.
    for table in created_as:
        columns.pop(table, None)
    return columns


def index_column_references() -> list[tuple[str, int, str, str, list[str]]]:
    """(الملفّ، السطر، الفهرس، الجدول، الأعمدة) لكلّ فهرسٍ بقائمة أعمدةٍ بسيطة."""
    found = []
    for path in _manifest_files():
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = _strip_sql_comments(raw)
        for m in _CREATE_INDEX.finditer(text):
            cols_raw = m.group("cols")
            if not _PLAIN_COLUMN_LIST.match(cols_raw):
                continue  # فهرسٌ تعبيريّ — ليس قائمةَ أعمدة
            cols = []
            for piece in cols_raw.split(","):
                words = [w for w in piece.split() if w.lower() not in _ORDER_WORDS]
                if words:
                    cols.append(_ident(words[0]))
            line = text.count("\n", 0, m.start()) + 1
            found.append(
                (path.name, line, _ident(m.group("index")), _ident(m.group("table")), cols)
            )
    return found


def test_every_indexed_column_is_defined_by_some_migration_of_its_table() -> None:
    columns = known_columns()
    offenders = []
    for file, line, index, table, cols in index_column_references():
        if table not in columns:
            continue  # جدولٌ لا يُعرِّفه البيان — لا حكمَ بلا تعريف
        missing = [c for c in cols if c not in columns[table]]
        if missing:
            offenders.append(
                f"{file}:{line} {index} ON {table}({', '.join(cols)}) — مفقود: {missing}"
            )
    assert not offenders, (
        "فهارسُ تسمّي أعمدةً لا يُعرِّفها أيُّ تعريفٍ لجدولها في الهجرات كلّها. على قاعدةٍ "
        "جديدة قد تمرّ (الجدول غائب عند القراءة) وعلى قاعدةٍ قائمة تُسقِط التمهيد "
        "(`column … does not exist`):\n  " + "\n  ".join(offenders)
    )


def test_the_checker_actually_sees_the_tree() -> None:
    """الشاهدُ الموجب — بدونه يخضرّ التأكيد أعلاه على شجرةٍ لم تُقرأ.

    لو تبدّل شكلُ البيان أو نمطُ `CREATE INDEX` فهبط الجردُ إلى صفر، لبقي «لا مخالفات»
    صادقاً وهو يحرس لا شيء. المقيس على الشجرة: ٤٤٨ فهرساً بقائمةٍ بسيطة و٤٥١ إجمالاً؛
    الأرضيّة أدناه دون ذلك بهامشٍ لا يُحمِّر على حذفٍ عاديّ ويُحمِّر على انهيار القارئ.
    """
    refs = index_column_references()
    judged = [r for r in refs if r[3] in known_columns()]
    assert len(refs) >= 300, f"القارئ لا يرى الفهارس ({len(refs)}) — تبدّل نمطٌ ما"
    assert len(judged) >= 250, f"القارئ يعرف تعريفَ {len(judged)} جدولاً فقط — انهار مُجمِّع الأعمدة"


def test_the_incident_shape_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """إعادةُ إنتاج العطل بعينه على بيانٍ مصطنع: الحارسُ يجب أن يحمرّ عليه."""
    mig = tmp_path / "migrations"
    mig.mkdir()
    (mig / "a_index.sql").write_text(
        "DO $$ BEGIN IF to_regclass('market_price_history') IS NOT NULL THEN\n"
        "CREATE INDEX IF NOT EXISTS idx_x ON market_price_history(crop_type, recorded_at DESC);\n"
        "END IF; END $$;\n",
        encoding="utf-8",
    )
    (mig / "b_table.sql").write_text(
        "CREATE TABLE IF NOT EXISTS market_price_history (\n"
        "  price_id UUID PRIMARY KEY, category TEXT NOT NULL,\n"
        "  price_usd NUMERIC(14,4) NOT NULL CHECK (price_usd >= 0), recorded_date DATE NOT NULL\n"
        ");\n",
        encoding="utf-8",
    )
    (mig / "MANIFEST.txt").write_text("a_index.sql\nb_table.sql\n", encoding="utf-8")
    monkeypatch.setattr("tests.test_migration_index_columns_exist.MIGRATIONS", mig)
    monkeypatch.setattr("tests.test_migration_index_columns_exist.MANIFEST", mig / "MANIFEST.txt")
    with pytest.raises(AssertionError, match="crop_type"):
        test_every_indexed_column_is_defined_by_some_migration_of_its_table()
