#!/usr/bin/env python3
"""حارس نطاق GUC المستأجِر — شجريّ لا ملفٌّ واحد. ``GUC-SCOPE-GUARD-SEES-ONE-FILE-01``.

**العطل الإنتاجيّ المقيس:** ``set_config('app.current_tenant', $1, true)`` يضبط الـGUC
بنطاق **المعاملة**. وasyncpg بلا معاملة صريحة يعمل في وضع autocommit — فكلّ استدعاء
معاملةٌ مستقلّة، ويضيع الضبط **قبل الاستعلام التالي** ⇒ RLS يُرجِع صفر صفوف ⇒ هندسة
فارغة. وقعت فعلاً في ``fetch_field_geometry`` (بلاطة bbox بلا قصّ على المضلّع).

**ولماذا لم يُمسَك على مستوى الشجرة:** الحارس القائم
(``services/raster-service/test_tenant_guc_session_scope_guard.py``) يحمل التشخيص
الصحيح مكتوباً، **لكنّ تأكيده regex على ``db_persist.py`` وحده**. وثانياً
``scripts/tenant_query_audit.py`` كان يمنح ``EXPLICIT`` لأيّ دالّة فيها ``set_config``
— **يفحص الوجود لا النطاق**، فيُعطي كلّ موضعٍ معيب شهادة سلامة.

**الخاصّيّة المقيسة هنا — نطاقٌ لا وجود:** كلّ ``set_config(..., true)`` يجب أن يقع
**داخل كتلة معاملة** (``async with conn.transaction():`` أو ما يكافئها). خارجها الضبط
عديم الأثر على الاستعلام التالي، وهو العيب بعينه.

**والقياس بـAST لا بـregex على الأسطر:** الاحتواء داخل كتلة سؤالٌ عن **البنية**، ولا
يُجاب بمطابقة نصّيّة سطريّة. (regex يُستعمل داخل السطر لاستخراج اسم الـGUC وعَلَم
``is_local`` وحدهما، بعد أن حدّدت الـAST موضع الاستدعاء.)

**ولا توحيد ميكانيكيّ لأسماء الـGUC:** الشجرة تحمل أكثر من اسم
(``app.current_tenant`` · ``app.current_tenant_id`` · ``app.tenant_id`` …). توحيدُها
آليّاً يكسر سياسات RLS التي تقرأ الاسم الآخر. فالحارس **يجرد** الأسماء ويُبلِغها،
ويحجب على النطاق وحده — والتوحيد قرارٌ بشريّ بمقارنة كلّ اسم بسياسة جداوله.

**راتشِت بأساسٍ مُعلَن:** العيب قائم في ٣٥ موضعاً يوم كُتِب هذا الحارس (٣٣ في أوّل قياسٍ نصّيّ، ثمّ ٣٥ بعد الترسية على الاستدعاء). حارسٌ يحجب
عليها كلّها لا يُدمَج، وحارسٌ يتجاهلها يُخفي الصنف. فالأساس **يتقلّص ولا ينمو**: موضعٌ
جديد ⇒ حجب؛ وموضعٌ أُصلِح ⇒ يُحذَف من الأساس (يفرضه فحصٌ يرفض الأساس البائت).

**ولا آليّة استثناء — بالقصد.** مسبارا health/readiness يضبطان مستأجِراً فارغاً ثمّ
ينفّذان ``SELECT 1``، فليسا خرق عزل والضبط فيهما عديم الجدوى أصلاً. ومع ذلك هما
**داخل الأساس** كبقيّة الـ٣٥، لا خارجه: الاستثناء كان **يحذفهما من العدّ المرئيّ**،
والأساس إنّما وُجِد ليُبقي الدَّين معدوداً. وتفسيرهما في سجلّ الفجوات
(``GUC-SCOPE-GUARD-SEES-ONE-FILE-01``) — **مُفسَّران لا مُستثنَيان**، والفرق أنّ
المُفسَّر يُعَدّ ويُرى ويُسقِط الأساس حين يُصلَح، والمُستثنى يختفي.

وكان هذا الموضع نفسه يقول «استثناء معلَّل واحد» بينما القاموس فارغ والفحص لا يُطبَّق
على أحد — وثيقةٌ تصف ما لا يفعله الكود، وهو صنف هذه الشريحة بعينه. أمسكَته مراجعةٌ
آليّة على #837، فحُذِفت الآليّة الميّتة وصُحِّح الوصف بدل أن يُصنَع استثناءٌ يُخفي.

الاستعمال::

    python3 scripts/ci/tenant_guc_scope_guard.py --check      # بوّابة
    python3 scripts/ci/tenant_guc_scope_guard.py --generate   # تحديث الأساس بعد إصلاح
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "architecture" / "tenant_guc_scope_baseline.json"

# يستخرج (اسم الـGUC، is_local) من نصّ استدعاء set_config. يُطبَّق على مقطع المصدر
# الذي حدّدته الـAST، لا على الملفّ كلّه — فالاحتواء تُجيبه البنية لا النصّ.
_SET_CONFIG = re.compile(
    r"set_config\(\s*'([a-zA-Z_.]+)'\s*,\s*[^,]*,\s*(true|false)\s*\)", re.IGNORECASE
)

_SCAN_DIRS = ("services", "shared", "agents", "scripts", "bots")


def _is_transaction_ctx(node: ast.expr) -> bool:
    """أهذه ``X.transaction()`` أو ``X.begin()``؟ — سياقُ معاملة يحفظ الـGUC."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    name = getattr(fn, "attr", None) or getattr(fn, "id", None)
    return name in {"transaction", "begin"}


