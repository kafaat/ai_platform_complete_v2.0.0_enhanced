#!/usr/bin/env python3
"""حارسُ شكلِ نداء ``tenant_connection`` ومراجعِ ``main.X`` — عطلٌ يتنكّر في زيّ عُطلٍ آخر.

**العطلُ مُكذَّبٌ بالتنفيذ قبل سطرِ علاج.** ``api/main.py::tenant_connection`` توقيعُها
``(user)`` وتقرأ من وسيطها ثلاثَ سماتٍ لتضبط GUCات RLS الثلاثة. وكان **٢٢ موضعاً**
يمرّرون **مُعرِّفَ المستأجِر عارياً** بدل كائن المستخدِم::

    async with tenant_connection(user.tenant_id) as conn:   # ١٦ في gis_cloud_native
    async with tenant_connection(tenant_id) as conn:        # ٦ في irrigation_mpc

وسُئل التنفيذُ فأجاب (``UUID`` لا تحمل ``.tenant_id``)::

    بلا pool  · الشكل A ⇒ HTTPException 503 «قاعدة البيانات غير مفعّلة»
    بلا pool  · الشكل B ⇒ HTTPException 503 «قاعدة البيانات غير مفعّلة»   ← لا فرق
    مع pool   · الشكل A ⇒ AttributeError: 'UUID' object has no attribute 'tenant_id'
    مع pool   · الشكل B ⇒ ✅

**وهنا العلّةُ التي أبقته حيّاً سنيناً:** ``get_pool()`` أوّلُ سطرٍ في الدالّة، فترمي
٥٠٣ **قبل** أن تمسّ الوسيط. في كلّ بيئةٍ بلا قاعدة — وهي بيئةُ الاختبارات وCI — يُعطي
الشكلان **الجوابَ نفسَه بالحرف**. فالعطلُ غيرُ مرئيٍّ حيثُ يُقاس، وحيثُ يظهر يكون
مقنّعاً: ١٦/١٦ من مواضع ``gis_cloud_native`` داخل ``except Exception`` تُترجِم إلى
``_db_unavailable`` ⇒ **٥٠٣ «القاعدة غير متاحة أو الهجرات غير مطبّقة»** — وهي جملةٌ
كاذبة: القاعدةُ متاحةٌ والهجراتُ مطبَّقة، والخطأُ خطأُ نوعٍ في سطر النداء.

**وأخطرُ من ٥٠٣:** في ``irrigation_mpc`` المصائدُ **fail-closed**، فتتحوّل غلطةُ
النوع إلى **جوابِ عملٍ مُقنِع**: ``_field_belongs_to_tenant`` تُرجِع ``False`` فيردّ
المسارُ ``{"status": "blocked", "reason": "field_not_owned"}`` — يُقال للمزارع «هذا
الحقلُ ليس لك» والحقلُ حقلُه. التصميمُ الأمينُ (fail-closed) هو ما أخفى العطل.

**والصنفُ الثاني، وهو من نسله:** ``internal_service.py`` كان ينادي
``main.tenant_connection_for(...)`` — **دالّةٌ لا وجودَ لها في ``main.py``**. تُحلّ
السمةُ وقتَ النداء لا وقتَ الاستيراد، فلا استيرادٌ يفشل ولا مُدقِّقٌ يشتكي؛ ويبتلعها
``except Exception`` فتصير ٥٠٣ هي أيضاً. وقياسُ الأصل: مَرجِعا ``main.X`` غيرُ
المعرَّفَين في كامل خدمة المنصّة كانا **هذين السطرين فحسب** — فالحارسُ العامّ نظيفٌ
بلا استثناءات، لا لأنّنا ضيّقناه بل لأنّ المقيسَ كذلك.

**والعقدُ مُشتَقٌّ لا مكتوب:** لا قائمةَ سماتٍ مُثبَّتةً هنا. تُقرأ الدالّةُ من مصدرها
فيُستخرَج ما تقرؤه من وسيطها؛ فلو غُيِّر توقيعُها غداً تبِعه الحارسُ من نفسه. **تعريفٌ
واحد، لا شرطان يتّفقان اليوم.**
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "services" / "sahool-platform"
MAIN = PLATFORM / "api" / "main.py"


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - ملفٌّ مكسور
        return None


def contract() -> tuple[str, set[str]]:
    """اسمُ معامل ``tenant_connection`` والسماتُ التي تقرؤها منه — **من مصدرها**."""
    tree = _parse(MAIN)
    if tree is None:
        raise SystemExit(f"cannot parse {MAIN}")
    fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
            and n.name == "tenant_connection"
        ),
        None,
    )
    if fn is None or not fn.args.args:
        raise SystemExit("api/main.py no longer defines tenant_connection(<param>)")
    param = fn.args.args[0].arg
    attrs = {
        n.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == param
    }
    if not attrs:
        raise SystemExit("tenant_connection reads no attribute off its parameter — contract lost")
    return param, attrs


def main_toplevel_names() -> set[str]:
    """كلُّ ما يُصدِّره ``main.py`` فعلاً (بما في ذلك ما داخل ``try:`` للاستيراد الاختياريّ)."""
    tree = _parse(MAIN)
    if tree is None:
        raise SystemExit(f"cannot parse {MAIN}")
    names: set[str] = set()

    def collect(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Import | ast.ImportFrom):
                names.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.Try):
                collect(node.body)
                for handler in node.handlers:
                    collect(handler.body)
                collect(node.orelse)
                collect(node.finalbody)
            elif isinstance(node, ast.If | ast.With):
                collect(node.body)
                collect(getattr(node, "orelse", []))

    collect(tree.body)
    return names


def _main_aliases(tree: ast.Module) -> set[str]:
    """الأسماءُ المحلّيّة التي **تُربَط فعلاً** بوحدة ``api.main`` في هذا الملفّ.

    **تصويبٌ من مراجعةٍ آليّة، مُكذَّبٌ بالتنفيذ:** كانت هذه الدالّة تشتقّ الاسمَ من
    ``a.name.split(".")[-1]``، أي تفترض أنّ ``import api.main`` يربط ``main``. وقياسُ
    بايثون يقول غيرَ ذلك::

        import pkg.mod          ⇒ يربط: ['pkg']     ← لا 'mod'
        import pkg.mod as mod   ⇒ يربط: ['mod']
        from pkg import mod     ⇒ يربط: ['mod']

    فكان الاسمُ المُشتَقُّ **غيرَ موجودٍ في نطاق الملفّ**: لا يطابق شيئاً في الشكل
    المقصود (``api.main.X`` عقدتُه ``Attribute(value=Attribute(...))`` لا
    ``Attribute(value=Name)``)، **وقد يطابق متغيّراً محلّيّاً اسمه ``main`` لا علاقةَ
    له** ⇒ إنذارٌ كاذب. أي حارسٌ **يبدو** مغطّياً شكلَ استيرادٍ لا يغطّيه — وهو الصنفُ
    الذي وُضِع هذا الحارسُ أصلاً لإغلاقه، منقلباً عليه.

    والعلاجُ ليس إسقاطَ الشكل بل تغطيتَه في موضعه: ``ast.Import`` يُحتسَب **فقط** مع
    ``asname``، والشكلُ المنقوط ``api.main.X`` يُمسَك في ``scan`` بعقدته الحقيقيّة.
    وأُسقِط ``"services.sahool-platform.api"`` — مسارٌ لا يصلح وحدةً أصلاً (شَرطة).
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # ``import api.main`` يربط ``api`` وحدَه؛ فلا اسمَ قصيراً إلّا بـ``as``.
            aliases.update(a.asname for a in node.names if a.asname and a.name.endswith(".main"))
        elif isinstance(node, ast.ImportFrom) and (node.module or "") == "api":
            aliases.update(a.asname or a.name for a in node.names if a.name == "main")
    return aliases


