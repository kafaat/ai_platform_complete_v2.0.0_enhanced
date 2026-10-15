#!/usr/bin/env python3
"""راتشِت الدَّين: اختبارٌ على اتّصال وهميّ يدّعي سلوكاً تفرضه القاعدة —
``FAKE-CONNECTION-ENFORCES-NOTHING-01``.

**الحادثة التي أوجبته، لا فرضيّة.** بعد تطبيق ٢٢٦ هجرة على PG16 نظيفة وتشغيل
الرحلة القانونيّة، تعطّلت **أربع مرّات متتالية بأربعة أسباب مختلفة**، كلّ إصلاح يكشف
الذي بعده. وكلّها كانت خضراء سنةً كاملة على وهميّ. أخطرها ``jsonb``: asyncpg يُعيده
**نصّاً** ما لم يُسجَّل codec، والوهميّ يُعيد ``dict`` — فما مرّ في الاختبار انهار حيّاً.

والسجلّ سمّى ما لم يُقَس صراحةً: «**كم اختباراً في هذا المستودع يعتمد على وهميّ لا
يفرض ما تفرضه القاعدة… السطح غير ممسوح**». هذا الملفّ يمسحه.

**ما يقيسه بالضبط:** ملفّات الاختبار التي تُعرّف/تستعمل اتّصالاً أو مسبحاً وهميّاً،
ومنها المجموعة الأخطر: ما يذكر أيضاً دلالةً **تفرضها القاعدة ولا يفرضها الوهميّ**
(``CHECK`` · ``TRIGGER`` · ``UNIQUE``/``ON CONFLICT`` · ``jsonb`` · ``FK``). خضرة هذه
لا تقول شيئاً عن سلوك القاعدة.

**وهو راتشِت لا بوّابة نظافة:** الأساس المُعلَن **يمنع النموّ ولا يدّعي أنّ ما فيه
سليم**. المُدرَجون لم يُثبَت انهيارهم؛ ثبت فقط أنّ خضرتهم لا تُثبِت العكس. وإخراج
ملفّ من الدَّين يكون **بإثباته على قاعدة حيّة**، لا بحذف الكلمة من نصّه.

**يعدّ صنفاً لا اسماً (FAKE-CONNECTION-RATCHET-COUNTS-A-NAMING-CONVENTION-NOT-A-CLASS-01).**
كان الماسح نمطاً نصّيّاً على اصطلاح التسمية (``class _?Fake…(Conn|Pool)`` · ``fake_conn…``
· ``fake_pool…``)، فاختبارٌ يُسمّي بديلَه ``_Conn`` أو ``fake_tenant_connection`` ويدّعي
مُسنَد المستأجِر أو JSONB نصّاً كان خارج العدّ. الكشفُ الآن **بنيويّ بـAST**
(``_stand_in_evidence``)، والقاعدة مكتوبة هناك بحدودها؛ والأساسُ لا ينمو إلّا بقيدٍ
مُبرَّر في ``admissions`` لا تكتبه ``--generate``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]


def with_carried_stamp(path, document: dict) -> dict:
    """ختمُ ``measured_on`` يتبع الحمولة لا HEAD (``deterministic_time.with_carried_stamp``).

    الاستيرادُ **كسولٌ عند الكتابة** لا عند التحميل: شواهدُ تنسخ هذا الملفّ وحده إلى شجرةٍ
    مؤقّتة وتُحمّله محرّكاً للقراءة (``build_main_inventory``) — واستيرادٌ عند التحميل أسقطها
    ``ENGINE_UNLOADABLE`` (CI على #1124). وفي نسخةٍ معزولةٍ بلا الوحدة يبقى السلوكُ السابق
    (ختمٌ طازج)؛ في المستودع الوحدةُ موجودةٌ دائماً.
    """
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from deterministic_time import with_carried_stamp as carry
    except ImportError:
        return document
    return carry(path, document)


BASELINE = ROOT / "docs" / "architecture" / "fake_connection_debt.json"

# ─────────────── الصنف لا الاسم: ما هو «بديلُ اتّصالٍ/مسبح» بنيويّاً ───────────────
#
# كان هنا نمطٌ نصّيّ على الاصطلاح (`_FakeConn` · `fake_pool`) فعدَّ ٤٠ ملفّاً وأعمى عن
# مثلها بأسماء أخرى (`_Conn` · `Connection` · `fake_tenant_connection`) — وهي تدّعي
# دلالاتِ القاعدة نفسها. القاعدة الآن على **شكل** البديل في الشجرة النحويّة، وكلُّ
# قناةٍ أدناه دليلٌ يُطبَع باسمه في رسالة الفشل:
#
# ① **صنفُ اتّصال:** صنفٌ يُعرِّف طرائق asyncpg. طريقةُ استعلام (`_QUERY_METHODS`) تُحسَب
#    فقط إن **قبلت جملةً** (وسيطاً موضعيّاً بعد `self` أو `*args`) — فـ`Skill.execute(self)`
#    و`_Pipe.execute(self)` (خطّ Redis) لا تُحسَبان. ويُعَدّ الصنفُ بديلاً إن **رسا** على
#    توقيع asyncpg: طريقةُ استعلامٍ وسيطُها الأوّل باسم جملة (`sql`/`query`/`q`/`stmt`/
#    `statement`) أو `*args` وحده — `(query, *args)` — أو `transaction(self)` بلا وسيطٍ
#    موضعيّ. فعميلُ HTTP بـ`fetch(self, url)` + `execute(self, request)` لا يُعَدّ ولو حمل
#    اسمين، ولا Redis بـ`transaction(self, func, *watches)`. (مقيس: كلُّ صنفٍ عُدَّ على
#    main@5472740e راسٍ بهذا — لم يحتج واحدٌ إلى «اسمين» بلا مرساة.)
#    **ويُستثنى الوكيل:** صنفٌ تُحيل طريقتُه إلى `self.<x>.<الطريقة نفسها>(…)` يلفّ اتّصالاً
#    قائماً (حقيقيّاً في `test_decision_sor_role_certify_pg.py`)، فليس بديلاً.
# ② **صنفُ مسبح:** صنفٌ يُعرِّف `acquire` — ما لم يكن قفلاً (`locked`، أو `release(self)`
#    بلا اتّصالٍ يُعاد) — وما لم يكن **مُحوِّلاً** يأخذ اتّصالاً في `__init__` في ملفٍّ يفتح
#    اتّصالاً حقيقيّاً (`asyncpg.connect`/`create_pool`): ذاك يلفّ القاعدة لا يُزيّفها.
# ③ **ترقيعُ مُورِّد الاتّصال:** `monkeypatch.setattr`/`patch`/`patch.object` على اسمٍ في
#    `_DB_SUPPLIERS` — ما لم يكن البديلُ يبلغ مُشغِّلاً حقيقيّاً (يُتتبَّع عبر الدوالّ المحلّيّة):
#    `test_migration_033_pg16.py` يُرقّع `_connect` باتّصال PG16 حيّ، فليس وهميّاً.
# ④ **محاكاةٌ مُهيَّأة:** كائنٌ تُسنَد إليه طريقتان من طرائق الاتّصال على الأقلّ
#    (`conn.fetchrow = …` · `conn.transaction.return_value = …`)، أو نداءٌ بوسيطين مُسمَّيين
#    منها (`SimpleNamespace(fetchrow=…, execute=…)`)، أو `spec=` يُسمّي asyncpg/Connection/Pool.
#
# ولأنّ الكشف على الشجرة النحويّة لا النصّ، فاسمُ ملفّ الأساس في سلسلةٍ نصّيّة لم يعد
# «استعمالاً» (الصنف الذي وقع فيه شاهدُ `no_report_only_change_guard` أدناه).
_QUERY_METHODS = frozenset(
    {
        "fetch",
        "fetchrow",
        "fetchval",
        "execute",
        "executemany",
        "copy_records_to_table",
        "copy_to_table",
        "copy_from_query",
    }
)
_CONN_METHODS = frozenset({"transaction", "cursor", "prepare"})
_STATEMENT_PARAM = re.compile(r"^_*(sql|query|q|stmt|statement)(_\w+)?$")
_DB_SUPPLIERS = frozenset(
    {
        "get_pool",
        "_get_pool",
        "get_db_pool",
        "create_pool",
        "tenant_connection",
        "get_tenant_connection",
        "acquire",
        "_connect",
        "get_connection",
    }
)
_MOCK_SPEC = re.compile(r"asyncpg|Connection|Pool")

# الحارس واختباره يحويان الرموز **بوصفها موضوعهما** — زرعاتٌ في مستودعات مؤقّتة
# وشرحٌ للحادثة. حارسٌ يُطلِق على توثيق ما يمنعه يُعطَّل في أوّل يوم، وهو عطل تكرّر
# في هذا المستودع (`probe_leak_guard` وقع فيه بعد `#802`) — **ووقعتُ فيه هنا عند أوّل
# تشغيل للمكنسة**: أدرج الأساسُ اختبارَ الحارس ديناً بـCHECK/UNIQUE/jsonb.
# الاستثناء بالمسار لا بالتخمين، ومقصورٌ على المُعدَّدين في `_SELF` أدناه (ثلاثة —
# الحارسُ واختبارُه والشاهدُ المذكور بعدُ)؛ كان التعليقُ يقول «الاثنين» بعد أن صاروا ثلاثة
# (مراجعة Copilot ٦ على #1012).
#
# **وثالثٌ وقع بالصنف نفسه — مقيسٌ على #1012 (مراجعة Copilot ٥):** شاهدُ حارس «لا تقارير
# فقط» يُسمّي `fake_connection_debt.json` **مساراً في وسائطِ حالةٍ ونصِّ تعليق** — واسمُ
# الأساس نفسُه يطابق `fake_conn\w*`. فأدرجه التوليدُ ديناً وهو لا يُنشئ اتّصالاً وهميّاً
# ولا يستعمله. أي أنّ **اسمَ الملفّ الذي يحمل الجردَ يقع في نمطِ ما يجرده**، فكلُّ شاهدٍ
# يُشير إليه مشروعاً يُلوَّث كذلك. الاستثناءُ هنا علاجُ الحالة؛ والعلاجُ البنيويّ — ألّا
# يُحسَب **مسارٌ نصّيّ** استعمالاً — مسجَّلٌ حدّاً في `gaps/registry.md`.
_SELF = {
    "scripts/ci/fake_connection_debt_guard.py",
    "tests_v9/test_fake_connection_debt_guard.py",
    "tests_v9/test_no_report_only_change_guard.py",
}

# دلالات تفرضها القاعدة ولا يفرضها أيّ وهميّ.
_DB_ENFORCED = {
    "CHECK": re.compile(r"\bCHECK\s*\(|\bcheck constraint\b|\bchk_\w+", re.I),
    "TRIGGER": re.compile(r"\bTRIGGER\b|\btrg_\w+", re.I),
    "UNIQUE": re.compile(r"\bUNIQUE\s*\(|\bON CONFLICT\b|\bduplicate key\b", re.I),
    "jsonb": re.compile(r"\bjsonb\b", re.I),
    "FK": re.compile(r"\bREFERENCES\s+\w+|\bforeign key\b", re.I),
}

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _statement_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[str], bool]:
    """الوسائط الموضعيّة بعد ``self`` وهل تُقبَل ``*args`` — أي: هل تقبل الطريقةُ جملة؟"""
    names = [a.arg for a in (*fn.args.posonlyargs, *fn.args.args)][1:]
    return names, fn.args.vararg is not None


def _delegates_to_wrapped(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """``self._c.fetch(…)`` داخل ``fetch`` ⇒ وكيلٌ يلفّ اتّصالاً قائماً، لا بديلٌ عنه."""
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == fn.name
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
        ):
            return True
    return False


def _connection_shape(cls: ast.ClassDef) -> list[str] | None:
    """القناة ①: إشارات الاتّصال التي يُعرِّفها الصنف، أو ``None`` إن لم يكن بديلَ اتّصال.

    **مرساةُ البديل توقيعُ asyncpg لا اسمُ الطريقة:** طريقةُ استعلامٍ وسيطُها الأوّل جملةٌ
    (``sql``/``query``/…) أو ``*args`` وحده، أو ``transaction`` بلا وسيطٍ موضعيّ. وما عداها
    إشاراتٌ تُطبَع دليلاً ولا تكفي وحدها — فـ``fetch(self, url)`` + ``execute(self, request)``
    (عميل HTTP) لا يُعَدّ، ولا ``transaction(self, func, *watches)`` (Redis).
    """
    signals: set[str] = set()
    anchored = False
    for fn in cls.body:
        if not isinstance(fn, _FUNCS):
            continue
        if fn.name in _QUERY_METHODS:
            if _delegates_to_wrapped(fn):
                return None
            params, varargs = _statement_params(fn)
            if not params and not varargs:
                continue  # `execute(self)` — مهمّةٌ أو خطّ Redis، لا جملة
            signals.add(fn.name)
            if (params and _STATEMENT_PARAM.match(params[0])) or (not params and varargs):
                anchored = True
        elif fn.name in _CONN_METHODS:
            signals.add(fn.name)
            if fn.name == "transaction" and _statement_params(fn) == ([], False):
                anchored = True
    return sorted(signals) if anchored else None


def _pool_shape(cls: ast.ClassDef, opens_real_driver: bool) -> bool:
    """القناة ②: ``acquire`` بلا شكل قفل، وليس مُحوِّلاً حول اتّصالٍ حقيقيّ."""
    methods = {fn.name: fn for fn in cls.body if isinstance(fn, _FUNCS)}
    if "acquire" not in methods or "locked" in methods:
        return False
    release = methods.get("release")
    if release is not None and _statement_params(release) == ([], False):
        return False  # `Lock.release(self)` — لا اتّصال يُعاد إلى مسبح
    init = methods.get("__init__")
    if opens_real_driver and init is not None and _statement_params(init) != ([], False):
        return False  # `_Pool(conn)` حول `asyncpg.connect(...)` — يلفّ القاعدة لا يُزيّفها
    return True


def _is_driver(expr: ast.expr) -> bool:
    """``asyncpg.connect`` / ``asyncpg.create_pool`` (أو ``x.asyncpg.connect``) — بلا ``unparse``."""
    return (
        isinstance(expr, ast.Attribute)
        and expr.attr in ("connect", "create_pool")
        and (
            (isinstance(expr.value, ast.Name) and expr.value.id == "asyncpg")
            or (isinstance(expr.value, ast.Attribute) and expr.value.attr == "asyncpg")
        )
    )


def _call_kind(func: ast.expr) -> str | None:
    """``setattr`` · ``patch`` · ``patch.object`` — من ذيل النداء، أيّاً كان مُستقبِله."""
    if isinstance(func, ast.Name):
        return func.id if func.id in ("setattr", "patch") else None
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr in ("setattr", "patch"):
        return func.attr
    if func.attr == "object" and _call_kind(func.value) == "patch":
        return "patch.object"
    return None


def _patched_name(call: ast.Call) -> str | None:
    """اسمُ الهدف المُرقَّع في ``setattr``/``patch``/``patch.object``، إن كان ثابتاً نصّيّاً."""
    kind = _call_kind(call.func)
    args = call.args

    def const(i: int) -> str | None:
        if len(args) > i and isinstance(args[i], ast.Constant) and isinstance(args[i].value, str):
            return args[i].value
        return None

    if kind == "setattr":
        if len(args) >= 3:  # setattr(obj, "name", new)
            return const(1)
        dotted = const(0)  # monkeypatch.setattr("pkg.mod.name", new)
        return dotted.rsplit(".", 1)[-1] if dotted else None
    if kind == "patch.object":
        return const(1)
    if kind == "patch":
        target = const(0)
        return target.rsplit(".", 1)[-1] if target else None
    return None


def _replacement(call: ast.Call) -> ast.expr | None:
    kind = _call_kind(call.func)
    for kw in call.keywords:
        if kw.arg in ("new", "side_effect", "return_value"):
            return kw.value
    if kind == "setattr":
        if len(call.args) >= 3:
            return call.args[2]
        return call.args[1] if len(call.args) == 2 else None
    if kind == "patch.object":
        return call.args[2] if len(call.args) >= 3 else None
    return call.args[1] if len(call.args) >= 2 else None


#: شرطٌ **لازمٌ** لا كاشف: كلُّ قناةٍ تتطلّب في المصدر أحدَ هذه الأشكال — ``def fetch``
#: (①②) · اسمَ مُورِّدٍ داخل سلسلة (③) · ``fetch=``/``.fetch… =``/``spec=`` (④). ملفٌّ يخلو
#: منها كلّها لا يُعرَب أصلاً، فتبقى كلفة المسح ثانيةً لا عشرين على ~١٨٠٠ ملفّ.
_SHAPE_NAMES = "|".join(sorted(_QUERY_METHODS | _CONN_METHODS | {"acquire"}))
_NECESSARY = tuple(  # أنماطٌ منفصلة لا تناوبٌ واحد: التناوب يتراجع عند كلّ علامة اقتباس (×٣ أبطأ)
    re.compile(rx)
    for rx in (
        rf"\bdef\s+({_SHAPE_NAMES})\b",
        rf"[\"'][\w.]*\b({'|'.join(sorted(_DB_SUPPLIERS))})[\"']",
        rf"\b({_SHAPE_NAMES})\b[\w.]*\s*=(?!=)",
        r"\bspec\s*=\s*[\w.]*(asyncpg|Connection|Pool)",
    )
)


def _stand_in_evidence(tree: ast.AST) -> list[str]:
    """القاعدة البنيويّة كلّها — يُرجِع الأدلّة (فارغةً إن لم يكن في الملفّ بديلُ اتّصال)."""
    defs: dict[str, list[ast.AST]] = {}
    classes: list[ast.ClassDef] = []
    calls: list[ast.Call] = []
    assigns: list[ast.Assign] = []
    for node in ast.walk(tree):  # مرورٌ واحد؛ والباقي على القوائم
        if isinstance(node, _FUNCS):
            defs.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            classes.append(node)
        elif isinstance(node, ast.Call):
            calls.append(node)
        elif isinstance(node, ast.Assign):
            assigns.append(node)

    def reaches_driver(node: ast.AST, seen: frozenset[str] = frozenset()) -> bool:
        """يبلغ ``asyncpg.connect``/``create_pool`` مباشرةً أو عبر دالّةٍ محلّيّة."""
        if _is_driver(node):
            return True
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if _is_driver(sub.func):
                return True
            name = sub.func.id if isinstance(sub.func, ast.Name) else None
            if name in defs and name not in seen:
                if any(reaches_driver(d, seen | {name}) for d in defs[name]):
                    return True
        return False

    opens_real_driver = any(_is_driver(c.func) for c in calls)
    evidence: list[str] = []
    shape = _QUERY_METHODS | _CONN_METHODS | {"acquire"}
    for cls in classes:
        signals = _connection_shape(cls)
        if signals:
            evidence.append(f"class {cls.name}({', '.join(signals)})")
        if _pool_shape(cls, opens_real_driver):
            evidence.append(f"pool {cls.name}(acquire)")
    for call in calls:
        target = _patched_name(call)
        if target in _DB_SUPPLIERS:
            new = _replacement(call)
            key = (
                new.id
                if isinstance(new, ast.Name)
                else new.attr
                if isinstance(new, ast.Attribute)
                else None
            )
            if key in defs:
                real = any(reaches_driver(d) for d in defs[key])
            else:
                real = new is not None and reaches_driver(new)
            if not real:
                evidence.append(f"patched {target}")
        named = sorted({kw.arg for kw in call.keywords if kw.arg} & shape)
        if len(named) >= 2:
            evidence.append(f"stub {ast.unparse(call.func)}({', '.join(named)})")
        for kw in call.keywords:
            if kw.arg == "spec" and _MOCK_SPEC.search(ast.unparse(kw.value)):
                evidence.append(f"spec {ast.unparse(kw.value)}")
    configured: dict[str, set[str]] = {}
    for assign in assigns:
        for target_node in assign.targets:
            cur = target_node
            while isinstance(cur, ast.Attribute):
                if cur.attr in shape and isinstance(cur.value, ast.Name | ast.Attribute):
                    configured.setdefault(ast.unparse(cur.value), set()).add(cur.attr)
                    break
                cur = cur.value
    for base, attrs in sorted(configured.items()):
        if len(attrs) >= 2:
            evidence.append(f"mock {base}({', '.join(sorted(attrs))})")
    return evidence


def _release_tracked_tests(base: Path) -> list[str]:
    """Delivery-ZIP fallback: derive membership from the sealed Release manifest.

    The delivery intentionally omits ``.git``.  Falling back to a raw filesystem walk
    would let ungoverned/package-only files enter the survey, so the fallback is the
    release membership list itself and every scanned candidate is digest-verified
    before it is trusted.
    """
    manifest = base / "release" / "FILE_CHECKSUMS.sha256"
    if not manifest.is_file():
        raise RuntimeError(
            "fake_connection_debt_guard requires either a Git index or "
            "release/FILE_CHECKSUMS.sha256"
        )

    tests: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            expected, rel = raw.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError(f"malformed release checksum entry: {raw!r}") from exc
        if not (rel.endswith(".py") and "test" in rel):
            continue
        if not rel.startswith(("tests_v9/", "tests/", "services/")):
            continue
        path = base / rel
        if not path.is_file():
            raise RuntimeError(f"release-tracked test is missing: {rel}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"release-tracked test digest mismatch: {rel} expected={expected} actual={actual}"
            )
        tests.append(rel)
    if not tests:
        raise RuntimeError("release manifest yielded zero tracked Python tests")
    return sorted(tests)


def _git_tracked_tests(base: Path, *pathspecs: str) -> list[str] | None:
    cmd = ["git", "ls-files", *pathspecs]
    out = subprocess.run(
        cmd,
        cwd=base,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if out.returncode != 0:
        return None
    return [ln for ln in out.stdout.splitlines() if ln.endswith(".py") and "test" in ln]


def _tracked_tests() -> list[str]:
    tracked = _git_tracked_tests(ROOT, "tests_v9", "tests", "services")
    if tracked is not None:
        return tracked
    return _release_tracked_tests(ROOT)


def survey(root: Path | None = None) -> dict:
    """يُرجِع المسح: كلّ من يستعمل وهميّاً، ومن يدّعي منهم دلالة قاعدة (مع سببها).

    ``evidence`` يُسمّي لكلّ ملفّ ما رآه الماسح فيه (يُطبَع في الفشل، ولا يُكتَب في الأساس)،
    و``unparsed`` ملفّاتٌ لم تُعرَب — لا تُعَدّ «نظيفة» بل تُحجَب: ما لم يُرَ لم يُقَس.
    """
    base = root or ROOT
    fake: list[str] = []
    claiming: dict[str, list[str]] = {}
    evidence: dict[str, list[str]] = {}
    unparsed: list[str] = []
    for rel in _tracked_tests() if base == ROOT else _tracked_in(base):
        if rel in _SELF:
            continue
        path = base / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not any(rx.search(text) for rx in _NECESSARY):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            unparsed.append(rel)
            continue
        seen = _stand_in_evidence(tree)
        if not seen:
            continue
        fake.append(rel)
        evidence[rel] = seen
        why = sorted(k for k, rx in _DB_ENFORCED.items() if rx.search(text))
        if why:
            claiming[rel] = why
    return {
        "fake": sorted(fake),
        "claiming": dict(sorted(claiming.items())),
        "evidence": dict(sorted(evidence.items())),
        "unparsed": sorted(unparsed),
    }


def _tracked_in(base: Path) -> list[str]:
    tracked = _git_tracked_tests(base)
    if tracked is not None:
        return tracked
    if base.resolve() == ROOT.resolve():
        return _release_tracked_tests(base)
    raise RuntimeError(f"cannot enumerate governed tests under {base}: no Git index is available")


def _load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _proof_covers(rel: str, entry: dict, claims: list[str]) -> list[str]:
    """هل يُخرِج هذا السداد الملفَّ من الدَّين فعلاً؟ المطلوب ثلاثة، وكلّها مقيسة.

    **لِمَ تُفحَص أصلاً:** المخرج الوحيد المُعلَن من الدَّين هو الإثبات الحيّ، ومدخلٌ
    يُكتَب باليد يستطيع أن يدّعيه بلا أن يفعله. فالمدخل الذي لا يُسمّي ملفَّ إثباتٍ
    قائماً **يذكر مصدره** ليس سداداً بل حذفٌ للكلمة من نصّه — وهو بالضبط ما يمنعه
    سطر العقد في `$comment`.
    """
    bad: list[str] = []
    proof = entry.get("proof", "")
    # المسار يُحَلّ ويُحصَر داخل `ROOT` قبل أيّ قراءة. العقد يقول «ملفّ إثبات **في
    # الشجرة**»، و`ROOT / proof` وحدها تقبل `../…` فتخرج منها — فيقرأ الحارسُ ملفّاً
    # خارج المستودع أثناء تشغيله. الاحتمال ضئيل (الأساس مُلتزَم ومُراجَع) لكنّ الحصر
    # مجّانيّ، وحدُّ العقد يُفرَض بدل أن يُفترَض. (لاحظه Copilot.)
    resolved = (ROOT / proof).resolve() if proof else None
    inside = resolved is not None and resolved.is_relative_to(ROOT.resolve())
    if not inside:
        bad.append(f"✗ {rel} — `proof` يخرج عن جذر المستودع أو فارغ: {proof or '—'}")
    elif not resolved.is_file():
        bad.append(f"✗ {rel} — `proof` لا يُسمّي ملفّاً قائماً: {proof}")
    elif rel not in resolved.read_text(encoding="utf-8", errors="ignore"):
        bad.append(
            f"✗ {rel} — ملفّ الإثبات `{proof}` لا يذكره. الربط يُقاس ولا يُدَّعى: "
            "مدخلٌ يشير إلى إثباتٍ لا يعرف مصدره يُسدّد ديناً لم يُقَس."
        )
    declared_claims = sorted(entry.get("claims", []))
    if declared_claims != sorted(claims):
        bad.append(
            f"✗ {rel} — السداد يغطّي {declared_claims or '—'} والمقيس الآن "
            f"{sorted(claims)}. ادّعاءٌ جديد في ملفّ مُسدَّد يُعيد فتح الدَّين؛ "
            "غطِّه حيّاً ثمّ حدّث `claims`."
        )
    if len((entry.get("evidence") or "").strip()) < 30:
        bad.append(f"✗ {rel} — سدادٌ بلا دليل مكتوب أقصر من تفسير")
    return bad


#: أدنى طولٍ لتبرير قبولِ دَين — سطرٌ أقصر من تفسيرٍ ليس تبريراً.
_MIN_JUSTIFICATION = 40


def _admission_problems(declared: dict) -> tuple[list[str], set[str]]:
    """سجلّ القبول: **النموّ لا يمرّ إلّا بقيدٍ مُبرَّر يُسمّي مواقعه** — ولا تكتبه `--generate`.

    **لِمَ وُجِد:** `fake_connection_tests` مُشتقّ، و`verify_all_generated --fix` يُعيد توليده،
    فكان «أعلِنه في الأساس» يعني عمليّاً إعادةَ توليدٍ تبتلع أيَّ وهميٍّ جديد بلا كلمة. وتصحيحُ
    القياس (الصنف لا الاسم) رفع العدّ فعلاً — فإمّا أن يمرّ الرفعُ صامتاً كأيّ نموّ، أو أن يكون
    للرفع طريقٌ مكتوبٌ يُراجَع. القيدُ: `kind` · `date` · `before`/`after` (والفرق = عدد
    `sites`) · `sites` (لا تكرار عبر القيود) · `justification` ≥ ``_MIN_JUSTIFICATION``.
    كلُّ موقعٍ يراه الماسح يجب أن يكون في قيدٍ ما؛ والقيود تاريخٌ لا تُحذَف بسداد الدَّين.
    """
    ledger = declared.get("admissions")
    if not isinstance(ledger, list) or not ledger:
        return [
            "✗ الأساس بلا `admissions` — لا سجلّ قبولٍ يُثبِت أنّ ما فيه دخل بقرارٍ مُبرَّر. "
            "إعادةُ التوليد لا تكتبه؛ استعِده من التاريخ."
        ], set()
    bad: list[str] = []
    admitted: set[str] = set()
    for i, entry in enumerate(ledger):
        label = f"admissions[{i}] ({entry.get('kind') or '—'})"
        sites = entry.get("sites")
        before, after = entry.get("before"), entry.get("after")
        if not isinstance(sites, list) or not all(isinstance(s, str) for s in sites):
            bad.append(f"✗ {label} — `sites` ليست قائمة مسارات")
            continue
        if not entry.get("kind") or not entry.get("date"):
            bad.append(f"✗ {label} — قيدٌ بلا `kind` أو `date`")
        if len((entry.get("justification") or "").strip()) < _MIN_JUSTIFICATION:
            bad.append(f"✗ {label} — قبولُ دَينٍ بلا تبريرٍ مكتوب أطول من سطر")
        if (
            not isinstance(before, int)
            or not isinstance(after, int)
            or after - before != len(sites)
        ):
            bad.append(
                f"✗ {label} — `before`→`after` ({before}→{after}) لا يطابق عدد المواقع "
                f"المُسمّاة ({len(sites)}). الزيادة تُعَدّ ولا تُقدَّر."
            )
        repeated = sorted((set(sites) & admitted) | {s for s in sites if sites.count(s) > 1})
        if repeated:
            bad.append(f"✗ {label} — مواقع مقبولةٌ مرّتين: {repeated}")
        admitted |= set(sites)
    return bad, admitted


def check() -> list[str]:
    """يُرجِع المخالفات. النموّ يُدان؛ والانكماش يُطالَب بتحديث الأساس."""
    found = survey()
    declared = _load_baseline()

    if not found["fake"]:
        return [
            "صفر ملفّ مفحوص — الماسح فقد عينه (تغيّرت بنية البدائل؟). "
            "أخضرٌ بصفر ليس نظافةً؛ صحّح `_stand_in_evidence` أو نطاق `git ls-files`."
        ]

    problems: list[str] = [
        f"✗ {rel} — لم يُعرَب (SyntaxError)؛ ما لم يُرَ لم يُقَس، فلا يُعَدّ نظيفاً."
        for rel in found["unparsed"]
    ]
    ledger_problems, admitted = _admission_problems(declared)
    problems.extend(ledger_problems)
    unadmitted = sorted(set(found["fake"]) - admitted)
    for rel in unadmitted:
        problems.append(
            f"✗ {rel} — بديلُ اتّصالٍ/مسبح خارج سجلّ القبول "
            f"({' · '.join(found['evidence'].get(rel, []))}). الدَّين راتشِت لا ينمو، و`--generate` "
            "لا يقبله: أزِل البديل، أو أضِف قيداً في `admissions` بتبريرٍ ومواقع."
        )
    new_fake = sorted(set(found["fake"]) - set(declared["fake_connection_tests"]))
    new_claim = sorted(set(found["claiming"]) - set(declared["claiming_db_enforced"]))
    gone_fake = sorted(set(declared["fake_connection_tests"]) - set(found["fake"]))
    gone_claim = sorted(set(declared["claiming_db_enforced"]) - set(found["claiming"]))

    # السداد الحيّ: ملفّ أُثبِتت **كلّ** ادّعاءاته التي تفرضها القاعدة يخرج من الدَّين
    # وهو ما يزال في `fake_connection_tests` — الوهميّ باقٍ لمنطق التطبيق، والمُسدَّد
    # هو الادّعاء عن القاعدة لا استعمال الوهميّ. وهذا القسم **لا يُشتقّ** بالماسح:
    # النصّ لا يتغيّر بالإثبات، فلا سبيل لاستنتاجه من الشجرة.
    proven = declared.get("proven_live", {})
    for rel, entry in sorted(proven.items()):
        if rel not in found["claiming"]:
            problems.append(
                f"✗ {rel} — سدادٌ لادّعاءٍ لم يعد الماسح يراه. مدخلٌ بائت يُوهِم بتغطية "
                "قائمة؛ احذفه أو أعِد الادّعاء."
            )
            continue
        problems.extend(_proof_covers(rel, entry, found["claiming"][rel]))

    for rel in new_claim:
        if rel in proven:
            continue
        problems.append(
            f"✗ {rel} — اختبارٌ على وهميّ يدّعي سلوكاً تفرضه القاعدة "
            f"({' · '.join(found['claiming'][rel])}). خضرتُه لا تقول شيئاً عن القاعدة. "
            "أثبِته على قاعدة حيّة، أو أعلِنه ديناً صراحةً في الأساس."
        )
    for rel in new_fake:
        if rel in new_claim or rel in unadmitted:
            continue
        problems.append(
            f"✗ {rel} — بديلٌ مقبولٌ في `admissions` غائبٌ عن `fake_connection_tests`؛ "
            "أعِد توليد الأساس بـ`--generate`."
        )
    if gone_fake or gone_claim:
        problems.append(
            "✗ الأساس صار أوسع من الواقع — حدّثه بما قِيس: "
            f"غادر الوهميّ {gone_fake or '—'} · غادر الادّعاء {gone_claim or '—'}. "
            "الأساس الذي يُبالغ يُدرَّب قارئه على تجاهله."
        )
    return problems


def _measured_on() -> str:
    """SHA الشجرة التي قِيس عليها الأساس — لأنّه **قياس** يَبيت بحركتها لا قرار."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return out.stdout.strip() or "unknown"


def outstanding(found: dict | None = None, declared: dict | None = None) -> dict[str, list[str]]:
    """الدَّين **القائم**: ما مسحه الماسح ناقص ما سُدِّد حيّاً.

    الرقم الذي يُراقَب هو هذا لا `claiming_db_enforced` الخام: الأخير مُشتقّ من النصّ،
    والنصّ لا يتغيّر بالإثبات — فلو رُبِط به الراتشِت لَما نزل أبداً مهما أُثبِت.
    """
    found = found or survey()
    declared = declared or _load_baseline()
    proven = declared.get("proven_live", {})
    return {
        rel: claims
        for rel, claims in found["claiming"].items()
        if sorted(proven.get(rel, {}).get("claims", [])) != sorted(claims)
    }


def _generate() -> None:
    found = survey()
    # `proven_live` قرارٌ مقيس لا مُشتقّ — يُحمَل عبر إعادة التوليد وإلّا محته أوّل
    # `--generate` ورجع الدَّين المُسدَّد صامتاً. (صنف «المصنوع يدهس المكتوب».)
    carried = _load_baseline().get("proven_live", {}) if BASELINE.exists() else {}
    # وكذلك `admissions`: سجلُّ قبولٍ مُبرَّر — لو اشتُقّ لابتلعت إعادةُ التوليد كلَّ نموّ.
    admissions = _load_baseline().get("admissions", []) if BASELINE.exists() else []
    BASELINE.write_text(
        json.dumps(
            with_carried_stamp(
                document={
                    "$comment": (
                        "FAKE-CONNECTION-ENFORCES-NOTHING-01 — أساس مُعلَن يمنع النموّ ولا "
                        "يدّعي أنّ ما فيه سليم. `claiming_db_enforced` مسحٌ خام مُشتقّ من "
                        "النصّ، والخروج منه يكون بإثبات الملفّ على قاعدة حيّة لا بحذف الكلمة "
                        "من نصّه — ويُعلَن السداد في `proven_live` (لا يُشتقّ: الإثبات الحيّ "
                        "لا يغيّر النصّ). الدَّين القائم = الأوّل ناقص الثاني، وهو المُراقَب. "
                        "`fake_connection_tests` يُكشَف بنيويّاً (صنفُ البديل لا اسمه)، ولا ينمو "
                        "إلّا بقيدٍ في `admissions` يُسمّي مواقعه ويُبرّرها — وهو لا يُشتقّ: "
                        "`--generate` يحمله ولا يكتبه، فإعادةُ التوليد لا تقبل ديناً."
                    ),
                    # مُشتقّ بماسحٍ من الشجرة ⇒ `measured` لا `decided`، فيلزمه أساسٌ
                    # يَبيت بحركتها. البيات يُبلَّغ ولا يحجب (سياسة `claim_base_guard`).
                    "measured_on": _measured_on(),
                    "fake_connection_tests": found["fake"],
                    "claiming_db_enforced": found["claiming"],
                    "proven_live": carried,
                    "admissions": admissions,
                },
                path=BASELINE,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args(argv)

    if args.generate:
        _generate()
        print(f"fake_connection_debt: كُتِب الأساس في {BASELINE.relative_to(ROOT)}")
        return 0

    problems = check()
    if problems:
        print("fake_connection_debt_guard FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    declared = _load_baseline()
    # الرقم المطبوع جزءٌ من الحارس: طباعة الخام وحده تقول «٨ ديون» بعد سدادها كلّها،
    # فتُدرِّب القارئ على تجاهُل العدّاد. الثلاثة تُطبَع كي يُقرأ السداد لا يُستنتَج.
    raw = len(declared["claiming_db_enforced"])
    paid = len(declared.get("proven_live", {}))
    print(
        "fake_connection_debt_guard_ok "
        f"(وهميّ: {len(declared['fake_connection_tests'])} · "
        f"يدّعي سلوك قاعدة: {raw} خاماً − {paid} مُسدَّداً حيّاً "
        f"⇒ {len(outstanding(declared=declared))} ديناً قائماً)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