def _transaction_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            if any(_is_transaction_ctx(i.context_expr) for i in node.items):
                spans.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    return spans


def _set_config_callsites(tree: ast.AST) -> list[tuple[int, str, str]]:
    """مواضع ``set_config`` **داخل سلاسل مُمرَّرة إلى استدعاء** — لا في نثرٍ ولا تعليق.

    **الترسية على الاستدعاء لا على نصّ الملفّ**، وهذا ليس تدقيقاً زائداً: أوّل صيغة من
    هذا الحارس مسحت الأسطر فالتقطت **شرحَه هو** (‏`set_config(..., true)` مذكوراً نثراً
    في وثيقته) وأدرجته مخالفةً. ملفٌّ يصف عيباً ليس ملفّاً يرتكبه — والفرق بنيويّ:
    السلسلة إمّا **وسيطُ نداءٍ للقاعدة** أو نصٌّ بشريّ، والـAST وحدها تفرّق.
    """
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                m = _SET_CONFIG.search(arg.value)
                if m:
                    out.append((arg.lineno, m.group(1), m.group(2).lower()))
    return out


def _iter_source_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for d in _SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            s = str(p)
            if "/node_modules/" in s or "/.git/" in s:
                continue
            # ملفّات الاختبار تصف العيب أو تحاكيه — ليست مسار إنتاج.
            if p.name.startswith("test_") or "/tests/" in s or "/tests_v9/" in s:
                continue
            out.append(p)
    return sorted(out)


def scan() -> tuple[list[dict], set[str]]:
    """يُرجِع (المخالفات، أسماء الـGUC المرصودة). مخالفة = ``true`` خارج معاملة."""
    offenders: list[dict] = []
    guc_names: set[str] = set()
    for path in _iter_source_files():
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "set_config" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            # ملفّ لا يُحلَّل ليس شهادة سلامة — يُبلَّغ لا يُتخطّى.
            offenders.append(
                {"file": str(path.relative_to(ROOT)), "line": 0, "guc": "<parse-error>"}
            )
            continue
        spans = _transaction_ranges(tree)
        for lineno, guc, is_local in _set_config_callsites(tree):
            guc_names.add(guc)
            if is_local != "true":
                continue  # نطاق الجلسة — خارج ما يقيسه هذا الحارس
            if any(a <= lineno <= b for a, b in spans):
                continue  # داخل معاملة ⇒ الضبط يحيا حتّى نهايتها
            offenders.append({"file": str(path.relative_to(ROOT)), "line": lineno, "guc": guc})
    return offenders, guc_names