def _main_attribute(node: ast.AST, aliases: set[str]) -> str | None:
    """اسمُ السمة إن كانت وصولاً إلى ``api.main`` — بالشكلين المربوطَين فعلاً.

    ``main.X`` حيث ``main`` اسمٌ مربوط · و``api.main.X`` المنقوط (الذي يربطه
    ``import api.main``). وبلا الثاني كان الحارسُ أعمى عن الشكل الأشيَع.
    """
    if not isinstance(node, ast.Attribute) or node.attr.startswith("__"):
        return None
    value = node.value
    if isinstance(value, ast.Name) and value.id in aliases:
        return node.attr
    if (
        isinstance(value, ast.Attribute)
        and value.attr == "main"
        and isinstance(value.value, ast.Name)
        and value.value.id == "api"
    ):
        return node.attr
    return None


def scan() -> list[str]:
    param, attrs = contract()
    exported = main_toplevel_names()
    failures: list[str] = []

    for path in sorted(PLATFORM.rglob("*.py")):
        if path == MAIN:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(ROOT)
        aliases = _main_aliases(tree)

        for node in ast.walk(tree):
            # ① شكلُ الوسيط: تمريرُ **سمةٍ** من الكائن بدل الكائن نفسِه.
            if isinstance(node, ast.Call) and node.args:
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name == "tenant_connection":
                    arg = node.args[0]
                    passed = None
                    if isinstance(arg, ast.Attribute) and arg.attr in attrs:
                        passed = ast.unparse(arg)
                    elif isinstance(arg, ast.Name) and arg.id in attrs:
                        passed = arg.id
                    if passed is not None:
                        failures.append(
                            f"{rel}:{node.lineno}: tenant_connection({passed}) — "
                            f"التوقيعُ ({param}) ويقرأ {sorted(attrs)}؛ مرِّر الكائنَ لا سمتَه. "
                            "بلا قاعدةٍ حيّةٍ يبدو هذا سليماً: كلا الشكلين يُعطي ٥٠٣."
                        )

            # ② مرجعُ ``main.X`` غيرُ معرَّفٍ في ``main.py`` — يُحَلّ وقتَ النداء فيمرّ صامتاً.
            attr = _main_attribute(node, aliases)
            if attr is not None and attr not in exported:
                failures.append(
                    f"{rel}:{node.lineno}: main.{attr} — غيرُ معرَّفٍ في api/main.py. "
                    "تُحَلّ السمةُ وقتَ النداء، فلا الاستيرادُ يفشل ولا المُدقِّقُ يشتكي."
                )

    return failures


if __name__ == "__main__":
    problems = scan()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(f"tenant_connection_call_shape_guard: {len(problems)} موضعاً")
    print("tenant_connection_call_shape_guard_ok")
