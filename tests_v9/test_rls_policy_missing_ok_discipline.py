"""انضباطُ ``missing_ok`` في كلّ ``current_setting('app.…')`` تنفيذيّ — راتشِتٌ عند الصفر.

``TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01`` — الصنفُ المسمّى صناعيّاً: عزلٌ
مبنيٌّ على ``current_setting('app.<اسم>')`` داخل سياسات RLS. والوسيطُ الثاني ليس تفصيلاً:

**مقيسٌ على PostgreSQL 16.13 بدورٍ مقيَّد (NOSUPERUSER · NOBYPASSRLS · لا يملك الجدول):**

    الحالة                          current_setting(n)      current_setting(n, true)
    ─────────────────────────────  ──────────────────────  ────────────────────────
    لم يُضبَط في الجلسة قطّ          ERROR 42704            NULL
    ضُبِط محلّيّاً ثمّ انتهت المعاملة   ''                     ''

فسياسةٌ بلا ``missing_ok`` **تُسقِط كلَّ استعلامٍ** على اتّصالٍ لم يُضبَط سياقُه — لا صفراً
صامتاً بل خطأً يكسر المسار — بينما مع ``true`` يصير الغيابُ ``NULL`` فرفضاً. والمقيسُ
اليوم أنّ **كلّ** نداءٍ تنفيذيٍّ في الهجرات يمرّر ``true`` (٥٢٩ نداءً على
``c1044010``)، وأنّ الستّة عشر الخالية منه كلَّها **في تعليقات** ``--``. فهذا راتشِتٌ
عند الصفر: أيُّ نداءٍ تنفيذيٍّ جديد بلا ``true`` يُحمِّره.

**لماذا تجريدُ التعليقات شرطٌ لا زينة:** مسحٌ نصّيٌّ ساذج يعدّ الستّة عشر مخالفاتٍ
فيُنشئ أساساً من نثرٍ لا يُنفَّذ — وأساسٌ من ضجيجٍ يُعلِّم القارئ تجاهلَ الحارس. ولماذا
**لا** يُجرَّد ما داخل ``$…$`` والسلاسل: عائلاتٌ كاملة من السياسات تُنشأ ديناميكيّاً
داخل ``format($p$…$p$)`` في كتل ``DO`` (``_sahool_apply_tenant_rls`` · v161–v163)،
فجسمُ الدولار هنا **شيفرة**، ومُجرِّدٌ يُسقطه يعمى عن أوسع عائلةٍ في الشجرة.

**وحدُّ الصدق:** يُثبِت الاختبارُ وجودَ ``missing_ok`` لا صحّةَ الاسم ولا صحّةَ السياسة.
ويبقى ``current_setting(n, true)::uuid`` بلا ``NULLIF`` (٢٩ جدولاً مقيساً) **صاخباً** على
``''`` بعد انتهاء المعاملة (22P02) — وذلك شكلٌ آخر يُقاس حيّاً في
``test_rls_tenant_isolation_live_pg.py`` لا هنا.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

#: المخالفاتُ المعروفة (``مسار:سطر``) — **فارغةٌ بالقياس**. تتقلّص ولا تنمو: مدخلٌ هنا
#: لم يعد يُرى يُحمِّر كذلك، كي لا يبقى أساسٌ بائتٌ يُقرأ ديناً قائماً.
_KNOWN_OFFENDERS: frozenset[str] = frozenset()

_CALL = re.compile(r"current_setting\s*\(", re.IGNORECASE)
_TRUE = re.compile(r"^true$", re.IGNORECASE)
_TENANT_NAMES = ("app.current_tenant", "app.tenant_id", "app.current_tenant_id")


def _sql_files() -> list[Path]:
    """النطاقُ **مُشتقٌّ لا مكتوب**: كلّ ``.sql`` تحت أيّ مجلّد ``migrations``.

    فهجرةُ خدمةٍ جديدة بمجلّدها الخاصّ تدخل النطاق بوجودها، ولا تنتظر من يُدرِجها.
    """
    out = set((ROOT / "migrations").rglob("*.sql"))
    for mig_dir in (ROOT / "services").rglob("migrations"):
        if mig_dir.is_dir() and "node_modules" not in mig_dir.parts:
            out.update(mig_dir.rglob("*.sql"))
    return sorted(out)


def executable_sql(text: str) -> str:
    """نصُّ SQL وقد أُفرِغت تعليقاتُه — **بالطول نفسِه والأسطر نفسِها** كي تبقى المواقع صادقة.

    يُفرَغ: ``-- …`` حتى نهاية السطر، و``/* … */``. ويُبقى: السلاسل ``'…'`` (قد تحمل SQL
    ديناميكيّاً بعلامات اقتباسٍ مضاعفة) وأجسام ``$tag$ … $tag$`` (plpgsql أو SQL
    ديناميكيّ) — مع إفراغ تعليقات ``--`` داخل الأجسام، فهي تعليقاتٌ هناك أيضاً.
    """
    chars = list(text)
    n = len(text)
    i = 0
    dollar: str | None = None

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if chars[k] != "\n":
                chars[k] = " "

    while i < n:
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if dollar is not None and text.startswith(dollar, i):
            i += len(dollar)
            dollar = None
            continue
        c = text[i]
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            # فاصلةٌ عليا داخل جسم دولارٍ هو **بيانات** (``COMMENT … IS $$it's$$``) ليست
            # سلسلة: لو تُبِعت لابتلعت وسمَ الإغلاق وانحرف المسح إلى نهاية الملفّ.
            if dollar is not None:
                close = text.find(dollar, i)
                if close != -1 and close < j:
                    i += 1
                    continue
            i = j + 1
            continue
        if dollar is None:
            m = re.match(r"\$[A-Za-z_0-9]*\$", text[i:])
            if m:
                dollar = m.group(0)
                i += len(dollar)
                continue
        i += 1
    return "".join(chars)


def _args(text: str, start: int) -> tuple[str, int]:
    """وسائطُ النداء بين القوسين المتوازنين، ونهايتُها."""
    depth, j = 1, start
    while j < len(text) and depth:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
        j += 1
    return text[start : j - 1], j


def _split_top_level(args: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in args:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur).strip())
    return parts


def classify(args: str) -> tuple[str | None, bool]:
    """(اسمُ الـGUC إن كان حرفيّاً، وهل مُرِّر ``missing_ok=true``).

    الاقتباسُ المضاعف (``''app.x''``) يُطبَّع قبل القراءة: هكذا يظهر النداء داخل سلسلةٍ
    تُمرَّر إلى ``format``/``EXECUTE``.
    """
    parts = _split_top_level(args.replace("''", "'"))
    first = re.sub(r"::\s*text\s*$", "", parts[0], flags=re.IGNORECASE).strip()
    m = re.fullmatch(r"'([^']+)'", first)
    name = m.group(1) if m else None
    missing_ok = len(parts) >= 2 and bool(_TRUE.match(parts[1].strip()))
    return name, missing_ok


def scan(text: str, rel: str) -> tuple[list[str], list[str]]:
    """(المخالفات ``مسار:سطر ⇒ مقطع``، أسماء الـGUC المقروءة) في نصّ ملفّ واحد.

    مخالفةٌ = نداءٌ باسمٍ مخصَّص (فيه نقطة — فالمدمجة تُعرَّف دائماً) أو باسمٍ ديناميكيّ
    لا يُقرَأ ساكناً، **بلا** ``true`` ثانياً.
    """
    code = executable_sql(text)
    offenders, names = [], []
    for m in _CALL.finditer(code):
        args, _end = _args(code, m.end())
        name, missing_ok = classify(args)
        if name is not None:
            names.append(name)
        custom = name is None or "." in name
        if custom and not missing_ok:
            line = code.count("\n", 0, m.start()) + 1
            offenders.append(f"{rel}:{line} ⇒ current_setting({' '.join(args.split())[:60]})")
    return offenders, names


def _tree_scan() -> tuple[set[str], list[str], int]:
    offenders: set[str] = set()
    names: list[str] = []
    calls = 0
    for path in _sql_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        found, seen = scan(text, rel)
        offenders.update(o.split(" ⇒ ", 1)[0] for o in found)
        names.extend(seen)
        calls += len(_CALL.findall(executable_sql(text)))
    return offenders, names, calls


def test_no_executable_current_setting_on_a_custom_guc_lacks_missing_ok():
    """الراتشِت: لا مخالفةَ جديدة، ولا مخالفةَ مُدرَجةً أُصلِحت وما تزال في الأساس."""
    offenders, _names, _calls = _tree_scan()
    new = sorted(offenders - _KNOWN_OFFENDERS)
    assert not new, (
        "current_setting('app.…') تنفيذيٌّ بلا missing_ok=true:\n  "
        + "\n  ".join(new)
        + "\nعلى اتّصالٍ لم يُضبَط سياقُه يرفع 42704 فيكسر كلّ استعلامٍ على الجدول. "
        "مرِّر `true` ثانياً (ولُفَّه بـNULLIF إن قورن بعد تحويل نوع)."
    )
    stale = sorted(_KNOWN_OFFENDERS - offenders)
    assert not stale, f"أساسٌ بائت — مواضع أُصلِحت وما تزال مُدرَجة: {stale}"


def test_the_scanner_reads_the_policy_families_it_claims_to_guard():
    """**أخضرُ بصفرٍ مفحوص هو الصمت الذي يوجد الراتشِت لمنعه.**

    يُشترَط أن يرى الماسحُ الأسماءَ الثلاثة كلَّها — ومنها ``app.current_tenant_id`` الذي
    لا يظهر إلّا داخل ``format($p$…$p$)`` في v161–v163 — وأن يعدّ نداءاتٍ بمئاتها.
    مُجرِّدٌ يُفرِغ أجسامَ الدولار كان يُسقط هذه العائلة كلَّها ويمرّ أخضر.
    """
    _offenders, names, calls = _tree_scan()
    missing = [n for n in _TENANT_NAMES if n not in names]
    assert not missing, f"الماسح لا يرى عائلات: {missing} — مجرِّد التعليقات أكل شيفرة"
    assert calls >= 300, f"انهار المسح إلى {calls} نداءً — تضييقٌ صامت"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        pytest.param(
            "CREATE POLICY p ON t USING (tenant_id::text = current_setting('app.current_tenant'));",
            1,
            id="bare-call-in-code",
        ),
        pytest.param(
            "CREATE POLICY p ON t USING (tenant_id = current_setting('app.x', false)::uuid);",
            1,
            id="explicit-false",
        ),
        pytest.param(
            "DO $$ BEGIN EXECUTE format($p$CREATE POLICY p ON %I USING "
            "(tenant_id = current_setting('app.current_tenant_id'))$p$, 't'); END $$;",
            1,
            id="inside-dollar-quoted-dynamic-policy",
        ),
        pytest.param(
            "DO $$ BEGIN EXECUTE format('CREATE POLICY p ON %I USING "
            "(tenant_id::text = current_setting(''app.tenant_id''))', 't'); END $$;",
            1,
            id="inside-single-quoted-dynamic-policy",
        ),
        pytest.param(
            "CREATE POLICY p ON t USING (x = current_setting(v_name));",
            1,
            id="dynamic-name-without-missing-ok",
        ),
        pytest.param(
            "-- current_setting('app.current_tenant') fail-closed prose\n"
            "/* current_setting('app.tenant_id') */ SELECT 1;",
            0,
            id="comments-are-not-code",
        ),
        pytest.param(
            "CREATE POLICY p ON t USING (tenant_id::text = "
            "NULLIF(current_setting('app.current_tenant'::text, TRUE), ''));",
            0,
            id="missing-ok-true-with-cast",
        ),
        pytest.param(
            "SELECT current_setting('server_version_num')::int;",
            0,
            id="builtin-guc-always-defined",
        ),
        pytest.param(
            "SELECT '-- not a comment', current_setting('app.current_tenant');",
            1,
            id="dashes-inside-a-literal-do-not-start-a-comment",
        ),
    ],
)
def test_the_detector_is_falsifiable(sql: str, expected: int):
    """**التكذيب داخل الجناح:** كلُّ شكلٍ مخالف يُمسَك، وكلُّ شكلٍ سليم يمرّ.

    بلا هذا لا يُعرَف أنّ خضرة الراتشِت خبرٌ عن الهجرات لا عن ماسحٍ أعمى.
    """
    offenders, _names = scan(sql, "probe.sql")
    assert len(offenders) == expected, offenders


def test_offender_locations_survive_comment_blanking():
    """الموقعُ المُبلَّغ سطرُ النداء في الملفّ الأصليّ — الإفراغ يحفظ الأسطر."""
    sql = "-- l1\n/* l2\n l3 */\nSELECT current_setting('app.current_tenant');\n"
    offenders, _ = scan(sql, "probe.sql")
    assert offenders and offenders[0].startswith("probe.sql:4 "), offenders