def _head_sha() -> str:
    """رأس الشجرة الذي قِيس عليه الأساس — أو ``unknown`` إن تعذّر (لا رمي، ولا اختلاق).

    قيمةٌ مختلقة كانت ستُنتِج ختماً يبدو صادقاً ولا يُحيل إلى شيء؛ و``unknown`` تُبقي
    الفجوة مرئيّة لـ``claim_base_guard`` بدل أن تُخفيها.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "unknown"
    except OSError:
        return "unknown"


def _key(o: dict) -> str:
    return f"{o['file']}:{o['line']}"


def _load_baseline() -> dict:
    if not BASELINE.is_file():
        return {"offenders": [], "guc_names": []}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


# ── أساسُ القياس: طزاجةٌ حتميّة بدل هويّة التزام ─────────────────────────────
#
# ``measured_on`` **إشارةُ إسناد** لا سلطةَ طزاجة (GOV-01). لكنّ إبقاءه وحده يترك
# سؤالاً بلا جواب: متى يكون الـprovenance المنشور نفسُه بائتاً والنتيجةُ مع ذلك
# مطابقة؟ إعادةُ الاشتقاق تُجيب عن **النتيجة** ولا تُجيب عن **الأساس** — فيبقى ختمٌ
# قديم إلى الأبد بحجّة أنّ الناتج لم يتغيّر.
#
# فالطزاجةُ هنا شرطٌ **اقترانيّ** لا بديل: طازجٌ ⇔ تطابقَ الأساسُ **و** تطابقت النتيجة.
# وإعادةُ الاشتقاق تبقى سلطةَ النتيجة كما كانت.
#
# **ولمَ ثلاثةُ مكوّنات لا واحد:** بصمةُ المدخلات وحدها تعمى عن تغيّر المولّد نفسه
# بمدخلاتٍ ثابتة — وهو أخطر الانحرافين لأنّه يغيّر معنى الرقم بلا أثرٍ في مدخلاته.
CONTRACT_VERSION = 1


def _algorithm_digest(source: str | None = None) -> str:
    """بصمةُ **دلالة** المولّد لا بايتاته: AST مُجرَّدةً من التوثيق.

    بايتاتٌ خام تجعل كلّ تعديل تعليقٍ انحرافاً — وهو بالضبط الـchurn الذي وُجِد
    هذا العقد ليمنعه. والـAST تُطابِق حسّاسيّةَ البصمة بحسّاسيّة القياس: تغييرُ
    منطقٍ يقلبها، وإعادةُ صياغة شرحٍ لا تقلبها.
    """
    text = pathlib.Path(__file__).read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(text)
    for node in ast.walk(tree):
        # نزعُ التوثيق: نصٌّ يصف ولا يُنفَّذ.
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return hashlib.sha256(ast.dump(tree).encode("utf-8")).hexdigest()


def _input_manifest() -> list[dict]:
    """المدخلاتُ التي **تصل القياس فعلاً**، مرتّبةً ترتيباً قانونيّاً بمسارات نسبيّة.

    لا الشجرةُ كلّها ولا الملفّات الممسوحة كلّها (١٥٣٥): تلك تُعيد إنتاج الدوّامة
    نفسها بصورة hash مختلفة — تعديلُ ملفٍّ لا يمسّ القياس يُبيت الأساس. والمُستهلَك
    فعلاً هو ما يحمل ``set_config``؛ وما دونه يُقصَى في ``scan`` قبل أيّ تحليل.

    ومصدرُ هذا الحارس **مُقصًى**: هو الخوارزميّة لا مُدخَلها، وبصمتُه في
    ``_algorithm_digest`` بتطبيعٍ آخر. عدُّه مرّتين بقاعدتَي حسّاسيّة مختلفتين
    يجعل تعديلَ تعليقٍ فيه انحرافَ مدخلات — وهو ما نمنعه.

    ولا زمنَ ولا مسارَ مطلق ولا mtime في البصمة: كلّها تختلف بين آلتين على نفس
    الشيفرة، فتُنتِج انحرافاً لا يصف شيئاً.
    """
    me = pathlib.Path(__file__).resolve()
    out: list[dict] = []
    for path in _iter_source_files():
        if path.resolve() == me:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"set_config" not in raw:
            continue
        out.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return sorted(out, key=lambda e: e["path"])


def _input_digest(manifest: list[dict] | None = None) -> str:
    """التطبيعُ هنا لا عند المُنادي.

    الاعتمادُ على ترتيبِ المُنادي يجعل البصمة تصف **ترتيبَ الاكتشاف** — وهو تفصيلُ
    نظامِ ملفّاتٍ يختلف بين آلتين على نفس الشيفرة، لا خاصّيّةٌ من خواصّ القياس.
    وأمسك هذا اختبارُ إعادةِ الترتيب قبل أن يُلتزَم.
    """
    entries = _input_manifest() if manifest is None else manifest
    canonical = json.dumps(
        sorted([e["path"], e["sha256"]] for e in entries),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def basis_digest(
    input_digest: str | None = None,
    algorithm_digest: str | None = None,
    contract_version: int = CONTRACT_VERSION,
) -> str:
    parts = [
        str(contract_version),
        _input_digest() if input_digest is None else input_digest,
        _algorithm_digest() if algorithm_digest is None else algorithm_digest,
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def main() -> int:
    # مخرَجُ هذا الحارس عربيّ، و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب
    # **صحيحاً** ثمّ يموت وهو يطبع نجاحه (`UnicodeEncodeError`) ⇒ خروجٌ بـ1 يُقرَأ
    # «الحارس يحجب» وهو قد مرّ. حارسٌ يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من
    # حارسٍ صامت. القراءة كانت مثبَّتة بـ`encoding="utf-8"` منذ البداية — والمنسيّ
    # الكتابة. مقيس: §١٠ من `preflight --full` أسقطه، والحالة مُسجَّلة في سجلّ الفجوات.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args()

    offenders, guc_names = scan()
    found = {_key(o) for o in offenders}

    if args.generate:
        manifest = _input_manifest()
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "$comment": (
                        "أساسٌ مُعلَن لـGUC-SCOPE-GUARD-SEES-ONE-FILE-01 — "
                        "`set_config(..., true)` خارج معاملة يضيع قبل الاستعلام التالي. "
                        "**يتقلّص ولا ينمو**: موضع جديد يُحجَب، وموضع مُصلَح يُحذَف من هنا. "
                        "**`measured_on` إسنادٌ لا سلطةُ طزاجة** — السلطةُ "
                        "`measurement_basis_digest` (نسخةُ العقد · بصمةُ المدخلات الأصيلة · "
                        "بصمةُ دلالة المولّد) مع إعادة الاشتقاق، شرطين اقترانيّين. "
                        "وأسماء الـGUC مجرودة بلا توحيد ميكانيكيّ — التوحيد يكسر سياسات "
                        "RLS التي تقرأ الاسم الآخر، فهو قرار بشريّ بمقارنة كلّ اسم بجداوله."
                    ),
                    # **عقدُ هذا الحقل، صريحاً حتّى لا يُقرأ شهادةً:**
                    #
                    #   measured_on is traceability metadata.
                    #   It is NOT freshness authority.
                    #
                    # سلطةُ الطزاجة `measurement_basis_digest` مع إعادة الاشتقاق —
                    # شرطان اقترانيّان. والاسم أُبقي على حاله لأنّ تغييره يكسر قرّاءً
                    # قائمين، لا لأنّه دقيق: «قِيس على» يوحي لغةً بأنّ النتيجة تشهد
                    # على ذلك الالتزام كلّه، وهي لا تفعل.
                    #
                    # **يكتبه المولّد لا اليد.** `claim_base_guard` يُلزِم كلّ أساسٍ
                    # **مقيس** بـ`measured_on` — لأنّه يَبيت بحركة الشجرة، بخلاف قرارٍ
                    # بشريّ لا يَبيت. وأضفتُه يدويّاً أوّل مرّة فمحته أوّل إعادة توليد
                    # (الحارس صار في `_GENERATE_FLAG`)، فأحمرّ الجناح ثانيةً على العطل
                    # نفسه. تعديلٌ يدويّ على مصنوعةٍ مولَّدة لا ينجو — والمصدر الوحيد
                    # الذي ينجو هو المولّد.
                    "measured_on": _head_sha(),
                    # **إسنادٌ لا سلطةُ طزاجة** (GOV-01). السلطةُ أدناه:
                    # `measurement_basis_digest` مع إعادة الاشتقاق.
                    "measurement_contract_version": CONTRACT_VERSION,
                    "measurement_input_digest": _input_digest(manifest),
                    "measurement_algorithm_digest": _algorithm_digest(),
                    "measurement_basis_digest": basis_digest(
                        _input_digest(manifest), _algorithm_digest()
                    ),
                    "measurement_inputs": manifest,
                    "baseline": "GUC-SCOPE-GUARD-SEES-ONE-FILE-01",
                    "offenders": sorted(found),
                    "guc_names": sorted(guc_names),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"كُتِب الأساس: {len(found)} موضعاً · {len(guc_names)} اسم GUC")
        return 0

    base = _load_baseline()
    known = set(base.get("offenders", []))
    new = sorted(found - known)
    settled = sorted(known - found)

    if new:
        print("🔴 مواضع جديدة: `set_config(..., true)` خارج معاملة — الضبط يضيع قبل الاستعلام")
        print("   (asyncpg بلا معاملة = autocommit ⇒ كلّ استدعاء معاملة مستقلّة ⇒ RLS يُرجِع صفراً)")
        for k in new:
            print(f"     {k}")
        print("   العلاج: لُفّ الضبط والاستعلام في `async with conn.transaction():`")
        return 1

    if settled:
        print("أساسٌ بائت — مواضع أُصلِحت وما تزال مُدرَجة. احذفها بـ--generate:")
        for k in settled:
            print(f"     {k}")
        return 1

    # النتيجةُ مطابقة. يبقى السؤال الذي لا تُجيب عنه إعادةُ الاشتقاق وحدها: أهذا
    # الـprovenance المنشور يصف الأساسَ الذي أنتج هذا الرقم فعلاً؟
    stored = base.get("measurement_basis_digest")
    if not stored:
        print(
            "أساسُ القياس غير مُعلَن — حالةُ هجرةٍ صريحة لا طزاجةٌ ضمنيّة.\n"
            "   المصنوعة سابقة لعقد `measurement_basis_digest`، ولا يجوز أن يُقرأ\n"
            "   غيابُ البصمة تطابقاً. أغلِقها بـ--generate."
        )
        return 1
    if stored != basis_digest():
        # **بياتُ provenance لا انحدارٌ دلاليّ.** لا مخالفة جديدة ولا مخالفة اختفت؛
        # تغيّر ما بُني عليه الرقم (مُدخَلٌ أصيل أو منطقُ المولّد) والناتج صمد.
        # يُحجَب لأنّ الملفّ المنشور يحتاج تحديثاً — ولا يُصنَّف تغيّرَ قدرة.
        print(
            "PROVENANCE_STALE: أساسُ القياس تغيّر والنتيجةُ لم تتغيّر.\n"
            "   لا مخالفةَ جديدة ولا مخالفةَ اختفت — تغيّر مُدخَلٌ أصيل أو منطقُ\n"
            "   المولّد، فالـprovenance المنشور صار يصف أساساً غير الذي بين يديك.\n"
            "   هذا **تجديدُ إسنادٍ لا انحدارٌ دلاليّ**: أعِد التوليد بـ--generate.\n"
            f"   مُعلَن={stored[:12]}  مُشتقّ={basis_digest()[:12]}"
        )
        return 1
    print(
        f"tenant_guc_scope_ok  دَين مُعلَن={len(known)}  أسماء GUC={len(guc_names)}  (يتقلّص ولا ينمو)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
